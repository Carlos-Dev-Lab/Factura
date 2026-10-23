"""Pruebas de las funciones nuevas: pagos fijos, presupuestos, proyección, avisos, cuentas,
factura electrónica, reglas, importación, papelera y reportes."""

import io
import json
import zipfile
from datetime import UTC, date, datetime, timedelta

import pytest
import zxingcpp
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Account, User
from app.services import notify
from app.services.accounts import card_cycle
from app.services.invoice_parser import check_digit, decode_cdc, find_cdc, parse_invoice_text, ruc_is_valid
from app.services.sifen import parse_qr, parse_xml

TODAY = date.today()
MONTH = TODAY.strftime("%Y-%m")


def _cat(client: TestClient, name: str, kind: str = "expense") -> int:
    return next(c["id"] for c in client.get("/api/v1/categories").json() if c["name"] == name and c["kind"] == kind)


def _cdc(ruc: str = "80009735", dv: str = "1", day: str = "20261014", number: str = "0458812") -> str:
    base = f"01{ruc}{dv}001002{number}2{day}1123456789"
    return base + str(check_digit(base))


# ---------- RUC, CDC, QR y XML ----------


def test_ruc_check_digit_matches_real_companies() -> None:
    assert ruc_is_valid("80009735-1")  # ANDE
    assert ruc_is_valid("80000519-8")  # ESSAP
    assert ruc_is_valid("80009735-2") is False
    assert ruc_is_valid("sin guion") is None


def test_cdc_is_decoded_and_validated() -> None:
    cdc = _cdc()
    info = decode_cdc(cdc)
    assert info is not None
    assert (info.ruc, info.number, info.issue_date) == ("80009735-1", "001-002-0458812", date(2026, 10, 14))
    broken = cdc[:-1] + str((int(cdc[-1]) + 1) % 10)
    assert decode_cdc(broken) is None
    # Impreso en grupos de 4 como en el KuDE, y rodeado de otros números.
    grouped = " ".join(cdc[i : i + 4] for i in range(0, 44, 4))
    assert find_cdc(f"Tel 021 123 456 CDC {grouped} Total 385.000").cdc == cdc  # type: ignore[union-attr]


def test_cdc_in_text_overrides_ocr_guesses() -> None:
    text = f"ANDE\nRUC 1234567-0\nFactura 999-999-0000001\nCDC: {_cdc()}\nTOTAL A PAGAR 385.000\nIVA 10% 35.000"
    p = parse_invoice_text(text)
    assert p.ruc == "80009735-1"
    assert p.number == "001-002-0458812"
    assert p.issue_date == date(2026, 10, 14)
    assert p.iva10 == 35000
    assert p.source == "cdc"


def test_iva_is_read_from_liquidation_line() -> None:
    text = (
        "FARMACIA X\nTOTAL A PAGAR 221.000\nLIQUIDACION DEL IVA: (5%) 1.000 (10%) 19.182 TOTAL IVA: 20.182\nEXENTAS 0"
    )
    p = parse_invoice_text(text)
    assert (p.iva5, p.iva10, p.exempt) == (1000, 19182, 0)


def test_qr_url_gives_exact_total() -> None:
    issued = b"2026-10-14T09:30:00".hex()
    url = f"https://ekuatia.set.gov.py/consultas/qr?nVersion=150&Id={_cdc()}&dFeEmiDE={issued}&dTotGralOpe=385000&dTotIVA=35000"
    qr = parse_qr(url)
    assert qr is not None
    assert qr["total"] == 385000
    assert qr["issue_date"] == date(2026, 10, 14)
    assert parse_qr("https://example.com/?Id=123") is None


