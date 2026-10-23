"""Ingreso con Google: OAuth 2.0 + OpenID Connect, flujo de código con PKCE.

Solo se piden los permisos básicos (openid, email, profile) y no se guarda ningún token de
Google: del `id_token` verificado se toman el identificador estable (`sub`), el email y el nombre.
"""

import base64
import hashlib
import json
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from functools import lru_cache

import jwt

from app.core.config import get_settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
SCOPES = "openid email profile"
# Direcciones que Google controla siempre: si dice que están verificadas, lo están hoy.
GOOGLE_MAIL_DOMAINS = ("gmail.com", "googlemail.com")
CLOCK_SKEW_SECONDS = 60


class GoogleAuthError(Exception):
    """El ingreso con Google no se pudo completar. El mensaje es para los registros, no para el usuario."""


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    name: str
    # Google tiene autoridad sobre ese email (Gmail o Google Workspace): sirve para reconocer
    # una cuenta existente por su email. Con otras direcciones, Google solo las verificó al
    # crear la cuenta de Google y hoy podrían ser de otra persona.
    authoritative: bool


@dataclass(frozen=True)
class AuthRequest:
    url: str
    state: str
    verifier: str
    nonce: str


CALLBACK_PATH = "/api/v1/auth/google/callback"
_LOOPBACK = ("localhost", "127.0.0.1")
# Un Host normal (nombre o IPv4, con puerto opcional). Cualquier otra cosa no arma direcciones.
_HOST_RE = re.compile(r"[A-Za-z0-9.-]{1,253}(:[0-9]{1,5})?")


def redirect_uri(host: str, scheme: str) -> str | None:
    """Dirección de retorno para quien entró con ese Host, o None si Google no la aceptaría.

    Google solo acepta http en localhost; en cualquier otro nombre exige HTTPS. Detrás de
    `tailscale serve` el pedido llega a nginx por http, por eso se usa PUBLIC_URL cuando el
    nombre coincide. Hay que registrar cada dirección resultante en Google Cloud Console.
    """
    s = get_settings()
    if not s.google_enabled or not _HOST_RE.fullmatch(host or ""):
        return None
    hostname = (urllib.parse.urlsplit(f"//{host}").hostname or "").lower()
    public = urllib.parse.urlsplit(s.public_url)
    if hostname in _LOOPBACK:
        base = f"{scheme}://{host}"
    elif public.scheme == "https" and public.netloc and public.netloc.lower() == host.lower():
        base = f"https://{public.netloc}"
    elif scheme == "https" and hostname:
        base = f"https://{host}"
    else:
        return None
    return base + CALLBACK_PATH


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def new_request(redirect_uri: str) -> AuthRequest:
    """Dirección de Google a la que se manda al navegador, con sus valores de un solo uso."""
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)  # PKCE: 86 caracteres (el estándar pide de 43 a 128)
    params = {
        "client_id": get_settings().google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "nonce": nonce,
        "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()),
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return AuthRequest(f"{AUTH_URL}?{urllib.parse.urlencode(params)}", state, verifier, nonce)


def _error_reason(exc: urllib.error.HTTPError) -> str:
    try:
        return str(json.loads(exc.read()).get("error", ""))[:60]
    except (ValueError, AttributeError, OSError):
        return ""


def exchange_code(code: str, redirect_uri: str, verifier: str) -> str:
    """Canjea el código de autorización por el `id_token` (directo con Google, por HTTPS)."""
    s = get_settings()
    data = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": s.google_client_id,
            "client_secret": s.google_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        }
    ).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        # Solo el tipo de error de Google (por ejemplo invalid_grant): nunca el código ni el secreto.
        raise GoogleAuthError(f"Google rechazó el canje ({exc.code} {_error_reason(exc)})") from None
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise GoogleAuthError(f"No se pudo contactar a Google ({type(exc).__name__})") from None
    token = body.get("id_token") if isinstance(body, dict) else None
    if not isinstance(token, str):
        raise GoogleAuthError("Google no devolvió un id_token")
    return token


@lru_cache
def _jwks() -> jwt.PyJWKClient:
    # Claves públicas de Google, en caché una hora (Google las rota cada tanto).
    return jwt.PyJWKClient(CERTS_URL, cache_keys=True, lifespan=3600, timeout=10)


def verify_id_token(token: str, nonce: str, jwks: jwt.PyJWKClient | None = None) -> GoogleIdentity:
    """Valida el `id_token` por completo y devuelve la identidad. Lanza GoogleAuthError si algo no cuadra."""
    client_id = get_settings().google_client_id
    try:
        # Solo RS256: "none" o HS256 (firmado con la clave pública como si fuera un secreto)
        # permitirían falsificar el token.
        if jwt.get_unverified_header(token).get("alg") != "RS256":
            raise GoogleAuthError("Algoritmo de firma no permitido")
        key = (jwks or _jwks()).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=ISSUERS,
            leeway=CLOCK_SKEW_SECONDS,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise GoogleAuthError(f"id_token inválido ({type(exc).__name__})") from None

    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise GoogleAuthError("El nonce no coincide")
    if "azp" in claims and claims["azp"] != client_id:
        raise GoogleAuthError("El token fue emitido para otra aplicación")
    if claims.get("email_verified") not in (True, "true"):
        raise GoogleAuthError("La cuenta de Google no tiene el email verificado")

    sub = str(claims["sub"])
    email = str(claims.get("email", "")).strip().lower()
    if not sub or len(sub) > 255 or "@" not in email or len(email) > 254:
        raise GoogleAuthError("Datos de la cuenta de Google incompletos")
    domain = email.rsplit("@", 1)[1]
    authoritative = domain in GOOGLE_MAIL_DOMAINS or claims.get("hd") == domain
    name = str(claims.get("name") or claims.get("given_name") or "").strip()[:80]
    return GoogleIdentity(sub=sub, email=email, name=name, authoritative=authoritative)
