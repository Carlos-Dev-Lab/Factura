"""Reconocimiento de campos en el texto de una factura.

Reglas pensadas para facturas de Paraguay (RUC, timbrado, numeración
001-001-0000001, factura electrónica con CDC), que también funcionan con
formatos genéricos.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_MONTHS = {
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "set": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}
_AMOUNT_RE = re.compile(r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?")
_RUC_LABELED_RE = re.compile(r"R\.?\s*U\.?\s*C\.?\s*(?:N[°ºO.]*)?\s*:?\s*(\d{4,9}\s*-\s*\d)")
_RUC_RE = re.compile(r"\b(\d{5,8}-\d)\b")
_NUMBER_RE = re.compile(r"\b(\d{3})\s*-\s*(\d{3})\s*-\s*(\d{5,9})\b")
_STAMP_RE = re.compile(r"TIMBRADO\s*(?:N[°ºO.]*)?\s*:?\s*(\d{6,10})")
_NUMERIC_DATE_RE = re.compile(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})")
_TEXT_DATE_RE = re.compile(r"(\d{1,2})\s*(?:de\s+)?([a-záé]{3,})\.?\s*(?:de\s+)?(\d{4})", re.I)
_SUPPLIER_LABEL_RE = re.compile(r"(?:RAZ[OÓ]N\s+SOCIAL|EMPRESA|PROVEEDOR)\s*:?\s*(.+)", re.I)
_TOTAL_STRONG_RE = re.compile(r"TOTAL\s*(A\s*PAGAR|GENERAL|FACTURA|GS|G\$|₲)")
_NOT_SUPPLIER_RE = re.compile(r"FACTURA|RUC|TIMBRADO|FECHA|TEL|DIREC|CDC|KUDE")
# Tramos de dígitos (con espacios simples): el CDC suele imprimirse en grupos de 4.
_DIGIT_RUN_RE = re.compile(r"\d[\d ]{42,200}\d")
_IVA10_RE = re.compile(r"\(?\s*10\s*%\s*\)?\s*:?\s*(?:GS\.?|G\$|₲)?\s*(\d[\d.,]*)")
_IVA5_RE = re.compile(r"(?<!\d)\(?\s*5\s*%\s*\)?\s*:?\s*(?:GS\.?|G\$|₲)?\s*(\d[\d.,]*)")
_EXEMPT_RE = re.compile(r"EXENTAS?\s*:?\s*(?:GS\.?|G\$|₲)?\s*(\d[\d.,]*)")

CATEGORY_HINTS: dict[str, tuple[str, ...]] = {
    "Servicios": (
        "ANDE",
        "ESSAP",
        "TIGO",
        "PERSONAL",
        "CLARO",
        "COPACO",
        "INTERNET",
        "ENERGIA",
        "ELECTRICIDAD",
        "AGUA",
        "CABLE",
    ),
    "Supermercado": ("SUPER", "STOCK", "BIGGIE", "SALEMMA", "MERCADO", "CASA RICA"),
    "Transporte": ("COMBUSTIBLE", "PETROPAR", "SHELL", "COPETROL", "PUMA", "NAFTA", "BOLT", "UBER", "PEAJE"),
    "Salud": ("FARMACIA", "PUNTO FARMA", "SANATORIO", "CLINICA", "LABORATORIO"),
    "Comidas": ("RESTAURANTE", "PIZZA", "BURGER", "CAFE", "PANADER", "DELIVERY", "PEDIDOSYA"),
    "Hogar": ("FERRETER", "MUEBLE", "ALQUILER", "INMOBILIAR"),
    "Educación": ("COLEGIO", "UNIVERSIDAD", "LIBRER", "CURSO"),
}
_KEY_FIELDS = ("supplier", "ruc", "number", "issue_date", "total")

# Un PDF puede traer millones de caracteres; una factura real entra holgada en este límite.
MAX_TEXT_CHARS = 20_000
# El mayor monto que admite la base (Numeric(14, 2)). Números más largos son códigos
# (CDC de 44 dígitos de la factura electrónica, códigos de barras, teléfonos), no montos.
MAX_AMOUNT = Decimal("999999999999.99")
_HSPACE_RE = re.compile(r"[^\S\n]+")
_BLANK_LINES_RE = re.compile(r"\n\s*\n+")

# Tipos de documento electrónico de SIFEN que tienen sentido como comprobante de compra.
CDC_DOCUMENT_TYPES = {"01", "04", "05", "06", "07"}


def _is_amount(value: Decimal | None, minimum: Decimal) -> bool:
    return value is not None and minimum <= value <= MAX_AMOUNT


def normalize_text(text: str) -> str:
    """Recorta el texto y colapsa espacios.

    Además de limpiar el OCR, deja como máximo un espacio entre palabras: así las
    expresiones con varios `\\s*` seguidos no pueden caer en backtracking costoso.
    """
    text = _HSPACE_RE.sub(" ", text[:MAX_TEXT_CHARS])
    return _BLANK_LINES_RE.sub("\n", text)


# ---------- RUC y CDC ----------


def check_digit(digits: str, base_max: int = 11) -> int:
    """Dígito verificador módulo 11 que usa la SET para el RUC y el CDC."""
    total, weight = 0, 2
    for c in reversed(digits):
        if weight > base_max:
            weight = 2
        total += int(c) * weight
        weight += 1
    rest = total % 11
    return 11 - rest if rest > 1 else 0


def ruc_is_valid(ruc: str) -> bool | None:
    """True/False si el RUC tiene la forma "base-DV"; None si no se puede comprobar."""
    m = re.fullmatch(r"([0-9]{1,8})-([0-9])", ruc.strip())
    if not m:
        return None
    return check_digit(m.group(1)) == int(m.group(2))


@dataclass
class CdcInfo:
    """Datos que vienen codificados en el CDC (44 dígitos) de una factura electrónica."""

    cdc: str
    document_type: str
    ruc: str
    number: str
    issue_date: date


def decode_cdc(cdc: str) -> CdcInfo | None:
    """Decodifica y valida un CDC. Devuelve None si no es un CDC válido."""
    if not re.fullmatch(r"[0-9]{44}", cdc) or check_digit(cdc[:43]) != int(cdc[43]):
        return None
    doc_type, ruc_base, ruc_dv = cdc[0:2], cdc[2:10], cdc[10]
    if doc_type not in CDC_DOCUMENT_TYPES or cdc[24] not in "12" or check_digit(ruc_base) != int(ruc_dv):
        return None
    try:
        issued = date(int(cdc[25:29]), int(cdc[29:31]), int(cdc[31:33]))
    except ValueError:
        return None
    return CdcInfo(
        cdc=cdc,
        document_type=doc_type,
        ruc=f"{int(ruc_base)}-{ruc_dv}",
        number=f"{cdc[11:14]}-{cdc[14:17]}-{cdc[17:24]}",
        issue_date=issued,
    )


def find_cdc(text: str) -> CdcInfo | None:
    for run in _DIGIT_RUN_RE.findall(text):
        digits = run.replace(" ", "")
        for i in range(len(digits) - 43):
            if info := decode_cdc(digits[i : i + 44]):
                return info
    return None


# ---------- Montos y fechas ----------


@dataclass
class ParsedInvoice:
    supplier: str | None = None
    ruc: str | None = None
    number: str | None = None
    stamp: str | None = None
    cdc: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    total: Decimal | None = None
    iva10: Decimal | None = None
    iva5: Decimal | None = None
    exempt: Decimal | None = None
    category_name: str | None = None
    source: str = "ocr"

    @property
    def confidence(self) -> float:
        return round(sum(1 for f in _KEY_FIELDS if getattr(self, f)) / len(_KEY_FIELDS), 2)

    @property
    def ruc_valid(self) -> bool | None:
        return ruc_is_valid(self.ruc) if self.ruc else None


def parse_amount(raw: str) -> Decimal | None:
    """Interpreta montos con separadores de miles '.' o ',' (385.000 · 1.234,56 · 1,234.56)."""
    s = re.sub(r"[^\d.,]", "", raw)
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = s.replace(",", "") if len(tail) == 3 else f"{head.replace(',', '')}.{tail}"
    elif "." in s:
        tail = s.rpartition(".")[2]
        if len(tail) == 3 or s.count(".") > 1:
            s = s.replace(".", "")
    try:
        return Decimal(s.strip("."))
    except InvalidOperation:
        return None


def parse_date(text: str) -> date | None:
    if m := _NUMERIC_DATE_RE.search(text):
        d, mo, y = (int(g) for g in m.groups())
        try:
            return date(y + 2000 if y < 100 else y, mo, d)
        except ValueError:
            pass
    if m := _TEXT_DATE_RE.search(text):
        month = _MONTHS.get(m.group(2).lower()[:3])
        if month:
            try:
                return date(int(m.group(3)), month, int(m.group(1)))
            except ValueError:
                pass
    return None


def guess_category(upper_text: str) -> str | None:
    for name, words in CATEGORY_HINTS.items():
        if any(w in upper_text for w in words):
            return name
    return None


def _find_total(lines: list[str], text: str) -> Decimal | None:
    ranked: list[tuple[int, Decimal]] = []
    for line in lines:
        upper = line.upper()
        amounts = [a for a in (parse_amount(x) for x in _AMOUNT_RE.findall(line)) if _is_amount(a, Decimal("0.01"))]
        if not amounts:
            continue
        if _TOTAL_STRONG_RE.search(upper):
            ranked.append((2, amounts[-1]))
        elif "TOTAL" in upper and "IVA" not in upper and "SUB" not in upper:
            ranked.append((1, amounts[-1]))
    if ranked:
        best = max(rank for rank, _ in ranked)
        return max(v for rank, v in ranked if rank == best)
    fallback = [a for a in (parse_amount(x) for x in _AMOUNT_RE.findall(text)) if _is_amount(a, Decimal(1000))]
    return max(fallback) if fallback else None


def _round_like(value: Decimal, total: Decimal | None) -> Decimal:
    places = Decimal("1") if total is None or total == total.to_integral_value() else Decimal("0.01")
    return value.quantize(places, rounding=ROUND_HALF_UP)


def _find_taxes(lines: list[str], total: Decimal | None) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """(IVA 10 %, IVA 5 %, exentas) desde la liquidación del IVA o el subtotal por columnas."""
    iva10 = iva5 = exempt = None
    for line in lines:
        upper = line.upper()
        if "IVA" in upper or "LIQUID" in upper:
            if iva10 is None and (m := _IVA10_RE.search(upper)):
                iva10 = parse_amount(m.group(1))
            if iva5 is None and (m := _IVA5_RE.search(upper)):
                iva5 = parse_amount(m.group(1))
        if exempt is None and "EXENTA" in upper and "IVA" not in upper and (m := _EXEMPT_RE.search(upper)):
            exempt = parse_amount(m.group(1))
    if iva10 is None and iva5 is None:
        # Subtotal en columnas: exentas, gravadas 5 % y gravadas 10 % (IVA incluido).
        for line in lines:
            if "SUB" in line.upper() and "TOTAL" in line.upper():
                amounts = [parse_amount(x) for x in _AMOUNT_RE.findall(line)]
                if len(amounts) == 3 and all(a is not None for a in amounts):
                    exe, g5, g10 = amounts  # type: ignore[misc]
                    exempt = exempt if exempt is not None else exe
                    iva5, iva10 = _round_like(g5 / 21, total), _round_like(g10 / 11, total)
                    break
    limit = total if total is not None else MAX_AMOUNT
    clean = [v if v is not None and Decimal(0) <= v <= limit else None for v in (iva10, iva5, exempt)]
    return clean[0], clean[1], clean[2]


def _find_supplier(lines: list[str], text: str) -> str | None:
    if (m := _SUPPLIER_LABEL_RE.search(text)) and len(m.group(1).strip()) > 2:
        return m.group(1).strip()[:120]
    for line in lines[:8]:
        if sum(c.isalpha() for c in line) >= 3 and not _NOT_SUPPLIER_RE.search(line.upper()):
            return line[:120]
    return None


def _find_ruc(text: str) -> str | None:
    """El RUC rotulado primero; entre varios candidatos, el que tenga dígito verificador correcto."""
    upper = text.upper()
    labeled = [re.sub(r"\s", "", m.group(1)) for m in _RUC_LABELED_RE.finditer(upper)]
    loose = [m.group(1) for m in _RUC_RE.finditer(text)]
    candidates = labeled + [c for c in loose if c not in labeled]
    for c in candidates:
        if ruc_is_valid(c):
            return c
    return candidates[0] if candidates else None


def parse_invoice_text(text: str) -> ParsedInvoice:
    text = normalize_text(text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    upper = text.upper()
    result = ParsedInvoice()

    result.ruc = _find_ruc(text)
    if m := _NUMBER_RE.search(text):
        result.number = "-".join(m.groups())
    if m := _STAMP_RE.search(upper):
        result.stamp = m.group(1)

    for line in lines:
        upper_line = line.upper()
        if "VENC" in upper_line and not result.due_date:
            result.due_date = parse_date(line)
        elif (
            ("FECHA" in upper_line or "EMISI" in upper_line)
            and not result.issue_date
            and "VIGENCIA" not in upper_line
            and "INICIO" not in upper_line
        ):
            result.issue_date = parse_date(line)
    result.issue_date = result.issue_date or parse_date(text)

    result.total = _find_total(lines, text)
    result.iva10, result.iva5, result.exempt = _find_taxes(lines, result.total)
    result.supplier = _find_supplier(lines, text)
    result.category_name = guess_category(upper)

    # El CDC trae RUC, número y fecha exactos (validados con dígito verificador): manda sobre el OCR.
    if info := find_cdc(text):
        apply_cdc(result, info)
    return result


def apply_cdc(result: ParsedInvoice, info: CdcInfo) -> None:
    result.cdc = info.cdc
    result.ruc = info.ruc
    result.number = info.number
    result.issue_date = info.issue_date
    if result.source in ("ocr", "pdf"):
        result.source = "cdc"
