"""Ingreso con Google: ida y vuelta OAuth, validación del id_token y reglas para vincular cuentas.

Google se simula: el canje del código devuelve un id_token firmado con una clave RSA de prueba,
y las "claves públicas de Google" son la pública de esa misma clave.
"""

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.api.v1.google import STATE_COOKIE
from app.core import config
from app.core.security import ACCESS_COOKIE, CSRF_COOKIE, CSRF_HEADER, decode_access_token, decode_signed
from app.main import app
from app.services import google_auth
from tests.conftest import PASSWORD

CLIENT_ID = "cliente-de-prueba.apps.googleusercontent.com"
LOCAL = "http://localhost:8080"
CALLBACK = "/api/v1/auth/google/callback"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _FakeJWKS:
    """Hace de las claves públicas de Google."""

    class _Key:
        key = _KEY.public_key()

    def get_signing_key_from_jwt(self, token: str) -> "_FakeJWKS._Key":
        return self._Key()


def make_token(expected_nonce: str, key=_KEY, **overrides: object) -> str:
    now = int(time.time())
    claims: dict[str, object] = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "azp": CLIENT_ID,
        "sub": "109876543210",
        "email": "ana@gmail.com",
        "email_verified": True,
        "name": "Ana",
        "iat": now,
        "exp": now + 3600,
        "nonce": expected_nonce,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


class Google:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.mp = monkeypatch

    def _answer(self, auth_url: str, **claims: object) -> str:
        q = parse_qs(urlsplit(auth_url).query)
        token = make_token(q["nonce"][0], **claims)
        self.mp.setattr(google_auth, "exchange_code", lambda code, redirect_uri, verifier: token)
        return q["state"][0]

    def login(self, client: TestClient, **claims: object) -> httpx.Response:
        start = client.get("/api/v1/auth/google/start", follow_redirects=False)
        assert start.status_code == 303, start.text
        state = self._answer(start.headers["location"], **claims)
        return client.get(CALLBACK, params={"code": "codigo", "state": state}, follow_redirects=False)

    def link(self, client: TestClient, **claims: object) -> httpx.Response:
        r = client.post("/api/v1/auth/google/link")
        assert r.status_code == 200, r.text
        state = self._answer(r.json()["url"], **claims)
        return client.get(CALLBACK, params={"code": "codigo", "state": state}, follow_redirects=False)


@pytest.fixture
def google(monkeypatch: pytest.MonkeyPatch) -> Google:
    s = config.get_settings()
    monkeypatch.setattr(s, "google_client_id", CLIENT_ID)
    monkeypatch.setattr(s, "google_client_secret", "secreto-de-prueba")
    monkeypatch.setattr(google_auth, "_jwks", lambda: _FakeJWKS())
    return Google(monkeypatch)


def local_client() -> TestClient:
    return TestClient(app, base_url=LOCAL)


def local_user(email: str) -> TestClient:
    """Cuenta con contraseña, con sesión en http://localhost:8080 (las cookies son por dirección)."""
    client = local_client()
    r = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD, "name": "Carlo"})
    assert r.status_code == 201, r.text
    return with_csrf(client)


def with_csrf(client: TestClient) -> TestClient:
    client.headers[CSRF_HEADER] = client.cookies.get(CSRF_COOKIE, "")
    return client


def set_cookies(r: httpx.Response) -> list[str]:
    return [v for k, v in r.headers.multi_items() if k == "set-cookie"]


# ---------- Ida a Google ----------


