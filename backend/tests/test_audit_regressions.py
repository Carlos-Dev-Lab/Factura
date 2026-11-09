from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.services.dates import add_months


def test_future_activity_does_not_change_todays_balances_or_card_statement(client: TestClient) -> None:
    today = date.today()
    first = today.replace(day=1)
    tomorrow = (today + timedelta(days=1)).isoformat()
    cash = client.get("/api/v1/accounts").json()[0]["id"]
    card = client.post(
        "/api/v1/accounts",
        json={"name": "Tarjeta", "type": "card", "closing_day": 1, "due_day": 20, "credit_limit": 2000},
    ).json()["id"]
    for data in (
        {"kind": "income", "amount": 1000, "date": today.isoformat(), "account_id": cash},
        {"kind": "income", "amount": 200, "date": tomorrow, "account_id": cash},
        {"amount": 400, "date": first.isoformat(), "account_id": card},
    ):
        assert client.post("/api/v1/transactions", json=data).status_code == 201
    assert client.post(
        "/api/v1/accounts/transfers",
        json={"from_account_id": cash, "to_account_id": card, "amount": 400, "date": tomorrow},
    ).status_code == 201
    accounts = {a["id"]: a for a in client.get("/api/v1/accounts").json()}
    assert accounts[cash]["balance"] == 1000
    assert accounts[cash]["movement_count"] == 3
    assert accounts[card]["card"]["statement_amount"] == 400
    summary = client.get("/api/v1/reports/summary", params={"month": first.strftime("%Y-%m")}).json()
    assert summary["due_total"] == 400
    assert summary["projection"]["card_payments"] == 400
    assert summary["projection"]["pending_expense"] == 0
    assert summary["projection"]["projected_balance"] == summary["balance"]


def test_late_installment_is_due_until_paid_in_the_actual_month(client: TestClient) -> None:
    today = date.today()
    first = today.replace(day=1)
    prior = add_months(first, -1).strftime("%Y-%m")
    current = first.strftime("%Y-%m")
    plan = client.post(
        "/api/v1/scheduled-payments",
        json={"name": "Cuota anterior", "start_month": prior, "end_month": prior, "amount": 80, "day_of_month": 5},
    ).json()
    pay_url = f"/api/v1/scheduled-payments/{plan['id']}/pay"
    summary_url = f"/api/v1/reports/summary?month={current}"
    assert client.get(summary_url).json()["due_total"] == 80
    assert len(client.get("/api/v1/alerts").json()) == 1
    payment = client.post(pay_url, json={"month": prior, "paid_on": today.isoformat()}).json()
    assert payment["date"] == today.isoformat()
    assert client.post(pay_url, json={"month": prior, "paid_on": today.isoformat()}).json()["id"] == payment["id"]
    assert client.get(summary_url).json()["due_total"] == 0
    assert client.get(summary_url).json()["expense"] == 80
    calendar = client.get(f"/api/v1/reports/calendar?month={prior}").json()
    assert calendar["days"][4]["dues"][0]["state"] == "paid"
    assert calendar["days"][4]["expense"] == 0
    trash_id = client.delete(f"/api/v1/transactions/{payment['id']}").json()["trash_id"]
    assert client.get(summary_url).json()["due_total"] == 80
    assert client.post(f"/api/v1/trash/{trash_id}/restore").status_code == 200
    assert client.get(summary_url).json()["due_total"] == 0


def test_convert_expense_links_original_without_changing_balance(client: TestClient, expense_category: dict) -> None:
    today = date.today()
    first = today.replace(day=1)
    current = first.strftime("%Y-%m")
    next_month = add_months(first, 1).strftime("%Y-%m")
    movements_url = "/api/v1/transactions"
    plans_url = "/api/v1/scheduled-payments"
    account = client.get("/api/v1/accounts").json()[0]["id"]
    expense = client.post(movements_url, json={
        "date": today.isoformat(), "description": "Servicio mensual", "amount": 80, "method": "debit",
        "account_id": account, "category_id": expense_category["id"],
    }).json()
    before = client.get("/api/v1/accounts").json()
    convert_url = f"{movements_url}/{expense['id']}/schedule"
    config = {
        "name": "Servicio", "amount": 100, "day_of_month": 5,
        "account_id": account, "category_id": expense_category["id"],
    }
    result = client.post(convert_url, json=config)
    assert result.status_code == 201, result.text
    plan = result.json()
    assert plan["start_month"] == current
    assert plan["amount"] == 100
    assert client.post(convert_url, json=config).status_code == 409
    assert client.get(plans_url).json() == [plan]
    linked = expense | {"scheduled_payment_id": plan["id"]}
    assert client.get(movements_url).json()["items"] == [linked]
    assert client.get("/api/v1/accounts").json() == before

    calendar = client.get(f"/api/v1/reports/calendar?month={current}").json()
    due = calendar["days"][4]["dues"][0]
    assert (due["state"], due["amount"]) == ("paid", 80)
    calendar = client.get(f"/api/v1/reports/calendar?month={next_month}").json()
    due = calendar["days"][4]["dues"][0]
    assert (due["state"], due["amount"]) == ("pending", 100)
    plan_url = f"{plans_url}/{plan['id']}"
    assert client.get(f"{plan_url}/history").json()["items"][0]["transaction_id"] == expense["id"]
    assert client.post(f"{plan_url}/pay", json={"month": current}).json() == linked
    assert client.delete(plan_url).status_code == 200
    assert client.get(movements_url).json()["items"] == [expense]


