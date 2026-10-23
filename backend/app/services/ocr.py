"""Extracción de texto (PDF u OCR con Tesseract) y lectura de códigos QR.

Los archivos los sube el usuario (o le llegan de terceros), así que todo está
acotado: páginas, píxeles a procesar y tiempo de Tesseract. Sin estos límites,
una imagen muy angosta y alta o un PDF con una página gigante pueden pedir
decenas de GB de memoria y tumbar el backend.
"""

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium
import pytesseract
import zxingcpp
from PIL import Image, ImageOps

MAX_PAGES = 3
MIN_EMBEDDED_CHARS = 30
TARGET_WIDTH = 1600  # las imágenes más angostas se agrandan para que Tesseract lea mejor
MAX_WIDTH = 3000  # las más anchas se achican: más resolución no mejora la lectura
MAX_OCR_PIXELS = 24_000_000  # tope de píxeles de la imagen que recibe Tesseract
# Tope de cada lado: Tesseract y el lector de QR no aceptan más de 65.535 px, y una tira de
# 54 × 438.000 px entra en el tope de píxeles pero no en el de lado.
MAX_SIDE = 20_000
PDF_RENDER_SCALE = 2.5  # ~180 ppp para una página A4
OCR_TIMEOUT_SECONDS = 30  # por página; nginx corta la petición a los 120 s
MAX_QR_CODES = 4

# Pillow rechaza al abrir las imágenes de más de 2× este valor (bombas de descompresión).
Image.MAX_IMAGE_PIXELS = 60_000_000

logger = logging.getLogger(__name__)


@dataclass
class Extracted:
    text: str
    method: str  # "pdf", "ocr" o "none"
    qr: list[str] = field(default_factory=list)


def ocr_size(width: int, height: int) -> tuple[int, int]:
    """Tamaño al que se lleva la imagen antes del OCR, sin pasar nunca MAX_OCR_PIXELS."""
    if width <= 0 or height <= 0:
        return width, height
    scale = TARGET_WIDTH / width if width < TARGET_WIDTH else min(1.0, MAX_WIDTH / width)
    scale = min(scale, math.sqrt(MAX_OCR_PIXELS / (width * height)), MAX_SIDE / max(width, height))
    return max(1, int(width * scale)), max(1, int(height * scale))


def pdf_render_scale(width_pt: float, height_pt: float) -> float:
    """Escala para rasterizar una página PDF sin superar MAX_OCR_PIXELS."""
    if width_pt <= 0 or height_pt <= 0:
        return PDF_RENDER_SCALE
    return min(PDF_RENDER_SCALE, math.sqrt(MAX_OCR_PIXELS / (width_pt * height_pt)))


def _prepare(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img).convert("L")
    size = ocr_size(img.width, img.height)
    return img.resize(size) if size != img.size else img


def _ocr(img: Image.Image, languages: str) -> str:
    try:
        return pytesseract.image_to_string(img, lang=languages, timeout=OCR_TIMEOUT_SECONDS)
    except Exception:  # Tesseract: imagen demasiado grande, tiempo agotado, idioma faltante...
        logger.exception("Tesseract no pudo leer la imagen")
        return ""


def read_qr_codes(img: Image.Image) -> list[str]:
    """Textos de los códigos QR de la imagen (el KuDE de la factura electrónica trae uno)."""
    try:
        results = zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.QRCode)
    except Exception:  # imagen inválida o formato no soportado por zxing
        logger.exception("No se pudo buscar códigos QR")
        return []
    return [r.text for r in results if r.text][:MAX_QR_CODES]


def _render(page: pdfium.PdfPage) -> Image.Image:
    return page.render(scale=pdf_render_scale(*page.get_size())).to_pil()


def _from_pdf(path: Path, languages: str) -> Extracted:
    with pdfplumber.open(str(path), pages=list(range(1, MAX_PAGES + 1))) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    doc = pdfium.PdfDocument(str(path))
    try:
        pages = [_prepare(_render(doc[i])) for i in range(min(len(doc), MAX_PAGES))]
    finally:
        doc.close()
    qr = read_qr_codes(pages[0]) if pages else []
    if len(text.strip()) >= MIN_EMBEDDED_CHARS:
        return Extracted(text, "pdf", qr)
    return Extracted("\n".join(_ocr(p, languages) for p in pages), "ocr", qr)


def extract(path: Path, languages: str) -> Extracted:
    try:
        if path.suffix == ".pdf":
            return _from_pdf(path, languages)
        with Image.open(path) as img:
            prepared = _prepare(img)
        return Extracted(_ocr(prepared, languages), "ocr", read_qr_codes(prepared))
    except Exception:  # pdfminer, pdfium y Pillow lanzan errores heterogéneos
        logger.exception("No se pudo extraer texto de %s", path.name)
        return Extracted("", "none")


def extract_text(path: Path, languages: str) -> tuple[str, str]:
    """Compatibilidad: (texto, método) donde método es 'pdf', 'ocr' o 'none'."""
    result = extract(path, languages)
    return result.text, result.method if result.text else "none"