def test_start_sends_to_google_with_pkce_and_a_protected_state_cookie(google: Google) -> None:
    r = local_client().get("/api/v1/auth/google/start", follow_redirects=False)
    assert r.status_code == 303
    url = urlsplit(r.headers["location"])
    assert (url.scheme, url.netloc) == ("https", "accounts.google.com")
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert q["client_id"] == CLIENT_ID
    assert q["redirect_uri"] == LOCAL + CALLBACK
    assert q["response_type"] == "code" and q["scope"] == "openid email profile"
    assert q["code_challenge_method"] == "S256" and q["prompt"] == "select_account"
    assert len(q["state"]) >= 43 and len(q["nonce"]) >= 43  # 256 bits

    (cookie,) = [c for c in set_cookies(r) if c.startswith(f"{STATE_COOKIE}=")]
    low = cookie.lower()
    assert "httponly" in low and "samesite=lax" in low and "path=/api/v1/auth/google" in low and "max-age=600" in low
    data = decode_signed(cookie.split(";")[0].split("=", 1)[1], "google-oauth-state")
    assert data and data["st"] == q["state"] and data["nn"] == q["nonce"] and data["mode"] == "login"
    challenge = base64.urlsafe_b64encode(hashlib.sha256(str(data["cv"]).encode()).digest()).rstrip(b"=").decode()
    assert challenge == q["code_challenge"]
    assert "secreto" not in r.headers["location"]  # el secreto nunca viaja por el navegador


def test_google_button_only_where_google_accepts_the_return_address(google: Google, monkeypatch) -> None:
    assert TestClient(app).get("/api/v1/auth/config").json()["google_login"] is False  # host "testserver"
    assert local_client().get("/api/v1/auth/config").json()["google_login"] is True
    # Por la IP de la casa y sin HTTPS, Google no acepta la vuelta: no se ofrece el botón.
    lan = TestClient(app, base_url="http://192.168.0.10:8080")
    assert lan.get("/api/v1/auth/config").json()["google_login"] is False
    r = lan.get("/api/v1/auth/google/start", follow_redirects=False)
    assert r.headers["location"] == "/ingresar?google=no-disponible"
    # Detrás de `tailscale serve` el pedido llega por http, pero la vuelta es la dirección HTTPS pública.
    monkeypatch.setattr(config.get_settings(), "public_url", "https://mi-pc.tu-red.ts.net")
    ts = TestClient(app, base_url="http://mi-pc.tu-red.ts.net")
    r = ts.get("/api/v1/auth/google/start", follow_redirects=False)
    q = parse_qs(urlsplit(r.headers["location"]).query)
    assert q["redirect_uri"] == ["https://mi-pc.tu-red.ts.net" + CALLBACK]


def test_google_is_off_without_credentials() -> None:
    assert local_client().get("/api/v1/auth/config").json()["google_login"] is False
    r = local_client().get("/api/v1/auth/google/start", follow_redirects=False)
    assert r.headers["location"] == "/ingresar?google=no-disponible"


def test_weird_host_headers_never_build_a_return_address(google: Google) -> None:
    for host in ("localhost:8080@evil.example", "evil.example/x", "localhost:8080\r\nX: y", "", "a b"):
        assert google_auth.redirect_uri(host, "https") is None, host


# ---------- Vuelta de Google: cuentas ----------


def test_first_user_can_sign_up_with_google(google: Google) -> None:
    client = local_client()
    r = google.login(client)
    assert r.status_code == 303 and r.headers["location"] == "/?ingreso=google"
    cookies = set_cookies(r)
    assert any(c.startswith(f"{ACCESS_COOKIE}=") and "samesite=strict" in c.lower() for c in cookies)
    assert any(c.startswith(f'{STATE_COOKIE}=""') or (STATE_COOKIE in c and "max-age=0" in c.lower()) for c in cookies)
    me = client.get("/api/v1/auth/me").json()
    assert me["email"] == "ana@gmail.com" and me["name"] == "Ana"
    assert me["has_password"] is False and me["google_email"] == "ana@gmail.com"
    assert client.get("/api/v1/categories").json()  # misma cuenta inicial que con contraseña


def test_google_does_not_create_accounts_when_registration_is_closed(client: TestClient, google: Google) -> None:
    r = google.login(local_client(), email="nuevo@gmail.com", sub="999")
    assert r.headers["location"] == "/ingresar?google=sin-cuenta"
    assert not any(c.startswith(f"{ACCESS_COOKIE}=") for c in set_cookies(r))