def test_convert_old_expense_does_not_create_past_due_installments(client: TestClient) -> None:
    first = date.today().replace(day=1)
    old = add_months(first, -3)
    expense = client.post("/api/v1/transactions", json={"date": old.isoformat(), "amount": 20}).json()
    url = f"/api/v1/transactions/{expense['id']}/schedule"
    config = {"name": "Servicio", "amount": 20, "day_of_month": 1}
    assert client.post(url, json=config | {"start_month": old.strftime("%Y-%m")}).status_code == 422
    assert client.get("/api/v1/scheduled-payments").json() == []
    plan = client.post(url, json=config).json()
    assert plan["start_month"] == first.strftime("%Y-%m")
    summary = client.get(f"/api/v1/reports/summary?month={plan['start_month']}").json()
    assert summary["due_total"] == 20


def test_invalid_tax_total_cannot_enter_through_invoice_or_linked_expense(client: TestClient) -> None:
    base = {"supplier": "Factura de prueba", "total": 100, "iva10": 50}
    assert client.post("/api/v1/invoices", json=base).status_code == 422
    saved = client.post("/api/v1/invoices", json=base | {"total": 550, "already_paid": True})
    assert saved.status_code == 201
    payment = client.get("/api/v1/transactions").json()["items"][0]
    config = {"name": "Factura", "amount": 550, "day_of_month": 10}
    assert client.post(f"/api/v1/transactions/{payment['id']}/schedule", json=config).status_code == 409
    assert client.patch(f"/api/v1/transactions/{payment['id']}", json={"amount": 40}).status_code == 422
    assert client.get("/api/v1/transactions").json()["expense_total"] == 550
    assert client.get("/api/v1/invoices").json()[0]["total"] == 550


def test_import_scope_retries_and_row_limit(client: TestClient) -> None:
    day = date.today().isoformat()
    bank = client.post("/api/v1/accounts", json={"name": "Banco", "type": "bank"}).json()["id"]
    cash = client.get("/api/v1/accounts").json()[0]["id"]
    tx = {"date": day, "description": "Comercio A", "amount": 123, "account_id": cash}
    assert client.post("/api/v1/transactions", json=tx).status_code == 201
    csv = f"Fecha;Concepto;Importe\n{day};Comercio A;-123\n{day};Comercio B;-123\n"
    for account, expected in ((cash, [True, False]), (bank, [False, False])):
        preview = client.post("/api/v1/imports/preview", data={"account_id": str(account)}, files={"file": ("b.csv", csv)})
        assert [row["duplicate"] for row in preview.json()["rows"]] == expected
    items = [{"date": day, "description": "Comercio B", "amount": 123, "kind": "expense"}]
    batch = {"account_id": bank, "items": items}
    assert client.post("/api/v1/imports/commit", json=batch).json()["created"] == 1
    assert client.post("/api/v1/imports/commit", json=batch).json()["created"] == 0
    assert client.get("/api/v1/transactions").json()["total"] == 2
    long_csv = "Fecha;Concepto;Importe\n" + f"{day};Compra;-123\n" * 2001
    rejected = client.post("/api/v1/imports/preview", files={"file": ("b.csv", long_csv)})
    assert rejected.status_code == 422 and "2000" in rejected.json()["detail"]


def test_category_average_uses_same_months_as_overall_average(client: TestClient) -> None:
    today = date.today()
    year = today.year if today.month < 12 else today.year + 1
    current = today.replace(year=year, day=1)
    if today.month == 12:
        current = current.replace(month=1)
    future = add_months(current, 1)
    for when, amount in ((current, 100), (future, 700)):
        assert client.post("/api/v1/transactions", json={"date": when.isoformat(), "amount": amount}).status_code == 201
    report = client.get(f"/api/v1/reports/year?year={year}").json()
    assert report["expense"] == 800
    assert report["categories"][0]["average_expense"] == report["average_expense"]
    assert report["average_expense"] == (100 if year == today.year else 0)
