"""Validación de datos raros y pedidos simultáneos (revisión de octubre de 2026).

Cada prueba reproduce un caso que antes terminaba en error 500 o en datos duplicados.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import app

TODAY = date.today()
MONTH = TODAY.strftime("%Y-%m")


def _same_session(client: TestClient) -> TestClient:
    """Otro cliente con la misma sesión, para mandar pedidos en paralelo desde varios hilos."""
    twin = TestClient(app)
    twin.cookies = client.cookies
    twin.headers.update(client.headers)
    return twin


def _parallel(client: TestClient, times: int, call) -> list[int]:
    clients = [_same_session(client) for _ in range(times)]
    with ThreadPoolExecutor(times) as pool:
        return [r.status_code for r in pool.map(call, clients)]


# ---------- Textos ----------


def test_invisible_control_characters_are_removed(client: TestClient) -> None:
    r = client.post(
        "/api/v1/transactions", json={"amount": 1000, "date": TODAY.isoformat(), "description": "Café\x00\x07 ok"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["description"] == "Café ok"


def test_name_made_only_of_control_characters_is_rejected(client: TestClient) -> None:
    r = client.post("/api/v1/categories", json={"name": "\x00\x01"})
    assert r.status_code == 422


def test_control_characters_in_search_do_not_break_the_api(client: TestClient) -> None:
    r = client.get("/api/v1/transactions", params={"q": "a\x00b"})
    assert r.status_code in (200, 422)


# ---------- Meses y fechas ----------


@pytest.mark.parametrize("month", ["٢٠٢٦-10", "２０２６-10", "2026-10\n", " 2026-10"])
def test_month_only_accepts_plain_digits(client: TestClient, month: str) -> None:
    assert client.get("/api/v1/reports/export.csv", params={"month": month}).status_code == 422
    assert client.get("/api/v1/reports/summary", params={"month": month}).status_code == 422


@pytest.mark.parametrize("day", ["0001-01-01", "1899-12-31", "3000-01-01", "9999-12-31"])
def test_dates_outside_the_supported_range_are_rejected(client: TestClient, day: str) -> None:
    r = client.post("/api/v1/transactions", json={"amount": 1000, "date": day})
    assert r.status_code == 422
    assert "1900" in r.text


def test_cdc_only_accepts_plain_digits(client: TestClient) -> None:
    r = client.post("/api/v1/invoices", json={"total": 1000, "cdc": "٠" * 44})
    assert r.status_code == 422


# ---------- Números ----------


def test_sums_larger_than_one_amount_do_not_break_reports(client: TestClient) -> None:
    for _ in range(12):
        r = client.post("/api/v1/transactions", json={"amount": 999_999_999_999, "date": TODAY.isoformat()})
        assert r.status_code == 201
    for path, params in [
        ("/api/v1/transactions", {"limit": 1}),
        ("/api/v1/reports/summary", {"month": MONTH}),
        ("/api/v1/reports/calendar", {"month": MONTH}),
        ("/api/v1/reports/year", {"year": TODAY.year}),
    ]:
        assert client.get(path, params=params).status_code == 200, path
    assert client.get("/api/v1/transactions", params={"limit": 1}).json()["expense_total"] == 11_999_999_999_988


def test_card_overspent_beyond_its_limit_still_lists(client: TestClient) -> None:
    card = client.post(
        "/api/v1/accounts",
        json={"name": "Visa", "type": "card", "closing_day": 5, "due_day": 15, "credit_limit": 100_000},
    ).json()
    client.post(
        "/api/v1/transactions", json={"amount": 999_999_999_999, "date": TODAY.isoformat(), "account_id": card["id"]}
    )
    r = client.get("/api/v1/accounts")
    assert r.status_code == 200
    assert next(a for a in r.json() if a["id"] == card["id"])["card"]["available"] == 0


@pytest.mark.parametrize("bad_id", [0, -1, 2**31, 2**70])
def test_out_of_range_ids_are_rejected_not_500(client: TestClient, bad_id: int) -> None:
    assert client.patch(f"/api/v1/transactions/{bad_id}", json={"amount": 5}).status_code == 422
    assert client.delete(f"/api/v1/invoices/{bad_id}").status_code == 422
    r = client.post("/api/v1/transactions", json={"amount": 1000, "date": TODAY.isoformat(), "category_id": bad_id})
    assert r.status_code == 422


def test_out_of_range_id_in_a_filter_is_not_500(client: TestClient) -> None:
    assert client.get("/api/v1/transactions", params={"account_id": 2**40}).status_code == 422


# ---------- Pedidos simultáneos ----------


def test_paying_a_scheduled_payment_many_times_at_once_records_it_once(client: TestClient) -> None:
    sp = client.post(
        "/api/v1/scheduled-payments",
        json={"name": "Internet", "amount": 150_000, "day_of_month": 5, "start_month": MONTH},
    ).json()
    codes = _parallel(client, 8, lambda c: c.post(f"/api/v1/scheduled-payments/{sp['id']}/pay", json={"month": MONTH}))
    assert codes == [200] * 8
    assert client.get("/api/v1/transactions", params={"q": "Internet"}).json()["total"] == 1


def test_paying_an_invoice_many_times_at_once_records_it_once(client: TestClient) -> None:
    inv = client.post("/api/v1/invoices", json={"supplier": "ANDE", "total": 50_000}).json()
    codes = _parallel(client, 8, lambda c: c.post(f"/api/v1/invoices/{inv['id']}/pay", json={}))
    assert codes == [200] * 8
    assert client.get("/api/v1/transactions", params={"q": "ANDE"}).json()["total"] == 1


def test_restoring_the_same_item_twice_at_once(client: TestClient) -> None:
    tx = client.post(
        "/api/v1/transactions", json={"amount": 7000, "date": TODAY.isoformat(), "description": "x"}
    ).json()
    trash_id = client.delete(f"/api/v1/transactions/{tx['id']}").json()["trash_id"]
    codes = _parallel(client, 6, lambda c: c.post(f"/api/v1/trash/{trash_id}/restore"))
    assert sorted(codes) == [200] + [404] * 5
    assert client.get("/api/v1/transactions").json()["total"] == 1


def test_deleting_the_same_movement_twice_at_once(client: TestClient) -> None:
    tx = client.post("/api/v1/transactions", json={"amount": 7000, "date": TODAY.isoformat()}).json()
    codes = _parallel(client, 6, lambda c: c.delete(f"/api/v1/transactions/{tx['id']}"))
    assert sorted(codes) == [200] + [404] * 5
    assert len(client.get("/api/v1/trash").json()) == 1


# ---------- Planillas ----------


def test_fiscal_csv_neutralizes_formulas_in_every_text_column(client: TestClient) -> None:
    client.post(
        "/api/v1/invoices",
        json={
            "supplier": "Prov",
            "ruc": "=1+1",
            "stamp": "+2",
            "number": "@SUM(A1)",
            "total": 10_000,
            "issue_date": TODAY.isoformat(),
        },
    )
    row = next(
        ln for ln in client.get("/api/v1/reports/fiscal.csv", params={"month": MONTH}).text.splitlines() if "1+1" in ln
    )
    cells = row.split(";")
    assert cells[1] == "'=1+1" and cells[3] == "'+2" and cells[4] == "'@SUM(A1)"


def test_import_ignores_absurd_dates_and_extra_columns(client: TestClient) -> None:
    wide = ";".join(f"c{i}" for i in range(500))
    content = f"Fecha;Concepto;Monto;{wide}\n01/01/0001;Viejo;-5000;\n15/10/2026;Bueno\x00;-7000;\n".encode()
    r = client.post("/api/v1/imports/preview", files={"file": ("e.csv", content, "text/csv")})
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["columns"]) <= 60
    old, good = data["rows"]
    assert old["date"] is None and old["error"]
    assert good["description"] == "Bueno"


# ---------- Nombres repetidos y restauraciones que duplicarían ----------


def test_names_are_unique_ignoring_case(client: TestClient) -> None:
    pets = client.post("/api/v1/categories", json={"name": "Mascotas"}).json()
    assert client.post("/api/v1/categories", json={"name": "mascotas "}).status_code == 409
    other = client.post("/api/v1/categories", json={"name": "Regalos"}).json()
    assert client.patch(f"/api/v1/categories/{other['id']}", json={"name": "MASCOTAS"}).status_code == 409
    assert client.patch(f"/api/v1/categories/{pets['id']}", json={"name": "mascotas"}).status_code == 200  # la misma
    client.post("/api/v1/accounts", json={"name": "Banco", "type": "bank"})
    assert client.post("/api/v1/accounts", json={"name": "banco", "type": "bank"}).status_code == 409


def test_restoring_a_category_clashes_ignoring_case(client: TestClient) -> None:
    cat = client.post("/api/v1/categories", json={"name": "Viajes"}).json()
    trash_id = client.delete(f"/api/v1/categories/{cat['id']}").json()["trash_id"]
    client.post("/api/v1/categories", json={"name": "viajes"})
    assert client.post(f"/api/v1/trash/{trash_id}/restore").status_code == 409


def test_restoring_an_old_invoice_payment_after_paying_again_does_not_duplicate(client: TestClient) -> None:
    inv = client.post("/api/v1/invoices", json={"supplier": "ANDE", "total": 90_000}).json()
    client.post(f"/api/v1/invoices/{inv['id']}/pay", json={})
    old = next(t for t in client.get("/api/v1/transactions").json()["items"] if t["invoice_id"] == inv["id"])
    trash_id = client.delete(f"/api/v1/transactions/{old['id']}").json()["trash_id"]
    client.post(f"/api/v1/invoices/{inv['id']}/pay", json={})
    r = client.post(f"/api/v1/trash/{trash_id}/restore")
    assert r.status_code == 409 and "duplicaría" in r.json()["detail"]
    assert client.get("/api/v1/transactions").json()["total"] == 1


def test_restoring_an_old_scheduled_payment_after_paying_again_does_not_duplicate(client: TestClient) -> None:
    sp = client.post(
        "/api/v1/scheduled-payments",
        json={"name": "Internet", "amount": 150_000, "day_of_month": 5, "start_month": MONTH},
    ).json()
    old = client.post(f"/api/v1/scheduled-payments/{sp['id']}/pay", json={"month": MONTH}).json()
    trash_id = client.delete(f"/api/v1/transactions/{old['id']}").json()["trash_id"]
    client.post(f"/api/v1/scheduled-payments/{sp['id']}/pay", json={"month": MONTH})
    r = client.post(f"/api/v1/trash/{trash_id}/restore")
    assert r.status_code == 409 and "Internet" in r.json()["detail"]
    assert client.get("/api/v1/transactions").json()["total"] == 1


def test_import_marks_only_as_many_duplicates_as_already_loaded(client: TestClient) -> None:
    day = TODAY.strftime("%d/%m/%Y")
    client.post("/api/v1/transactions", json={"amount": 95_000, "date": TODAY.isoformat(), "description": "Nafta"})
    content = f"Fecha;Concepto;Débito\n{day};COMPRA A;95.000\n{day};COMPRA B;95.000\n".encode()
    rows = client.post("/api/v1/imports/preview", files={"file": ("e.csv", content, "text/csv")}).json()["rows"]
    assert [r["duplicate"] for r in rows] == [True, False]


# ---------- Mensajes de validación en español ----------


def test_validation_errors_are_in_spanish_and_do_not_echo_the_input() -> None:
    anon = TestClient(app)
    r = anon.post("/api/v1/auth/register", json={"email": "x@example.com", "password": "corta-123"})
    assert r.status_code == 422
    assert r.json()["detail"][0]["msg"] == "Contraseña: tiene que tener al menos 10 caracteres"
    assert "corta-123" not in r.text and "input" not in r.json()["detail"][0]
    r = anon.post("/api/v1/auth/login", json={"email": "sin-arroba", "password": "x"})
    assert r.json()["detail"][0]["msg"].startswith("Email: no es un email válido")
    r = anon.post("/api/v1/auth/register", json={"email": "a" * 250 + "@x.com", "password": "Clave-larga-2026"})
    assert r.status_code == 422


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"date": "2026-10-01"}, "Monto: es obligatorio"),
        ({"amount": 0, "date": "2026-10-01"}, "Monto: tiene que ser mayor a cero"),
        ({"amount": 10.555, "date": "2026-10-01"}, "Monto: admite hasta 2 decimales"),
        ({"amount": 10, "date": "21/10/2026"}, "Fecha: no es una fecha válida (usá AAAA-MM-DD)"),
        ({"amount": 10, "date": "1800-01-01"}, "Fecha: La fecha debe estar entre los años 1900 y 2999"),
        ({"amount": 10, "date": "2026-10-01", "kind": "regalo"}, "Tipo: no es una opción válida"),
        ({"amount": "mucho", "date": "2026-10-01"}, "Monto: tiene que ser un número"),
    ],
)
def test_each_field_error_names_the_field(client: TestClient, body: dict, message: str) -> None:
    r = client.post("/api/v1/transactions", json=body)
    assert r.status_code == 422
    assert r.json()["detail"][0]["msg"] == message


def test_broken_json_gets_a_clear_message(client: TestClient) -> None:
    r = client.post("/api/v1/transactions", content="{nada", headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and r.json()["detail"][0]["msg"] == "Los datos enviados no son válidos"
