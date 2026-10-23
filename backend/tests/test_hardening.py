"""Pruebas de regresión de la revisión de seguridad y de flujo de datos."""

import io
import os
import time
from datetime import date, timedelta
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.rate_limit import LoginAttemptLimiter
from app.core.security import ACCESS_COOKIE
from app.main import app
from app.services import invoice_parser
from app.services.invoice_parser import MAX_AMOUNT, parse_invoice_text
from app.services.ocr import MAX_OCR_PIXELS, MAX_SIDE, MAX_WIDTH, TARGET_WIDTH, ocr_size, pdf_render_scale


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(buf, "PNG")
    return buf.getvalue()


def _upload(client: TestClient) -> str:
    r = client.post("/api/v1/invoices/analyze", files={"file": ("f.png", _png(), "image/png")})
    assert r.status_code == 200, r.text
    return r.json()["file_key"]


def _user_files() -> list[Path]:
    root = get_settings().storage_dir
    return sorted(p for p in root.glob("*/*") if p.is_file())


@pytest.fixture(autouse=True)
def _empty_storage():
    for p in _user_files():
        p.unlink()


# ---------- Sesión, base de datos y cabeceras ----------


def test_failed_commit_is_reported_as_error(client: TestClient, monkeypatch) -> None:
    """El commit debe ocurrir antes de responder: si falla, el cliente no puede recibir 201."""
    probe = TestClient(app, raise_server_exceptions=False)
    probe.cookies = client.cookies
    probe.headers.update(client.headers)

    def broken_commit(self: Session) -> None:
        raise RuntimeError("la base no confirmó")

    monkeypatch.setattr(Session, "commit", broken_commit)
    r = probe.post("/api/v1/transactions", json={"amount": 1000, "date": "2026-10-01"})
    assert r.status_code == 500