def test_existing_gmail_account_is_recognized(make_client, google: Google) -> None:
    make_client("ana@gmail.com")
    client = local_client()
    assert google.login(client).headers["location"] == "/?ingreso=google"
    me = client.get("/api/v1/auth/me").json()
    assert me["email"] == "ana@gmail.com" and me["has_password"] is True and me["google_email"] == "ana@gmail.com"
    # La próxima vez se la reconoce por el identificador de Google, aunque cambie el email.
    again = local_client()
    assert google.login(again, email="ana.nueva@gmail.com").headers["location"] == "/?ingreso=google"
    assert again.get("/api/v1/auth/me").json()["id"] == me["id"]


def test_other_email_providers_are_not_linked_automatically(make_client, google: Google) -> None:
    # Google verificó carlo@example.com cuando se creó la cuenta de Google, pero ese dominio no es
    # suyo: la dirección hoy podría ser de otra persona. Hay que vincular desde Ajustes.
    make_client("carlo@example.com")
    r = google.login(local_client(), email="carlo@example.com")
    assert r.headers["location"] == "/ingresar?google=vincular"
    # Con Google Workspace (claim "hd" del mismo dominio), Google sí es la autoridad del email.
    assert (
        google.login(local_client(), email="carlo@example.com", hd="example.com").headers["location"]
        == "/?ingreso=google"
    )
    # Otro "hd" no cuenta.
    assert (
        google_auth.verify_id_token(
            make_token("n", email="x@example.com", hd="otro.com"), "n", _FakeJWKS()
        ).authoritative
        is False
    )


def test_unverified_google_email_is_rejected(google: Google) -> None:
    r = google.login(local_client(), email_verified=False)
    assert r.headers["location"] == "/ingresar?google=error"


# ---------- Vuelta de Google: state, cookie y errores ----------


def test_state_must_match_the_cookie_of_this_browser(google: Google) -> None:
    client = local_client()
    start = client.get("/api/v1/auth/google/start", follow_redirects=False)
    google._answer(start.headers["location"])
    # CSRF de login: alguien te hace abrir la vuelta con SU código y SU state.
    r = client.get(CALLBACK, params={"code": "codigo", "state": "state-de-otro"}, follow_redirects=False)
    assert r.headers["location"] == "/ingresar?google=expirado"
    # Sin la cookie (otro navegador) tampoco sirve.
    fresh = local_client()
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    r = fresh.get(CALLBACK, params={"code": "codigo", "state": state}, follow_redirects=False)
    assert r.headers["location"] == "/ingresar?google=expirado"


def test_state_cookie_is_single_use(google: Google) -> None:
    client = local_client()
    start = client.get("/api/v1/auth/google/start", follow_redirects=False)
    state = google._answer(start.headers["location"])
    first = client.get(CALLBACK, params={"code": "codigo", "state": state}, follow_redirects=False)
    assert first.headers["location"] == "/?ingreso=google"
    replay = client.get(CALLBACK, params={"code": "codigo", "state": state}, follow_redirects=False)
    assert replay.headers["location"] == "/ingresar?google=expirado"


def test_tampered_or_reused_state_cookie_is_rejected(google: Google) -> None:
    client = local_client()
    start = client.get("/api/v1/auth/google/start", follow_redirects=False)
    state = google._answer(start.headers["location"])
    raw = client.cookies.get(STATE_COOKIE)
    client.cookies.delete(STATE_COOKIE)
    client.cookies.set(STATE_COOKIE, raw[:-3] + "AAA", path="/api/v1/auth/google")
    r = client.get(CALLBACK, params={"code": "codigo", "state": state}, follow_redirects=False)
    assert r.headers["location"] == "/ingresar?google=expirado"


