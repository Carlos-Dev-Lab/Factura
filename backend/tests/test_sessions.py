"""Sesiones y bloqueos: dispositivos de confianza, cierre de sesión que revoca el token y límites del registro.

Detrás de Docker Desktop o de `tailscale serve` todos los pedidos llegan con la misma IP (en
producción la pone nginx en X-Real-IP). Estos tests la simulan con ese header.
"""

import time

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core import config
from app.core.security import ACCESS_COOKIE, ALGORITHM, DEVICE_AUDIENCE, DEVICE_COOKIE
from app.main import app
from tests.conftest import PASSWORD

LOGIN = "/api/v1/auth/login"
SHARED_IP = {"X-Real-IP": "10.213.47.1"}
OWNER = "carlo@example.com"
RIGHT = {"email": OWNER, "password": PASSWORD}
WRONG = {"email": OWNER, "password": "no-es-la-clave"}


def device(*, logged_in: bool = True) -> TestClient:
    """Un navegador que llega con la IP compartida; si `logged_in`, ya entró bien (es de confianza)."""
    c = TestClient(app, headers=SHARED_IP)
    if logged_in:
        assert c.post(LOGIN, json=RIGHT).status_code == 200
        assert c.cookies.get(DEVICE_COOKIE)
    return c


def lock_out_owner() -> TestClient:
    """Un intruso en la misma red se equivoca a propósito con el email del dueño hasta bloquearlo."""
    intruder = device(logged_in=False)
    for _ in range(config.get_settings().login_max_attempts):
        assert intruder.post(LOGIN, json=WRONG).status_code == 401
    return intruder


# ---------- Bloqueo del ingreso con IP compartida ----------


def test_intruder_cannot_lock_the_owner_out_of_a_trusted_device(client: TestClient) -> None:
    owner = device()
    intruder = lock_out_owner()
    # El intruso, y cualquier dispositivo nuevo, quedan frenados aunque prueben la clave correcta...
    assert intruder.post(LOGIN, json=RIGHT).status_code == 429
    assert device(logged_in=False).post(LOGIN, json=RIGHT).status_code == 429
    # ...pero el dueño sigue entrando desde donde ya había entrado, con la misma IP.
    assert owner.post(LOGIN, json=RIGHT).status_code == 200


def test_a_trusted_device_still_has_its_own_attempt_limit(client: TestClient) -> None:
    owner = device()
    for _ in range(config.get_settings().login_max_attempts):
        assert owner.post(LOGIN, json=WRONG).status_code == 401
    assert owner.post(LOGIN, json=RIGHT).status_code == 429


def test_forged_or_foreign_device_cookies_are_not_trusted(client: TestClient) -> None:
    intruder = lock_out_owner()
    now = int(time.time())
    claims = {"did": "d" * 22, "email": OWNER, "sv": 0, "aud": DEVICE_AUDIENCE, "iat": now, "exp": now + 3600}
    forged = jwt.encode(claims, "otra-clave-que-no-es-la-del-servidor-0123456789", algorithm=ALGORITHM)
    for value in ("inventada", forged):
        intruder.cookies.set(DEVICE_COOKIE, value)
        assert intruder.post(LOGIN, json=RIGHT).status_code == 429, value


def test_device_cookie_of_another_email_is_not_trusted(make_client, monkeypatch) -> None:
    make_client()
    monkeypatch.setattr(config.get_settings(), "allow_registration", True)
    other = TestClient(app, headers=SHARED_IP)
    r = other.post("/api/v1/auth/register", json={"email": "otra@example.com", "password": PASSWORD})
    assert r.status_code == 201 and other.cookies.get(DEVICE_COOKIE)
    lock_out_owner()
    # Es de confianza para otra@example.com, no para el dueño.
    assert other.post(LOGIN, json=RIGHT).status_code == 429


def test_closing_all_sessions_also_drops_device_trust(client: TestClient) -> None:
    lost_phone = device()
    assert client.post("/api/v1/auth/logout-all").status_code == 204
    lock_out_owner()
    # El celular perdido ya no es de confianza: no esquiva el bloqueo.
    assert lost_phone.post(LOGIN, json=RIGHT).status_code == 429


def test_many_emails_from_one_ip_are_capped_but_trusted_devices_are_not(client: TestClient) -> None:
    owner = device()
    intruder = device(logged_in=False)
    for i in range(config.get_settings().login_ip_max_attempts):
        r = intruder.post(LOGIN, json={"email": f"x{i}@example.com", "password": "no-es-la-clave"})
        assert r.status_code == 401
    assert intruder.post(LOGIN, json={"email": "otro@example.com", "password": "x"}).status_code == 429
    assert owner.post(LOGIN, json=RIGHT).status_code == 200


def test_device_cookie_is_httponly_lax_and_long_lived(client: TestClient) -> None:
    r = TestClient(app).post(LOGIN, json=RIGHT)
    (cookie,) = [v for k, v in r.headers.multi_items() if k == "set-cookie" and v.startswith(f"{DEVICE_COOKIE}=")]
    low = cookie.lower()
    assert "httponly" in low and "samesite=lax" in low and "path=/" in low and "max-age=15552000" in low


# ---------- Cerrar sesión revoca el token ----------


def test_logout_revokes_the_token_even_if_someone_copied_it(make_client) -> None:
    client = make_client()
    other_session = make_client(register=False)
    stolen = client.cookies.get(ACCESS_COOKIE)
    assert client.post("/api/v1/auth/logout").status_code == 204
    thief = TestClient(app)
    thief.cookies.set(ACCESS_COOKIE, stolen)
    assert thief.get("/api/v1/auth/me").status_code == 401
    # Las demás sesiones de la misma cuenta siguen abiertas.
    assert other_session.get("/api/v1/auth/me").status_code == 200


def test_session_token_without_id_is_rejected(client: TestClient) -> None:
    now = int(time.time())
    old_style = jwt.encode(
        {"sub": "1", "ver": 0, "iat": now, "exp": now + 3600}, config.get_settings().secret_key, algorithm=ALGORITHM
    )
    anon = TestClient(app)
    anon.cookies.set(ACCESS_COOKIE, old_style)
    assert anon.get("/api/v1/auth/me").status_code == 401


# ---------- Registro ----------


def test_registration_is_rate_limited_per_ip(make_client, monkeypatch) -> None:
    make_client()
    monkeypatch.setattr(config.get_settings(), "allow_registration", True)
    spammer = TestClient(app, headers={"X-Real-IP": "198.51.100.7"})
    for i in range(10):
        r = spammer.post("/api/v1/auth/register", json={"email": f"spam{i}@example.com", "password": PASSWORD})
        assert r.status_code == 201, r.text
    r = spammer.post("/api/v1/auth/register", json={"email": "spam-extra@example.com", "password": PASSWORD})
    assert r.status_code == 429


# ---------- Configuración ----------


def test_example_database_password_is_rejected() -> None:
    url = "postgresql+psycopg://factura_app:{}@db:5432/factura"
    base = {"secret_key": "k" * 40}
    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD"):
        config.Settings(**base, database_url=url.format("cambiar-por-una-clave-larga"))
    assert config.Settings(**base, database_url=url.format("Xq9-aleatoria-larga")).database_url