def test_token_without_expiration_is_rejected(client: TestClient) -> None:
    token = jwt.encode({"sub": "1", "ver": 0}, get_settings().secret_key, algorithm="HS256")
    client.cookies.set(ACCESS_COOKIE, token)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_api_responses_are_never_cached(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").headers["cache-control"] == "no-store"
    csv = client.get("/api/v1/reports/export.csv")
    assert csv.headers["cache-control"] == "no-store"


def test_login_limit_is_shared_between_processes(client: TestClient) -> None:
    """Dos procesos del backend (dos instancias del limitador) comparten el conteo."""
    worker_a, worker_b = LoginAttemptLimiter(3, 300), LoginAttemptLimiter(3, 300)
    for _ in range(3):
        worker_a.hit("1.2.3.4:x@example.com")
    assert worker_b.is_blocked("1.2.3.4:x@example.com")
    assert not worker_b.is_blocked("1.2.3.4:otro@example.com")
    worker_b.reset("1.2.3.4:x@example.com")
    assert not worker_a.is_blocked("1.2.3.4:x@example.com")


def test_wrong_current_password_keeps_session_and_is_rate_limited(client: TestClient) -> None:
    wrong = {"current_password": "no-es-esta-clave", "new_password": "otra-clave-segura-456"}
    for _ in range(get_settings().login_max_attempts):
        assert client.post("/api/v1/auth/password", json=wrong).status_code == 422
    assert client.post("/api/v1/auth/password", json=wrong).status_code == 429
    assert client.get("/api/v1/auth/me").status_code == 200  # la sesión sigue activa


# ---------- Validación de entradas ----------


def test_blank_names_are_rejected(client: TestClient) -> None:
    assert client.post("/api/v1/categories", json={"name": "   "}).status_code == 422
    r = client.post("/api/v1/scheduled-payments", json={"name": "  ", "amount": 10, "day_of_month": 1})
    assert r.status_code == 422
    ok = client.post("/api/v1/categories", json={"name": "  Mascotas  "})
    assert ok.json()["name"] == "Mascotas"


def test_impossible_month_is_rejected_not_500(client: TestClient) -> None:
    assert client.get("/api/v1/reports/summary", params={"month": "0000-01"}).status_code == 422
    assert client.get("/api/v1/reports/calendar", params={"month": "0001-01"}).status_code == 422


def test_huge_offset_is_rejected_not_500(client: TestClient) -> None:
    assert client.get("/api/v1/transactions", params={"offset": 10**20}).status_code == 422


def test_search_wildcards_are_literal(client: TestClient) -> None:
    client.post("/api/v1/transactions", json={"amount": 1, "date": "2026-10-01", "description": "Jugo 100% natural"})
    client.post("/api/v1/transactions", json={"amount": 1, "date": "2026-10-01", "description": "Pan"})
    assert client.get("/api/v1/transactions", params={"q": "%"}).json()["total"] == 1
    assert client.get("/api/v1/transactions", params={"q": "_"}).json()["total"] == 0


def test_csv_neutralizes_formulas_in_category_names(client: TestClient) -> None:
    cat = client.post("/api/v1/categories", json={"name": "=cmd|' /C calc'!A0"}).json()
    client.post("/api/v1/transactions", json={"amount": 5, "date": "2026-10-01", "category_id": cat["id"]})
    client.post("/api/v1/transactions", json={"amount": 5, "date": "2026-10-01", "description": "@SUM(A1:A9)"})
    text = client.get("/api/v1/reports/export.csv").text
    assert "'=cmd" in text
    assert "'@SUM(A1:A9)" in text


# ---------- Facturas y sus pagos ----------


def test_paid_invoice_total_cannot_become_zero(client: TestClient) -> None:
    inv = client.post("/api/v1/invoices", json={"supplier": "ANDE", "total": 1000, "already_paid": True}).json()
    r = client.patch(f"/api/v1/invoices/{inv['id']}", json={"total": 0})
    assert r.status_code == 422


def test_editing_invoice_payment_keeps_invoice_in_sync(client: TestClient) -> None:
    body = {"supplier": "Tigo", "number": "001-001-1", "total": 249000, "already_paid": True}
    inv = client.post("/api/v1/invoices", json=body).json()
    tx = client.get("/api/v1/transactions").json()["items"][0]

    assert client.patch(f"/api/v1/transactions/{tx['id']}", json={"kind": "income"}).status_code == 422
    r = client.patch(f"/api/v1/transactions/{tx['id']}", json={"amount": 250000, "date": "2026-10-05"})
    assert r.status_code == 200
    synced = next(i for i in client.get("/api/v1/invoices").json() if i["id"] == inv["id"])
    assert synced["total"] == 250000
    assert synced["paid_on"] == "2026-10-05"

    client.patch(f"/api/v1/invoices/{inv['id']}", json={"supplier": "Tigo Paraguay"})
    assert client.get("/api/v1/transactions").json()["items"][0]["description"] == "Factura Tigo Paraguay 001-001-1"


def test_scheduled_payment_cannot_move_to_another_month(client: TestClient) -> None:
    sp = client.post(
        "/api/v1/scheduled-payments",
        json={"name": "Alquiler", "amount": 100, "day_of_month": 5, "start_month": "2026-01"},
    ).json()
    tx = client.post(f"/api/v1/scheduled-payments/{sp['id']}/pay", json={"month": "2026-02"}).json()
    assert client.patch(f"/api/v1/transactions/{tx['id']}", json={"date": "2026-03-05"}).status_code == 422
    assert client.patch(f"/api/v1/transactions/{tx['id']}", json={"date": "2026-02-20"}).status_code == 200


def test_file_cannot_be_shared_by_two_invoices(client: TestClient) -> None:
    key = _upload(client)
    first = client.post("/api/v1/invoices", json={"total": 10, "file_key": key})
    assert first.status_code == 201
    second = client.post("/api/v1/invoices", json={"total": 20, "file_key": key})
    assert second.status_code == 409


def test_deleting_invoice_keeps_file_until_trash_is_emptied(client: TestClient) -> None:
    key = _upload(client)
    inv = client.post("/api/v1/invoices", json={"total": 10, "file_key": key}).json()
    assert [p.name for p in _user_files()] == [key]
    assert client.delete(f"/api/v1/invoices/{inv['id']}").status_code == 200
    assert [p.name for p in _user_files()] == [key]  # se puede restaurar con su archivo
    assert client.delete("/api/v1/trash").status_code == 204
    assert _user_files() == []


def test_failed_analysis_leaves_no_file(client: TestClient, monkeypatch) -> None:
    probe = TestClient(app, raise_server_exceptions=False)
    probe.cookies = client.cookies
    probe.headers.update(client.headers)

    def boom(_: str) -> None:
        raise RuntimeError("fallo del lector")

    monkeypatch.setattr("app.services.invoices.parse_invoice_text", boom)
    r = probe.post("/api/v1/invoices/analyze", files={"file": ("f.png", _png(), "image/png")})
    assert r.status_code == 500
    assert _user_files() == []


def test_abandoned_uploads_are_purged(client: TestClient) -> None:
    abandoned = _upload(client)
    kept = _upload(client)
    client.post("/api/v1/invoices", json={"total": 10, "file_key": kept})
    two_days_ago = time.time() - 2 * 86400
    for p in _user_files():
        os.utime(p, (two_days_ago, two_days_ago))

    fresh = _upload(client)  # cada análisis limpia lo abandonado hace más de un día
    names = {p.name for p in _user_files()}
    assert abandoned not in names
    assert {kept, fresh} <= names


# ---------- Reportes ----------


def test_scheduled_payment_is_not_overdue_before_it_existed(client: TestClient) -> None:
    client.post("/api/v1/scheduled-payments", json={"name": "Gimnasio", "amount": 100, "day_of_month": 10})
    old = client.get("/api/v1/reports/calendar", params={"month": "2020-01"}).json()
    assert all(not d["dues"] for d in old["days"])
    this_month = date.today().strftime("%Y-%m")
    current = client.get("/api/v1/reports/calendar", params={"month": this_month}).json()
    assert sum(len(d["dues"]) for d in current["days"]) == 1


def test_today_expense_does_not_depend_on_selected_month(client: TestClient) -> None:
    client.post("/api/v1/transactions", json={"amount": 7000, "date": date.today().isoformat()})
    other = (date.today().replace(day=1) - timedelta(days=40)).strftime("%Y-%m")
    s = client.get("/api/v1/reports/summary", params={"month": other}).json()
    assert s["today_expense"] == 7000
    assert s["expense"] == 0


# ---------- Lectura de facturas y OCR ----------


def test_long_codes_are_not_taken_as_total() -> None:
    """El CDC de 44 dígitos de la factura electrónica antes daba un total imposible (error 500)."""
    text = "SUPERSEIS S.A.\nCDC: 01800187540001003007821322026101910123456789\nGs. 612.400"
    p = parse_invoice_text(text)
    assert p.total is not None
    assert p.total <= MAX_AMOUNT
    assert p.total == 612400


def test_parser_handles_hostile_whitespace_quickly() -> None:
    hostile = "RUC" + " " * 30_000 + "x\n" + "EMPRESA" + "\n" * 30_000
    start = time.perf_counter()
    parse_invoice_text(hostile * 5)
    assert time.perf_counter() - start < 2


def test_parser_truncates_huge_text() -> None:
    assert len(invoice_parser.normalize_text("a" * 10_000_000)) == invoice_parser.MAX_TEXT_CHARS


@pytest.mark.parametrize(
    ("width", "height"),
    [(100, 1_000_000), (54, 438_178), (438_178, 54), (800, 1000), (6000, 8000), (12000, 9000), (1, 1)],
)
def test_ocr_image_size_is_bounded(width: int, height: int) -> None:
    w, h = ocr_size(width, height)
    assert w * h <= MAX_OCR_PIXELS
    assert w <= max(MAX_WIDTH, TARGET_WIDTH)
    assert max(w, h) <= MAX_SIDE  # Tesseract y el lector de QR no aceptan más de 65.535 px por lado


def test_small_images_are_enlarged_for_ocr() -> None:
    assert ocr_size(800, 1000) == (TARGET_WIDTH, 2000)


def test_giant_pdf_page_is_rendered_within_limits() -> None:
    scale = pdf_render_scale(14400, 14400)  # página de 5 x 5 metros
    assert (14400 * scale) * (14400 * scale) <= MAX_OCR_PIXELS * 1.001
    assert pdf_render_scale(595, 842) == 2.5  # A4 normal: sin cambios
