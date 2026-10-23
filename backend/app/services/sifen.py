"""Factura electrónica de Paraguay (SIFEN): XML del documento y QR del KuDE.

Cuando hay XML o QR, los datos son exactos (no hay que adivinar con OCR). Los
nombres de los campos siguen el manual técnico de SIFEN; si algún emisor usa una
variante que no se reconoce, se cae de vuelta a la lectura por texto.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlparse
from xml.etree.ElementTree import Element

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

from app.services.invoice_parser import MAX_AMOUNT, ParsedInvoice, apply_cdc, decode_cdc, guess_category

MAX_XML_BYTES = 2 * 1024 * 1024
_XML_MARKERS = (b"ekuatia", b"<rDE", b"<DE ", b"<DE>", b":rDE", b":DE ")


def looks_like_sifen_xml(content: bytes) -> bool:
    head = content[:4096].lstrip(b"\xef\xbb\xbf \t\r\n")
    return head.startswith(b"<") and any(m in content[:65536] for m in _XML_MARKERS)


def _money(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        amount = Decimal(value.strip())
    except InvalidOperation:
        return None
    return amount if Decimal(0) <= amount <= MAX_AMOUNT else None


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_xml(content: bytes) -> ParsedInvoice | None:
    """Lee un XML de factura electrónica. Devuelve None si no es un documento de SIFEN."""
    if len(content) > MAX_XML_BYTES:
        return None
    try:
        root = fromstring(content, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (ParseError, DefusedXmlException, ValueError):
        return None

    fields: dict[str, str] = {}
    cdc_attr: str | None = None
    for el in root.iter():
        name = _local(el.tag) if isinstance(el.tag, str) else ""
        if name == "DE" and (ident := el.get("Id")):
            cdc_attr = ident
        if name and name not in fields and el.text and el.text.strip():
            fields[name] = el.text.strip()
    if "dRucEm" not in fields and cdc_attr is None:
        return None

    result = ParsedInvoice(source="xml")
    if fields.get("dRucEm") and fields.get("dDVEmi"):
        result.ruc = f"{fields['dRucEm']}-{fields['dDVEmi']}"
    result.supplier = (fields.get("dNomFanEmi") or fields.get("dNomEmi") or "")[:120] or None
    result.stamp = fields.get("dNumTim")
    if all(k in fields for k in ("dEst", "dPunExp", "dNumDoc")):
        result.number = f"{fields['dEst']}-{fields['dPunExp']}-{fields['dNumDoc']}"
    result.issue_date = _date(fields.get("dFeEmiDE"))
    result.due_date = _date(fields.get("dVencCuo"))
    result.total = _money(fields.get("dTotGralOpe"))
    result.iva10 = _money(fields.get("dIVA10"))
    result.iva5 = _money(fields.get("dIVA5"))
    result.exempt = _money(fields.get("dSubExe"))
    if cdc_attr and (info := decode_cdc(cdc_attr)):
        result.cdc = info.cdc
        result.ruc = result.ruc or info.ruc
        result.number = result.number or info.number
        result.issue_date = result.issue_date or info.issue_date
    result.category_name = guess_category((result.supplier or "").upper())
    return result


def xml_text(content: bytes) -> str:
    """Texto plano del XML (para mostrar "texto leído" y buscar reglas)."""
    try:
        root: Element = fromstring(content[:MAX_XML_BYTES], forbid_dtd=True)
    except (ParseError, DefusedXmlException, ValueError):
        return ""
    return "\n".join(f"{_local(e.tag)}: {e.text.strip()}" for e in root.iter() if e.text and e.text.strip())


# ---------- QR del KuDE ----------


def _hex_date(value: str) -> date | None:
    """En el QR, la fecha de emisión viene en hexadecimal (por ejemplo "323032362d31302d3134...")."""
    value = value.strip()
    if re.fullmatch(r"(?:[0-9a-fA-F]{2})+", value):
        try:
            return _date(bytes.fromhex(value).decode("ascii", "ignore"))
        except ValueError:
            return None
    return _date(value)


def parse_qr(payload: str) -> dict | None:
    """Datos del QR de un KuDE: CDC, total, IVA y fecha. None si el QR no es de SIFEN."""
    try:
        url = urlparse(payload.strip())
    except ValueError:
        return None
    params = {k.lower(): v[0] for k, v in parse_qs(url.query).items() if v}
    info = decode_cdc(params.get("id", ""))
    if info is None:
        return None
    return {
        "cdc": info,
        "total": _money(params.get("dtotgralope")),
        "iva_total": _money(params.get("dtotiva")),
        "issue_date": _hex_date(params["dfeemide"]) if "dfeemide" in params else None,
    }


def apply_qr(result: ParsedInvoice, qr: dict) -> None:
    """Completa (y corrige) lo leído por texto con los datos exactos del QR."""
    apply_cdc(result, qr["cdc"])
    result.source = "qr"
    if qr["issue_date"]:
        result.issue_date = qr["issue_date"]
    total: Decimal | None = qr["total"]
    if total:
        result.total = total
    iva: Decimal | None = qr["iva_total"]
    if iva is not None and total and result.iva10 is None and result.iva5 is None:
        # El QR trae solo el IVA total: se asigna si cuadra con todo al 10 % o todo al 5 %.
        if abs(total / 11 - iva) <= 1:
            result.iva10, result.iva5 = iva, Decimal(0)
        elif abs(total / 21 - iva) <= 1:
            result.iva5, result.iva10 = iva, Decimal(0)