SIFEN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd"><dVerFor>150</dVerFor>
<DE Id="{cdc}"><gTimb><iTiDE>1</iTiDE><dNumTim>12345678</dNumTim><dEst>001</dEst><dPunExp>002</dPunExp>
<dNumDoc>0458812</dNumDoc></gTimb><gDatGralOpe><dFeEmiDE>2026-10-14T10:00:00</dFeEmiDE><gEmis>
<dRucEm>80009735</dRucEm><dDVEmi>1</dDVEmi><dNomEmi>ADMINISTRACION NACIONAL DE ELECTRICIDAD</dNomEmi>
<dNomFanEmi>ANDE</dNomFanEmi></gEmis></gDatGralOpe><gTotSub><dSubExe>0</dSubExe><dIVA5>0</dIVA5>
<dIVA10>35000</dIVA10><dTotGralOpe>385000</dTotGralOpe></gTotSub></DE></rDE>"""


def test_sifen_xml_is_parsed_exactly() -> None:
    p = parse_xml(SIFEN_XML.format(cdc=_cdc()).encode())
    assert p is not None
    assert (p.supplier, p.ruc, p.stamp, p.number) == ("ANDE", "80009735-1", "12345678", "001-002-0458812")
    assert (p.total, p.iva10, p.issue_date, p.cdc) == (385000, 35000, date(2026, 10, 14), _cdc())


def test_xml_upload_and_safe_download(client: TestClient) -> None:
    r = client.post("/api/v1/invoices/analyze", files={"file": ("fe.xml", SIFEN_XML.format(cdc=_cdc()), "text/xml")})
    assert r.status_code == 200, r.text
    draft = r.json()
    assert draft["method"] == "xml"
    assert draft["total"] == 385000
    assert draft["category_id"] == _cat(client, "Servicios")
    inv = client.post("/api/v1/invoices", json={"supplier": "ANDE", "total": 385000, "file_key": draft["file_key"]})
    file = client.get(f"/api/v1/invoices/{inv.json()['id']}/file")
    assert file.headers["content-disposition"].startswith("attachment")
    assert "sandbox" in file.headers["content-security-policy"]


def test_xml_with_external_entity_is_not_expanded(client: TestClient) -> None:
    evil = (
        b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><rDE><dNomEmi>&x;</dNomEmi></rDE>'
    )
    r = client.post("/api/v1/invoices/analyze", files={"file": ("x.xml", evil, "text/xml")})
    assert r.status_code == 200
    assert "root:" not in r.text
    assert r.json()["method"] == "none"


def test_qr_on_photo_is_read(client: TestClient) -> None:
    url = f"https://ekuatia.set.gov.py/consultas/qr?nVersion=150&Id={_cdc()}&dTotGralOpe=385000&dTotIVA=35000"
    code = zxingcpp.create_barcode(url, zxingcpp.BarcodeFormat.QRCode).to_image(scale=6)
    h, w = code.shape
    qr = Image.frombuffer("L", (w, h), bytes(code), "raw", "L", 0, 1)
    page = Image.new("L", (w + 200, h + 200), 255)
    page.paste(qr, (100, 100))
    buf = io.BytesIO()
    page.save(buf, "PNG")
    draft = client.post("/api/v1/invoices/analyze", files={"file": ("q.png", buf.getvalue(), "image/png")}).json()
    assert draft["method"] == "qr"
    assert (draft["total"], draft["ruc"], draft["cdc"], draft["iva10"]) == (385000, "80009735-1", _cdc(), 35000)


def test_duplicate_invoice_is_detected(client: TestClient) -> None:
    body = {"supplier": "ANDE", "ruc": "80009735-1", "number": "001-002-0458812", "total": 385000}
    assert client.post("/api/v1/invoices", json=body).status_code == 201
    again = client.post("/api/v1/invoices", json=body)
    assert again.status_code == 409
    assert "Guardar igual" in again.json()["detail"]
    assert client.post("/api/v1/invoices", json=body | {"allow_duplicate": True}).status_code == 201
    r = client.post("/api/v1/invoices/analyze", files={"file": ("fe.xml", SIFEN_XML.format(cdc=_cdc()), "text/xml")})
    assert r.json()["duplicate_of"]["label"].startswith("ANDE")


def test_taxes_cannot_exceed_total(client: TestClient) -> None:
    r = client.post("/api/v1/invoices", json={"supplier": "X", "total": 1000, "iva10": 900, "exempt": 500})
    assert r.status_code == 422


# ---------- Reglas de categorías ----------


def test_categories_are_learned_from_invoices_and_descriptions(client: TestClient) -> None:
    hogar = _cat(client, "Hogar")
    client.post(
        "/api/v1/invoices", json={"supplier": "Ferretería", "ruc": "80000519-8", "total": 10, "category_id": hogar}
    )
    s = client.get("/api/v1/categories/suggest", params={"ruc": "80000519-8"}).json()
    assert s == {"category_id": hogar, "source": "ruc"}

    comidas = _cat(client, "Comidas")
    client.post(
        "/api/v1/transactions",
        json={"amount": 5, "date": "2026-10-01", "description": "Biggie", "category_id": comidas},
    )
    s = client.get("/api/v1/categories/suggest", params={"text": "BIGGIE Mcal. López"}).json()
    assert s == {"category_id": comidas, "source": "historial"}  # lo aprendido gana a la lista fija

    rule = client.post(
        "/api/v1/categories/rules", json={"match": "contains", "pattern": "Peaje", "category_id": hogar}
    ).json()
    assert client.get("/api/v1/categories/suggest", params={"text": "peaje ruta 2"}).json()["source"] == "regla"
    assert client.delete(f"/api/v1/categories/rules/{rule['id']}").status_code == 204


# ---------- Pagos fijos ----------


def test_scheduled_income_installments_and_real_amount(client: TestClient) -> None:
    sueldo = client.post(
        "/api/v1/scheduled-payments",
        json={
            "name": "Sueldo",
            "kind": "income",
            "amount": 5_000_000,
            "day_of_month": 5,
            "category_id": _cat(client, "Sueldo", "income"),
            "start_month": "2026-01",
        },
    )
    assert sueldo.status_code == 201
    wrong = client.post(
        "/api/v1/scheduled-payments",
        json={"name": "X", "kind": "income", "amount": 1, "day_of_month": 1, "category_id": _cat(client, "Hogar")},
    )
    assert wrong.status_code == 422  # categoría de gasto en un ingreso

    plan = client.post(
        "/api/v1/scheduled-payments",
        json={
            "name": "Heladera",
            "amount": 300_000,
            "day_of_month": 10,
            "start_month": "2026-01",
            "end_month": "2026-03",
        },
    ).json()
    assert plan["installments"] == 3
    feb = client.get("/api/v1/reports/calendar", params={"month": "2026-02"}).json()
    dues = [d for day in feb["days"] for d in day["dues"]]
    heladera = next(d for d in dues if d["name"] == "Heladera")
    assert heladera["detail"] == "Cuota 2 de 3"
    assert next(d for d in dues if d["name"] == "Sueldo")["direction"] == "in"
    april = client.get("/api/v1/reports/calendar", params={"month": "2026-04"}).json()
    assert all(d["name"] != "Heladera" for day in april["days"] for d in day["dues"])
    assert client.post(f"/api/v1/scheduled-payments/{plan['id']}/pay", json={"month": "2026-04"}).status_code == 422

    ande = client.post(
        "/api/v1/scheduled-payments",
        json={"name": "ANDE", "amount": 200_000, "variable_amount": True, "day_of_month": 20, "start_month": "2026-01"},
    ).json()
    for month, amount in (("2026-01", 180_000), ("2026-02", 220_000)):
        tx = client.post(f"/api/v1/scheduled-payments/{ande['id']}/pay", json={"month": month, "amount": amount}).json()
        assert tx["amount"] == amount
    history = client.get(f"/api/v1/scheduled-payments/{ande['id']}/history").json()
    assert history["last_amount"] == 220_000
    assert history["average"] == 200_000
    march = client.get("/api/v1/reports/calendar", params={"month": "2026-03"}).json()
    assert next(d for day in march["days"] for d in day["dues"] if d["name"] == "ANDE")["estimated"] is True


# ---------- Presupuestos, proyección y avisos ----------


def test_category_budget_projection_and_alerts(client: TestClient) -> None:
    comidas = _cat(client, "Comidas")
    assert client.patch(f"/api/v1/categories/{comidas}", json={"monthly_budget": 100_000}).status_code == 200
    sueldo_cat = _cat(client, "Sueldo", "income")
    assert client.patch(f"/api/v1/categories/{sueldo_cat}", json={"monthly_budget": 1}).status_code == 422

    today = TODAY.isoformat()
    client.post("/api/v1/transactions", json={"kind": "income", "amount": 1_000_000, "date": today})
    client.post("/api/v1/transactions", json={"amount": 90_000, "date": today, "category_id": comidas})
    last_day = (TODAY.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    client.post(
        "/api/v1/scheduled-payments",
        json={"name": "Internet", "amount": 300_000, "day_of_month": last_day.day, "start_month": MONTH},
    )
    client.post(
        "/api/v1/scheduled-payments",
        json={
            "name": "Freelance",
            "kind": "income",
            "amount": 500_000,
            "day_of_month": last_day.day,
            "start_month": MONTH,
        },
    )

    s = client.get("/api/v1/reports/summary", params={"month": MONTH}).json()
    budget = next(b for b in s["budgets"] if b["category_id"] == comidas)
    assert (budget["pct"], budget["state"]) == (90.0, "warn")
    p = s["projection"]
    assert (p["pending_income"], p["pending_expense"]) == (500_000, 300_000)
    assert p["projected_balance"] == 1_000_000 - 90_000 + 500_000 - 300_000
    assert p["days_left"] == (last_day - TODAY).days + 1
    assert all(d["direction"] == "out" for d in s["upcoming"] if d["name"] == "Internet")
    assert s["due_total"] == 300_000  # los cobros esperados no suman a "por pagar"

    alerts = client.get("/api/v1/alerts").json()
    assert any(a["key"].startswith(f"presupuesto:{comidas}:80") for a in alerts)

    past = client.get("/api/v1/reports/summary", params={"month": "2020-01"}).json()["projection"]
    assert (past["days_left"], past["daily_allowance"]) == (0, None)


def test_alerts_for_overdue_and_today(client: TestClient) -> None:
    client.post("/api/v1/invoices", json={"supplier": "ESSAP", "total": 96_000, "due_date": "2020-01-10"})
    client.post("/api/v1/invoices", json={"supplier": "Tigo", "total": 249_000, "due_date": TODAY.isoformat()})
    alerts = client.get("/api/v1/alerts").json()
    levels = {a["title"]: a["level"] for a in alerts}
    overdue = next(t for t in levels if t.startswith("La factura de ESSAP venció hace "))
    assert levels[overdue] == "danger"
    assert any(a["level"] == "warn" and "Tigo" in a["title"] for a in alerts)
    assert alerts[0]["level"] == "danger"  # lo urgente primero


# ---------- Notificaciones ----------


def test_push_subscription_rejects_internal_urls(client: TestClient) -> None:
    keys = {"p256dh": "BNc" + "a" * 84, "auth": "x" * 22}
    bad = client.post("/api/v1/notifications/push", json={"endpoint": "http://db:5432/x", "keys": keys})
    assert bad.status_code == 422
    sneaky = {"endpoint": "https://fcm.googleapis.com.evil.example/x", "keys": keys}
    assert client.post("/api/v1/notifications/push", json=sneaky).status_code == 422
    ok = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": keys, "label": "Celular"}
    assert client.post("/api/v1/notifications/push", json=ok).status_code == 204
    assert client.get("/api/v1/notifications/settings").json()["push_devices"] == 1
    key = client.get("/api/v1/notifications/push/key").json()["public_key"]
    assert len(key) == 87  # punto P-256 sin comprimir (65 bytes) en base64url


def test_daily_digest_is_sent_once(client: TestClient, monkeypatch) -> None:
    sent: list[dict] = []
    monkeypatch.setattr(notify, "webpush", lambda info, data, **kw: sent.append(json.loads(data)))
    keys = {"p256dh": "BNc" + "a" * 84, "auth": "x" * 22}
    client.post("/api/v1/notifications/push", json={"endpoint": "https://fcm.googleapis.com/fcm/send/a", "keys": keys})
    client.post("/api/v1/invoices", json={"supplier": "ESSAP", "total": 96_000, "due_date": "2020-01-10"})

    now = datetime.combine(TODAY, datetime.min.time()).replace(hour=9)
    with SessionLocal() as db:
        user = db.scalar(select(User))
        assert notify.should_send_digest(db, user, now)
        assert notify.run_digest(db, user, now) == 1
        db.commit()
        assert not notify.should_send_digest(db, user, now)
        assert notify.deliver(db, user, now, digest=False) == 0  # ya avisado: no se repite
    assert len(sent) == 1
    assert "ESSAP" in sent[0]["body"]


def test_telegram_link_requires_configuration(client: TestClient) -> None:
    assert client.post("/api/v1/notifications/telegram").status_code == 404
    assert client.get("/api/v1/notifications/settings").json()["telegram_available"] is False


# ---------- Cuentas, transferencias y tarjeta ----------


def test_card_cycle_dates() -> None:
    card = Account(closing_day=25, due_day=5)
    assert card_cycle(card, date(2026, 10, 21)) == (date(2026, 9, 25), date(2026, 10, 25), date(2026, 10, 5))
    assert card_cycle(card, date(2026, 10, 26)) == (date(2026, 10, 25), date(2026, 11, 25), date(2026, 11, 5))
    feb = Account(closing_day=31, due_day=10)
    assert card_cycle(feb, date(2026, 3, 5))[0] == date(2026, 2, 28)


def test_accounts_balances_transfers_and_card(client: TestClient) -> None:
    cash = client.get("/api/v1/accounts").json()[0]
    assert cash["name"] == "Efectivo"
    bank = client.post("/api/v1/accounts", json={"name": "Itaú", "type": "bank", "opening_balance": 2_000_000}).json()
    closing = 1 if TODAY.day != 1 else 15
    card = client.post(
        "/api/v1/accounts",
        json={"name": "Visa", "type": "card", "closing_day": closing, "due_day": 10, "credit_limit": 5_000_000},
    ).json()
    assert client.post("/api/v1/accounts", json={"name": "Otra", "type": "card"}).status_code == 422

    old = (TODAY - timedelta(days=40)).isoformat()
    client.post("/api/v1/transactions", json={"amount": 300_000, "date": old, "account_id": card["id"]})
    client.post("/api/v1/transactions", json={"amount": 50_000, "date": TODAY.isoformat(), "account_id": card["id"]})
    client.post("/api/v1/transactions", json={"amount": 100_000, "date": TODAY.isoformat(), "account_id": bank["id"]})
    t = client.post(
        "/api/v1/accounts/transfers",
        json={"from_account_id": bank["id"], "to_account_id": card["id"], "amount": 100_000, "date": TODAY.isoformat()},
    )
    assert t.status_code == 201

    by_id = {a["id"]: a for a in client.get("/api/v1/accounts").json()}
    assert by_id[bank["id"]]["balance"] == 2_000_000 - 100_000 - 100_000
    visa = by_id[card["id"]]
    assert visa["balance"] == -300_000 - 50_000 + 100_000
    assert visa["card"]["debt"] == 250_000
    assert visa["card"]["statement_amount"] == 300_000 - 100_000
    assert visa["card"]["current_period"] == 50_000
    assert visa["card"]["available"] == 5_000_000 - 250_000

    page = client.get("/api/v1/transactions", params={"account_id": card["id"]}).json()
    assert (page["total"], page["expense_total"]) == (2, 350_000)
    assert client.delete(f"/api/v1/accounts/{bank['id']}").status_code == 409  # tiene movimientos
    client.patch(f"/api/v1/accounts/{bank['id']}", json={"archived": True})
    r = client.post("/api/v1/transactions", json={"amount": 1, "date": "2026-10-01", "account_id": bank["id"]})
    assert r.status_code == 422


# ---------- Importación de extractos ----------

STATEMENT = """Banco X - Extracto de cuenta
Fecha;Descripción;Débito;Crédito;Saldo
01/10/2026;COMPRA BIGGIE;150.000;;1.000.000
02/10/2026;TRANSFERENCIA RECIBIDA;;2.500.000;3.500.000
03/10/2026;PAGO ANDE;385.000;;3.115.000
Saldo final;;;;3.115.000
"""


def test_bank_csv_import(client: TestClient) -> None:
    client.post("/api/v1/transactions", json={"amount": 385_000, "date": "2026-10-03", "description": "ANDE"})
    r = client.post("/api/v1/imports/preview", files={"file": ("e.csv", STATEMENT.encode("latin-1"), "text/csv")})
    assert r.status_code == 200, r.text
    preview = r.json()
    rows = preview["rows"]
    assert [(x["date"], x["amount"], x["kind"]) for x in rows] == [
        ("2026-10-01", 150_000, "expense"),
        ("2026-10-02", 2_500_000, "income"),
        ("2026-10-03", 385_000, "expense"),
    ]
    assert rows[0]["category_id"] == _cat(client, "Supermercado")
    assert [x["duplicate"] for x in rows] == [False, False, True]
    assert preview["skipped"] == 1

    account = client.get("/api/v1/accounts").json()[0]["id"]
    items = [{k: x[k] for k in ("date", "description", "amount", "kind", "category_id")} for x in rows[:2]]
    done = client.post("/api/v1/imports/commit", json={"account_id": account, "items": items})
    assert done.status_code == 201
    assert done.json() == {"created": 2, "total": 2_650_000}
    assert client.get("/api/v1/transactions", params={"account_id": account}).json()["total"] == 2


def test_bank_xlsx_import_with_signed_amounts(client: TestClient) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Fecha", "Concepto", "Importe"])
    ws.append([datetime(2026, 10, 5), "Shell Mcal López", -120000])
    ws.append([datetime(2026, 10, 6), "Sueldo", 5000000])
    buf = io.BytesIO()
    wb.save(buf)
    preview = client.post("/api/v1/imports/preview", files={"file": ("e.xlsx", buf.getvalue(), "application/x")}).json()
    assert [(x["kind"], x["amount"]) for x in preview["rows"]] == [("expense", 120000), ("income", 5000000)]
    assert preview["rows"][0]["category_id"] == _cat(client, "Transporte")


def test_import_rejects_old_excel(client: TestClient) -> None:
    r = client.post("/api/v1/imports/preview", files={"file": ("e.xls", b"\xd0\xcf\x11\xe0" + b"0" * 100, "x")})
    assert r.status_code == 422


# ---------- Papelera ----------


def test_trash_restores_each_kind_of_item(client: TestClient) -> None:
    servicios = _cat(client, "Servicios")
    tx = client.post("/api/v1/transactions", json={"amount": 10, "date": "2026-10-01", "category_id": servicios}).json()
    inv = client.post("/api/v1/invoices", json={"supplier": "Tigo", "total": 249_000, "already_paid": True}).json()

    trash_id = client.delete(f"/api/v1/transactions/{tx['id']}").json()["trash_id"]
    assert client.post(f"/api/v1/trash/{trash_id}/restore").json() == {"entity": "transaction", "id": tx["id"]}

    trash_id = client.delete(f"/api/v1/invoices/{inv['id']}").json()["trash_id"]
    assert client.get("/api/v1/transactions").json()["total"] == 1
    client.post(f"/api/v1/trash/{trash_id}/restore")
    restored = next(i for i in client.get("/api/v1/invoices").json() if i["id"] == inv["id"])
    assert restored["status"] == "paid"
    assert client.get("/api/v1/transactions").json()["total"] == 2  # volvió también su pago

    trash_id = client.delete(f"/api/v1/categories/{servicios}").json()["trash_id"]
    assert client.get("/api/v1/transactions").json()["items"][-1]["category"] is None
    client.post(f"/api/v1/trash/{trash_id}/restore")
    again = next(t for t in client.get("/api/v1/transactions").json()["items"] if t["id"] == tx["id"])
    assert again["category"]["id"] == servicios

    sp = client.post(
        "/api/v1/scheduled-payments", json={"name": "Gym", "amount": 1, "day_of_month": 1, "start_month": "2026-01"}
    ).json()
    paid = client.post(f"/api/v1/scheduled-payments/{sp['id']}/pay", json={"month": "2026-02"}).json()
    trash_id = client.delete(f"/api/v1/scheduled-payments/{sp['id']}").json()["trash_id"]
    client.post(f"/api/v1/trash/{trash_id}/restore")
    relinked = next(t for t in client.get("/api/v1/transactions").json()["items"] if t["id"] == paid["id"])
    assert relinked["scheduled_payment_id"] == sp["id"]
    assert client.get("/api/v1/trash").json() == []


def test_trash_restore_conflicts_and_isolation(client: TestClient, make_client, monkeypatch) -> None:
    from app.core import config

    cat = client.post("/api/v1/categories", json={"name": "Mascotas"}).json()
    trash_id = client.delete(f"/api/v1/categories/{cat['id']}").json()["trash_id"]
    client.post("/api/v1/categories", json={"name": "Mascotas"})
    assert client.post(f"/api/v1/trash/{trash_id}/restore").status_code == 409

    monkeypatch.setattr(config.get_settings(), "allow_registration", True)
    intruder = make_client("intruso@example.com")
    assert intruder.post(f"/api/v1/trash/{trash_id}/restore").status_code == 404
    assert intruder.get("/api/v1/trash").json() == []


# ---------- Reportes y exportaciones ----------


def test_year_report(client: TestClient) -> None:
    client.post("/api/v1/transactions", json={"kind": "income", "amount": 1000, "date": "2025-03-10"})
    client.post("/api/v1/transactions", json={"amount": 400, "date": "2025-03-11", "category_id": _cat(client, "Ocio")})
    client.post("/api/v1/transactions", json={"amount": 200, "date": "2025-07-01"})
    y = client.get("/api/v1/reports/year", params={"year": 2025}).json()
    # El promedio cuenta desde marzo (primer mes con movimientos) hasta diciembre: 10 meses.
    assert (y["income"], y["expense"], y["balance"], y["months_counted"]) == (1000, 600, 400, 10)
    assert y["months"][2] == {"month": "2025-03", "income": 1000, "expense": 400, "balance": 600}
    assert y["average_expense"] == 60
    assert y["categories"][0]["name"] == "Ocio"
    assert client.get("/api/v1/reports/year", params={"year": 1}).status_code == 422


def test_fiscal_report_csv_and_zip(client: TestClient) -> None:
    client.post(
        "/api/v1/invoices",
        json={
            "supplier": "Farmacia",
            "ruc": "80000519-8",
            "number": "001-001-1",
            "total": 221_000,
            "iva10": 19_182,
            "iva5": 1_000,
            "issue_date": "2026-09-15",
            "irp_deductible": True,
        },
    )
    client.post("/api/v1/invoices", json={"supplier": "Sin IVA", "total": 50_000, "issue_date": "2026-09-20"})
    rep = client.get("/api/v1/reports/fiscal", params={"month": "2026-09"}).json()
    assert (rep["iva10"], rep["taxed10"], rep["iva5"], rep["taxed5"]) == (19_182, 211_002, 1_000, 21_000)
    assert (rep["irp_total"], rep["missing_iva"], len(rep["rows"])) == (221_000, 1, 2)
    csv = client.get("/api/v1/reports/fiscal.csv", params={"month": "2026-09"}).text
    assert "80000519-8" in csv and "Sí" in csv
    z = client.get("/api/v1/reports/fiscal.zip", params={"month": "2026-09"})
    assert z.headers["content-type"] == "application/zip"
    assert zipfile.ZipFile(io.BytesIO(z.content)).namelist() == ["compras_2026-09.csv"]


def test_full_export_zip(client: TestClient) -> None:
    client.post("/api/v1/transactions", json={"amount": 10, "date": "2026-10-01", "description": "Pan"})
    z = client.get("/api/v1/export/full.zip")
    assert z.status_code == 200
    with zipfile.ZipFile(io.BytesIO(z.content)) as zf:
        assert {"datos.json", "movimientos.csv"} <= set(zf.namelist())
        data = json.loads(zf.read("datos.json"))
    assert data["transactions"][0]["description"] == "Pan"
    assert "password_hash" not in json.dumps(data)


def test_backups_listing_reads_folder(client: TestClient, tmp_path, monkeypatch) -> None:
    from app.core import config

    monkeypatch.setattr(config.get_settings(), "backups_dir", tmp_path)
    (tmp_path / "factura-db-20261021-0300.dump").write_bytes(b"x" * 10)
    (tmp_path / "otra-cosa.txt").write_text("no")
    backups = client.get("/api/v1/system/backups").json()
    assert [b["name"] for b in backups] == ["factura-db-20261021-0300.dump"]
    assert datetime.fromisoformat(backups[0]["created_at"]) <= datetime.now(UTC)


@pytest.mark.parametrize(
    "path", ["/api/v1/alerts", "/api/v1/accounts", "/api/v1/trash", "/api/v1/reports/year?year=2026"]
)
def test_new_endpoints_require_session(path: str) -> None:
    from app.main import app

    assert TestClient(app).get(path).status_code == 401


def test_new_card_shows_the_next_due_date_not_a_past_one(client: TestClient) -> None:
    from app.models import Account
    from app.services.accounts import card_cycle

    acc = Account(closing_day=25, due_day=5)
    last, nxt, due = card_cycle(acc, date(2026, 10, 21))
    assert (last, nxt, due) == (date(2026, 9, 25), date(2026, 10, 25), date(2026, 10, 5))
    assert card_cycle(acc, nxt)[2] == date(2026, 11, 5)

    card = client.post(
        "/api/v1/accounts", json={"name": "Visa", "type": "card", "closing_day": 5, "due_day": 15}
    ).json()["card"]
    assert card["statement_amount"] == 0
    assert card["next_due_date"] > date.today().isoformat()


def test_card_debt_loaded_today_goes_to_the_next_statement(client: TestClient) -> None:
    from sqlalchemy import text as sql

    from app.core.database import engine

    closing = 28 if date.today().day < 28 else 1  # siempre con un cierre anterior a hoy
    card = client.post(
        "/api/v1/accounts",
        json={"name": "Master", "type": "card", "closing_day": closing, "due_day": 2, "opening_balance": -500_000},
    ).json()
    assert card["card"]["statement_amount"] == 0  # la deuda de hoy entra en el próximo resumen
    assert card["card"]["debt"] == 500_000
    assert not [a for a in client.get("/api/v1/alerts").json() if "Master" in a["title"]]

    # Si la tarjeta se cargó antes del último cierre, esa deuda sí es del resumen cerrado.
    with engine.begin() as conn:
        conn.execute(
            sql("UPDATE accounts SET created_at = now() - interval '70 days' WHERE id = :id"), {"id": card["id"]}
        )
    again = next(a for a in client.get("/api/v1/accounts").json() if a["id"] == card["id"])
    assert again["card"]["statement_amount"] == 500_000


def test_maintenance_empties_trash_after_30_days_with_its_files(client: TestClient) -> None:
    import io

    from PIL import Image
    from sqlalchemy import text as sql

    from app.core.config import get_settings
    from app.core.database import engine
    from app.worker import run_maintenance

    buf = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(buf, "PNG")
    key = client.post("/api/v1/invoices/analyze", files={"file": ("f.png", buf.getvalue(), "image/png")}).json()[
        "file_key"
    ]
    old = client.post("/api/v1/invoices", json={"supplier": "Vieja", "total": 1000, "file_key": key}).json()
    recent = client.post("/api/v1/transactions", json={"amount": 500, "date": date.today().isoformat()}).json()
    old_trash = client.delete(f"/api/v1/invoices/{old['id']}").json()["trash_id"]
    recent_trash = client.delete(f"/api/v1/transactions/{recent['id']}").json()["trash_id"]
    with engine.begin() as conn:
        conn.execute(sql("UPDATE trash SET deleted_at = now() - interval '31 days' WHERE id = :id"), {"id": old_trash})
        conn.execute(
            sql("UPDATE trash SET deleted_at = now() - interval '29 days' WHERE id = :id"), {"id": recent_trash}
        )
    files = list(get_settings().storage_dir.glob(f"*/{key}"))
    assert files, "el archivo de la factura borrada se conserva mientras está en la papelera"

    run_maintenance()

    left = [i["id"] for i in client.get("/api/v1/trash").json()]
    assert left == [recent_trash]  # la de 31 días se fue, la de 29 sigue
    assert not files[0].exists()  # y con ella su archivo
    assert client.post(f"/api/v1/trash/{recent_trash}/restore").status_code == 200
