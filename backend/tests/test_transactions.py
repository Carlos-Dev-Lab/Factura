from fastapi.testclient import TestClient


def test_crud_and_filters(client: TestClient, expense_category: dict) -> None:
    body = {"amount": 212500, "date": "2026-10-21", "category_id": expense_category["id"], "description": "Luz"}
    created = client.post("/api/v1/transactions", json=body)
    assert created.status_code == 201
    tx = created.json()
    assert tx["category"]["name"] == "Servicios"
    assert tx["amount"] == 212500

    client.post("/api/v1/transactions", json={"kind": "income", "amount": 9500000, "date": "2026-10-01"})
    page = client.get("/api/v1/transactions", params={"start": "2026-10-01", "end": "2026-10-31", "kind": "expense"})
    assert page.json()["total"] == 1
    assert client.get("/api/v1/transactions", params={"q": "servic"}).json()["total"] == 1

    r = client.patch(f"/api/v1/transactions/{tx['id']}", json={"amount": 100000})
    assert r.json()["amount"] == 100000
    deleted = client.delete(f"/api/v1/transactions/{tx['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["trash_id"] > 0
    assert client.get("/api/v1/transactions").json()["total"] == 1


def test_rejects_invalid_amount_and_wrong_category_kind(client: TestClient, expense_category: dict) -> None:
    assert client.post("/api/v1/transactions", json={"amount": 0, "date": "2026-10-01"}).status_code == 422
    r = client.post(
        "/api/v1/transactions",
        json={"kind": "income", "amount": 10, "date": "2026-10-01", "category_id": expense_category["id"]},
    )
    assert r.status_code == 422


def test_users_are_isolated(make_client, monkeypatch) -> None:
    from app.core import config

    owner = make_client()
    tx = owner.post("/api/v1/transactions", json={"amount": 5000, "date": "2026-10-01"}).json()
    monkeypatch.setattr(config.get_settings(), "allow_registration", True)
    intruder = make_client("intruso@example.com")

    assert intruder.get("/api/v1/transactions").json()["total"] == 0
    assert intruder.patch(f"/api/v1/transactions/{tx['id']}", json={"amount": 1}).status_code == 404
    assert intruder.delete(f"/api/v1/transactions/{tx['id']}").status_code == 404
    foreign_cat = owner.get("/api/v1/categories").json()[0]["id"]
    r = intruder.post("/api/v1/transactions", json={"amount": 1, "date": "2026-10-01", "category_id": foreign_cat})
    assert r.status_code == 404


def test_duplicate_category_conflict(client: TestClient) -> None:
    r = client.post("/api/v1/categories", json={"name": "Servicios", "kind": "expense"})
    assert r.status_code == 409
    r = client.post("/api/v1/categories", json={"name": "Mascotas", "color": "#112233"})
    assert r.status_code == 201