def test_cancel_and_google_failures_never_open_a_session(google: Google, monkeypatch) -> None:
    client = local_client()
    client.get("/api/v1/auth/google/start", follow_redirects=False)
    r = client.get(CALLBACK, params={"error": "access_denied"}, follow_redirects=False)
    assert r.headers["location"] == "/ingresar?google=cancelado"

    def broken(*_: object) -> str:
        raise google_auth.GoogleAuthError("Google rechazó el canje (400 invalid_grant)")

    start = client.get("/api/v1/auth/google/start", follow_redirects=False)
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    monkeypatch.setattr(google_auth, "exchange_code", broken)
    r = client.get(CALLBACK, params={"code": "codigo", "state": state}, follow_redirects=False)
    assert r.headers["location"] == "/ingresar?google=error"
    assert client.get("/api/v1/auth/me").status_code == 401


def test_return_address_is_always_internal(google: Google) -> None:
    # No hay parámetro "next": nadie puede usar la vuelta para mandarte a otro sitio.
    client = local_client()
    client.get("/api/v1/auth/google/start", follow_redirects=False)
    r = client.get(
        CALLBACK,
        params={"error": "x", "next": "https://evil.example", "redirect": "//evil.example"},
        follow_redirects=False,
    )
    assert r.headers["location"].startswith("/ingresar?google=")


def test_repeated_bad_returns_are_blocked(google: Google) -> None:
    client = local_client()
    for _ in range(5):
        client.get("/api/v1/auth/google/start", follow_redirects=False)
        client.get(CALLBACK, params={"code": "c", "state": "malo"}, follow_redirects=False)
    r = client.get(CALLBACK, params={"code": "c", "state": "malo"}, follow_redirects=False)
    assert r.headers["location"] == "/ingresar?google=demasiados"


def test_state_cookie_is_not_a_session(google: Google) -> None:
    client = local_client()
    client.get("/api/v1/auth/google/start", follow_redirects=False)
    raw = client.cookies.get(STATE_COOKIE)
    assert decode_access_token(raw) is None
    other = local_client()
    other.cookies.set(ACCESS_COOKIE, raw)
    assert other.get("/api/v1/auth/me").status_code == 401


# ---------- id_token ----------


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "otra-app.apps.googleusercontent.com"},
        {"azp": "otra-app.apps.googleusercontent.com"},
        {"iss": "https://accounts.google.com.evil.example"},
        {"nonce": "otro-nonce"},
        {"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200},
        {"iat": int(time.time()) + 3600, "exp": int(time.time()) + 7200},
        {"sub": None},
        {"email_verified": False},
        {"email_verified": None},
        {"email": None},
    ],
)
def test_invalid_id_tokens_are_rejected(google: Google, overrides: dict) -> None:
    with pytest.raises(google_auth.GoogleAuthError):
        google_auth.verify_id_token(make_token("nonce-ok", **overrides), "nonce-ok", _FakeJWKS())


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def test_forged_signatures_are_rejected(google: Google) -> None:
    good = jwt.decode(make_token("n"), options={"verify_signature": False})
    # Firmado con otra clave RSA (la del atacante).
    with pytest.raises(google_auth.GoogleAuthError):
        google_auth.verify_id_token(make_token("n", key=_OTHER_KEY), "n", _FakeJWKS())
    # Sin firma (alg "none").
    unsigned = f"{_b64(json.dumps({'alg': 'none', 'kid': 'k1'}).encode())}.{_b64(json.dumps(good).encode())}."
    with pytest.raises(google_auth.GoogleAuthError):
        google_auth.verify_id_token(unsigned, "n", _FakeJWKS())
    # HS256 usando la clave PÚBLICA de Google como secreto (confusión de algoritmos).
    pem = _KEY.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    signing_input = f"{_b64(json.dumps({'alg': 'HS256', 'kid': 'k1'}).encode())}.{_b64(json.dumps(good).encode())}"
    forged = f"{signing_input}.{_b64(hmac.new(pem, signing_input.encode(), hashlib.sha256).digest())}"
    with pytest.raises(google_auth.GoogleAuthError):
        google_auth.verify_id_token(forged, "n", _FakeJWKS())


def test_valid_id_token_gives_the_identity(google: Google) -> None:
    identity = google_auth.verify_id_token(make_token("n", email="Ana@Gmail.com"), "n", _FakeJWKS())
    assert (identity.sub, identity.email, identity.name, identity.authoritative) == (
        "109876543210",
        "ana@gmail.com",
        "Ana",
        True,
    )
    other = google_auth.verify_id_token(make_token("n", email="ana@example.com"), "n", _FakeJWKS())
    assert other.authoritative is False


