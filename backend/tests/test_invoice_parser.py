from datetime import date
from decimal import Decimal

import pytest

from app.services.invoice_parser import parse_amount, parse_invoice_text
from app.services.storage import detect_file_type


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("385.000", "385000"),
        ("1.234.567", "1234567"),
        ("1.234,56", "1234.56"),
        ("1,234.56", "1234.56"),
        ("Gs. 96.000", "96000"),
        ("12,5", "12.5"),
    ],
)
def test_parse_amount(raw: str, expected: str) -> None:
    assert parse_amount(raw) == Decimal(expected)


def test_parse_paraguayan_invoice() -> None:
    text = """ADMINISTRACION NACIONAL DE ELECTRICIDAD
RUC: 80009735-1
TIMBRADO N° 12345678
FACTURA 001-002-0458812
Fecha de emision: 14/10/2026
Vencimiento: 28 de octubre de 2026
Consumo                      350.000
IVA 10%                       35.000
TOTAL A PAGAR Gs.            385.000"""
    p = parse_invoice_text(text)
    assert p.supplier == "ADMINISTRACION NACIONAL DE ELECTRICIDAD"
    assert p.ruc == "80009735-1"
    assert p.stamp == "12345678"
    assert p.number == "001-002-0458812"
    assert p.issue_date == date(2026, 10, 14)
    assert p.due_date == date(2026, 10, 28)
    assert p.total == Decimal("385000")
    assert p.category_name == "Servicios"
    assert p.confidence == 1.0


def test_empty_text() -> None:
    assert parse_invoice_text("").confidence == 0


def test_detect_file_type() -> None:
    assert detect_file_type(b"%PDF-1.7") == "pdf"
    assert detect_file_type(b"\x89PNG\r\n\x1a\n....") == "png"
    assert detect_file_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp"
    assert detect_file_type(b"<script>") is None
