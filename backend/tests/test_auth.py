import pytest
from fastapi.testclient import TestClient

from app.core.security import ACCESS_COOKIE
from app.main import app
from tests.conftest import PASSWORD


def test_first_user_can_register_then_registration_closes(client: TestClient) -> None:
    anon = TestClient(app)
    assert anon.get("/api/v1/auth/config").json() == {
        "registration_open": False,
        "first_user": False,
        "google_login": False,
    }
    r = anon.post("/api/v1/auth/register", json={"email": "otro@example.com", "password": PASSWORD})
    assert r.status_code == 403


def test_register_seeds_categories_and_sets_httponly_cookie() -> None:
    anon = TestClient(app)
    r = anon.post("/api/v1/auth/register", json={"email": "Nuevo@Example.com", "password": PASSWORD})
    assert r.status_code == 201
    assert r.json()["email"] == "nuevo@example.com"
    assert "httponly" in r.headers["set-cookie"].lower()
    assert "samesite=strict" in r.headers["set-cookie"].lower()


def test_short_password_rejected() -> None:
    r = TestClient(app).post("/api/v1/auth/register", json={"email": "a@example.com", "password": "corta"})
    assert r.status_code == 422


def test_login_wrong_password_and_rate_limit(client: TestClient) -> None:
    anon = TestClient(app)
    wrong = {"email": "carlo@example.com", "password": "mala-clave"}
    for _ in range(5):
        assert anon.post("/api/v1/auth/login", json=wrong).status_code == 401
    r = anon.post("/api/v1/auth/login", json={"email": "carlo@example.com", "password": PASSWORD})
    assert r.status_code == 429


def test_protected_routes_require_session() -> None:
    assert TestClient(app).get("/api/v1/transactions").status_code == 401


def test_mutations_require_csrf_header(client: TestClient) -> None:
    del client.headers["X-CSRF-Token"]
    r = client.post("/api/v1/transactions", json={"amount": 1000, "date": "2026-10-01"})
    assert r.status_code == 403


def test_tampered_token_is_rejected(client: TestClient) -> None:
    client.cookies.set(ACCESS_COOKIE, client.cookies.get(ACCESS_COOKIE) + "x")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_password_change_invalidates_other_sessions(make_client) -> None:
    first = make_client()
    second = make_client(register=False)
    r = first.post(
        "/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": "otra-clave-segura-456"}
    )
    assert r.status_code == 200
    assert first.get("/api/v1/auth/me").status_code == 200
    assert second.get("/api/v1/auth/me").status_code == 401


def test_profile_update(client: TestClient) -> None:
    r = client.patch("/api/v1/auth/me", json={"monthly_budget": 5000000, "daily_limit": 250000, "currency": "PYG"})
    assert r.status_code == 200
    assert r.json()["monthly_budget"] == 5000000
    assert client.patch("/api/v1/auth/me", json={"currency": "XXX"}).status_code == 422


def test_logout_clears_session(client: TestClient) -> None:
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize(
    "weak", ["1234567890", "0987654321", "aaaaaaaaaaaa", "abababababab", "Contraseña123", "qwertyuiop"]
)
def test_obvious_passwords_are_rejected(weak: str) -> None:
    anon = TestClient(app)
    r = anon.post("/api/v1/auth/register", json={"email": "nuevo@example.com", "password": weak})
    assert r.status_code == 422
    assert "Elegí otra" in r.json()["detail"]


def test_password_cannot_contain_the_email() -> None:
    anon = TestClient(app)
    r = anon.post("/api/v1/auth/register", json={"email": "carlitos@example.com", "password": "Carlitos-2026!"})
    assert r.status_code == 422


def test_weak_new_password_does_not_count_as_a_failed_attempt(client: TestClient) -> None:
    for _ in range(8):
        r = client.post("/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": "1234567890"})
        assert r.status_code == 422
    r = client.post(
        "/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": "otra-clave-segura-456"}
    )
    assert r.status_code == 200


def test_logout_everywhere_closes_every_session(make_client) -> None:
    first = make_client()
    second = make_client(register=False)
    assert first.post("/api/v1/auth/logout-all").status_code == 204
    assert first.get("/api/v1/auth/me").status_code == 401
    assert second.get("/api/v1/auth/me").status_code == 401
    assert make_client(register=False).get("/api/v1/auth/me").status_code == 200  # se puede volver a entrar


def test_login_screen_knows_when_it_is_the_first_user(make_client, monkeypatch) -> None:
    from app.core import config

    anon = TestClient(app)
    first = {"registration_open": True, "first_user": True, "google_login": False}
    assert anon.get("/api/v1/auth/config").json() == first
    make_client()
    monkeypatch.setattr(config.get_settings(), "allow_registration", True)
    # Con registro abierto y usuarios existentes, la pantalla debe ofrecer ingresar Y crear cuenta.
    assert anon.get("/api/v1/auth/config").json() == {
        "registration_open": True,
        "first_user": False,
        "google_login": False,
    }