# ---------- Vincular y desvincular desde Ajustes ----------


def test_link_and_unlink_from_settings(google: Google) -> None:
    client = local_user("carlo@example.com")
    r = google.link(client, email="carlo.personal@gmail.com", sub="555")
    assert r.headers["location"] == "/ajustes?seccion=seguridad&google=vinculado"
    me = client.get("/api/v1/auth/me").json()
    assert me["google_email"] == "carlo.personal@gmail.com" and me["email"] == "carlo@example.com"
    # Ahora entra con esa cuenta de Google aunque el email sea distinto.
    other = local_client()
    assert google.login(other, email="carlo.personal@gmail.com", sub="555").headers["location"] == "/?ingreso=google"
    assert other.get("/api/v1/auth/me").json()["id"] == me["id"]

    assert client.delete("/api/v1/auth/google").status_code == 204
    assert client.get("/api/v1/auth/me").json()["google_email"] is None
    assert (
        google.login(local_client(), email="carlo.personal@gmail.com", sub="555")
        .headers["location"]
        .endswith("google=sin-cuenta")
    )


def test_a_google_account_belongs_to_one_user(google: Google, monkeypatch) -> None:
    monkeypatch.setattr(config.get_settings(), "allow_registration", True)
    ana, beto = local_user("ana@example.com"), local_user("beto@example.com")
    assert google.link(ana, sub="777").headers["location"].endswith("google=vinculado")
    assert google.link(beto, sub="777").headers["location"] == "/ajustes?seccion=seguridad&google=ya-vinculada"


def test_logout_everywhere_cancels_a_pending_link(google: Google) -> None:
    client = local_user("carlo@example.com")
    r = client.post("/api/v1/auth/google/link")
    state = google._answer(r.json()["url"])
    # Alguien con la sesión robada empezó a vincular SU Google; cerrás todas las sesiones.
    assert client.post("/api/v1/auth/logout-all").status_code == 204
    r = client.get(CALLBACK, params={"code": "codigo", "state": state}, follow_redirects=False)
    assert r.headers["location"] == "/ajustes?seccion=seguridad&google=expirado"


def test_link_and_unlink_require_session_and_csrf(client: TestClient, google: Google) -> None:
    anon = local_client()
    assert anon.post("/api/v1/auth/google/link").status_code in (401, 403)
    assert anon.delete("/api/v1/auth/google").status_code in (401, 403)


# ---------- Cuentas creadas solo con Google ----------


def test_google_only_account_password_rules(google: Google) -> None:
    client = local_client()
    google.login(client)
    with_csrf(client)
    # Sin contraseña: no se entra con contraseña (mismo error que un email inexistente).
    r = local_client().post("/api/v1/auth/login", json={"email": "ana@gmail.com", "password": PASSWORD})
    assert r.status_code == 401 and r.json()["detail"] == "Email o contraseña incorrectos"
    # No puede desvincular Google: se quedaría sin forma de entrar.
    assert client.delete("/api/v1/auth/google").status_code == 422
    # Puede crear su primera contraseña sin "contraseña actual"; se validan las reglas de siempre.
    weak = client.post("/api/v1/auth/password", json={"new_password": "aaaaaaaaaaaa"})
    assert weak.status_code == 422
    r = client.post("/api/v1/auth/password", json={"new_password": PASSWORD})
    assert r.status_code == 200 and r.json()["has_password"] is True
    with_csrf(client)
    login = local_client().post("/api/v1/auth/login", json={"email": "ana@gmail.com", "password": PASSWORD})
    assert login.status_code == 200
    # Ya con contraseña, cambiarla exige la actual.
    assert client.post("/api/v1/auth/password", json={"new_password": "otra-clave-segura-456"}).status_code == 422
    assert client.delete("/api/v1/auth/google").status_code == 204
