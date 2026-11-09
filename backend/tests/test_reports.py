from datetime import date

from fastapi.testclient import TestClient


def test_scheduled_payment_is_idempotent_and_shown_in_calendar(client: TestClient) -> None:
    body = {"name": "Alquiler", "amount": 2800000, "day_of_month": 31, "start_month": "2026-01"}
    sp = client.post("/api/v1/scheduled-payments", json=body).json()
    r = client.post(f"/api/v1/scheduled-payments/{sp['id']}/pay", json={"month": "2026-02"})
    assert r.json()["date"] == "2026-02-28"  # día 31 ajustado a febrero
    client.post(f"/api/v1/scheduled-payments/{sp['id']}/pay", json={"month": "2026-02"})
    assert client.get("/api/v1/transactions").json()["total"] == 1

    bad = client.post(f"/api/v1/scheduled-payments/{sp['id']}/pay", json={"month": "2026-03", "paid_on": "2026-02-27"})
    assert bad.status_code == 422

    cal = client.get("/api/v1/reports/calendar", params={"month": "2026-02"}).json()
    last = cal["days"][-1]
    assert last["date"] == "2026-02-28"
    assert last["dues"][0]["state"] == "paid"
    assert last["expense"] == 2800000


def test_summary_totals(client: TestClient, expense_category: dict) -> None:
    month = date.today().strftime("%Y-%m")
    today = date.today().isoformat()
    client.patch("/api/v1/auth/me", json={"monthly_budget": 1000000, "daily_limit": 100000})
    client.post("/api/v1/transactions", json={"kind": "income", "amount": 900000, "date": today})
    client.post("/api/v1/transactions", json={"amount": 250000, "date": today, "category_id": expense_category["id"]})
    client.post("/api/v1/invoices", json={"supplier": "ANDE", "total": 385000, "due_date": today})

    s = client.get("/api/v1/reports/summary", params={"month": month}).json()
    assert s["income"] == 900000
    assert s["expense"] == 250000
    assert s["balance"] == 650000
    assert s["budget_used_pct"] == 25.0
    assert s["today_expense"] == 250000
    assert s["due_total"] == 385000
    assert s["by_category"][0]["name"] == "Servicios"
    assert len(s["daily"]) >= 28


def test_invalid_month_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/reports/summary", params={"month": "2026-13"}).status_code == 422


def test_csv_export_neutralizes_formulas(client: TestClient) -> None:
    client.post("/api/v1/transactions", json={"amount": 1000, "date": "2026-10-01", "description": "=HYPERLINK(1)"})
    r = client.get("/api/v1/reports/export.csv", params={"month": "2026-10"})
    assert r.status_code == 200
    assert "'=HYPERLINK(1)" in r.text


def test_category_filter_reconciles_summary_calendar_reports_and_exports(client: TestClient) -> None:
    today = date.today()
    month = today.strftime("%Y-%m")
    categories = client.get("/api/v1/categories").json()
    selected = next(c["id"] for c in categories if c["name"] == "Servicios")
    other = next(c["id"] for c in categories if c["name"] == "Supermercado")
    client.patch("/api/v1/auth/me", json={"monthly_budget": 1000, "daily_limit": 50})
    client.patch(f"/api/v1/categories/{selected}", json={"monthly_budget": 200})
    for category, title, amount in ((selected, "Servicio filtrado", 100), (other, "Compra excluida", 300)):
        tx = {"amount": amount, "date": today.isoformat(), "category_id": category, "description": title}
        assert client.post("/api/v1/transactions", json=tx).status_code == 201
        invoice = {"total": amount, "issue_date": today.isoformat(), "due_date": today.isoformat(),
                   "category_id": category, "supplier": title}
        assert client.post("/api/v1/invoices", json=invoice).status_code == 201

    scope = {"category_id": selected}
    params = {"month": month, **scope}
    summary = client.get("/api/v1/reports/summary", params=params).json()
    assert (summary["expense"], summary["today_expense"], summary["due_total"]) == (100, 100, 100)
    assert (summary["budget"], summary["budget_used_pct"], summary["daily_limit"]) == (200, 50, 0)
    assert summary["daily"][today.day - 1]["expense"] == 100
    assert [item["category_id"] for item in summary["by_category"]] == [selected]
    assert client.get("/api/v1/reports/summary", params={"month": month}).json()["expense"] == 400
    calendar = client.get("/api/v1/reports/calendar", params=params).json()["days"][today.day - 1]
    assert calendar["expense"] == 100 and [due["name"] for due in calendar["dues"]] == ["Servicio filtrado"]
    annual = client.get("/api/v1/reports/year", params={"year": today.year, **scope}).json()
    assert annual["expense"] == annual["months"][today.month - 1]["expense"] == 100
    assert client.get("/api/v1/reports/expenses/yearly", params=scope).json() == [{"year": today.year, "expense": 100}]
    assert client.get("/api/v1/reports/fiscal", params=params).json()["total"] == 100
    assert [item["supplier"] for item in client.get("/api/v1/invoices", params=scope).json()] == ["Servicio filtrado"]
    for path in ("/api/v1/reports/fiscal.csv", "/api/v1/reports/export.csv"):
        csv = client.get(path, params=params).text
        assert "Servicio filtrado" in csv and "Compra excluida" not in csv
