import io
import shutil

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont


def _invoice_png() -> bytes:
    img = Image.new("RGB", (1400, 800), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=40)
    lines = ["SUPERSEIS S.A.", "RUC 80018754-0", "Factura 003-001-0078213", "Fecha: 19/10/2026", "TOTAL 612.400"]
    for i, line in enumerate(lines):
        draw.text((60, 60 + i * 110), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_rejects_unsupported_file(client: TestClient) -> None:
    r = client.post("/api/v1/invoices/analyze", files={"file": ("x.pdf", b"<html>no</html>", "application/pdf")})
    assert r.status_code == 422


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract no instalado")
def test_analyze_image_extracts_fields(client: TestClient) -> None:
    r = client.post("/api/v1/invoices/analyze", files={"file": ("f.png", _invoice_png(), "image/png")})
    assert r.status_code == 200, r.text
    draft = r.json()
    assert draft["ruc"] == "80018754-0"
    assert draft["number"] == "003-001-0078213"
    assert draft["total"] == 612400
    assert draft["category_id"] is not None

    body = {"supplier": "Superseis", "total": 612400, "file_key": draft["file_key"]}
    created = client.post("/api/v1/invoices", json=body)
    assert created.status_code == 201
    inv = created.json()
    assert inv["has_file"] is True
    assert "file_key" not in inv
    file = client.get(f"/api/v1/invoices/{inv['id']}/file")
    assert file.status_code == 200
    assert file.headers["content-type"] == "image/png"


def test_cannot_attach_unknown_file(client: TestClient) -> None:
    r = client.post("/api/v1/invoices", json={"total": 1, "file_key": "0" * 32 + ".pdf"})
    assert r.status_code == 404


def test_pay_unpay_lifecycle_and_overdue(client: TestClient, expense_category: dict) -> None:
    body = {"supplier": "ANDE", "total": 385000, "due_date": "2020-01-10", "category_id": expense_category["id"]}
    inv = client.post("/api/v1/invoices", json=body).json()
    assert inv["overdue"] is True
    assert [i["id"] for i in client.get("/api/v1/invoices", params={"status": "overdue"}).json()] == [inv["id"]]

    paid = client.post(f"/api/v1/invoices/{inv['id']}/pay", json={"paid_on": "2026-10-20", "method": "qr"}).json()
    assert paid["status"] == "paid"
    assert paid["overdue"] is False
    txs = client.get("/api/v1/transactions").json()["items"]
    assert len(txs) == 1
    assert txs[0]["invoice_id"] == inv["id"]
    assert txs[0]["amount"] == 385000

    client.patch(f"/api/v1/invoices/{inv['id']}", json={"total": 400000})
    assert client.get("/api/v1/transactions").json()["items"][0]["amount"] == 400000

    # Pagar dos veces no duplica el gasto
    client.post(f"/api/v1/invoices/{inv['id']}/pay", json={})
    assert client.get("/api/v1/transactions").json()["total"] == 1

    assert client.post(f"/api/v1/invoices/{inv['id']}/unpay").json()["status"] == "pending"
    assert client.get("/api/v1/transactions").json()["total"] == 0


def test_deleting_payment_reopens_invoice(client: TestClient) -> None:
    inv = client.post("/api/v1/invoices", json={"supplier": "Tigo", "total": 249000, "already_paid": True}).json()
    assert inv["status"] == "paid"
    tx = client.get("/api/v1/transactions").json()["items"][0]
    client.delete(f"/api/v1/transactions/{tx['id']}")
    assert client.get("/api/v1/invoices").json()[0]["status"] == "pending"


def test_delete_invoice_removes_payment(client: TestClient) -> None:
    inv = client.post("/api/v1/invoices", json={"supplier": "ESSAP", "total": 96000, "already_paid": True}).json()
    assert client.delete(f"/api/v1/invoices/{inv['id']}").status_code == 200
    assert client.get("/api/v1/transactions").json()["total"] == 0
