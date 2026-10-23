"""Hash de contraseñas (Argon2), tokens JWT y tokens CSRF."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

ALGORITHM = "HS256"
ACCESS_COOKIE = "factura_session"
CSRF_COOKIE = "factura_csrf"
CSRF_HEADER = "X-CSRF-Token"
# Dispositivo donde ya se entró bien alguna vez. Los intentos fallidos de otros no lo bloquean.
DEVICE_COOKIE = "factura_device"
DEVICE_AUDIENCE = "trusted-device"
DEVICE_DAYS = 180

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


@dataclass(frozen=True)
class SessionToken:
    user_id: int
    version: int
    # Identificador único de esta sesión: al cerrarla se anota como revocado.
    jti: str
    expires_at: datetime


def create_access_token(user_id: int, session_version: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "ver": session_version,
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> SessionToken | None:
    """La sesión del token, o None si el token no es válido."""
    try:
        payload = jwt.decode(
            token,
            get_settings().secret_key,
            algorithms=[ALGORITHM],
            # Un token sin vencimiento (o sin identificador para poder revocarlo) nunca se acepta.
            options={"require": ["exp", "iat", "sub", "ver", "jti"]},
        )
        jti = payload["jti"]
        if not isinstance(jti, str) or not 16 <= len(jti) <= 64:
            return None
        return SessionToken(
            int(payload["sub"]), int(payload["ver"]), jti, datetime.fromtimestamp(int(payload["exp"]), UTC)
        )
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


def create_signed(payload: dict[str, object], audience: str, minutes: int) -> str:
    """Token firmado de corta duración para un uso concreto (por ejemplo, el ingreso con Google).

    El `aud` impide usarlo para otra cosa: el de sesión no lleva `aud`, y PyJWT rechaza un token
    con `aud` si no se pidió ese público al leerlo.
    """
    now = datetime.now(UTC)
    claims = {**payload, "aud": audience, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(claims, get_settings().secret_key, algorithm=ALGORITHM)


def decode_signed(token: str, audience: str) -> dict[str, object] | None:
    try:
        return jwt.decode(
            token,
            get_settings().secret_key,
            algorithms=[ALGORITHM],
            audience=audience,
            options={"require": ["exp", "iat", "aud"]},
        )
    except jwt.PyJWTError:
        return None


def create_device_token(email: str, session_version: int) -> str:
    """Marca este navegador como uno donde `email` ya entró bien (técnica "device cookie" de OWASP).

    Lleva la versión de sesión: cerrar todas las sesiones o cambiar la contraseña también le
    quita la confianza a los demás dispositivos.
    """
    claims = {"did": secrets.token_urlsafe(16), "email": email.lower(), "sv": session_version}
    return create_signed(claims, DEVICE_AUDIENCE, DEVICE_DAYS * 24 * 60)


def device_id(token: str, email: str | None = None, session_version: int | None = None) -> str | None:
    """Id del dispositivo si el token es válido y, si se indican, de ese email y esa versión de sesión."""
    data = decode_signed(token, DEVICE_AUDIENCE) if token else None
    if not data or not isinstance(data.get("did"), str) or not isinstance(data.get("email"), str):
        return None
    if email is not None and data["email"] != email.lower():
        return None
    if session_version is not None and data.get("sv") != session_version:
        return None
    return str(data["did"])[:64]


def keyed_hash(purpose: str, value: str) -> str:
    """HMAC-SHA256 con la clave del servidor: sirve para guardar códigos sin guardarlos en claro."""
    key = get_settings().secret_key.encode()
    return hmac.new(key, f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


# Contraseñas de 10 o más caracteres que igual son de las primeras que se prueban.
_COMMON_PASSWORDS = {
    "password123", "password1234", "contraseña", "contrasena", "contraseña1", "contrasena1", "contraseña123",
    "contrasena123", "administrador", "admin12345", "qwerty1234", "qwerty123456", "iloveyou12", "paraguay123",
    "asuncion123", "factura123", "1q2w3e4r5t", "q1w2e3r4t5", "abc1234567", "1234qwerty", "pass123456",
}  # fmt: skip
_SEQUENCES = ("0123456789012345678901234567890", "abcdefghijklmnñopqrstuvwxyz", "qwertyuiopasdfghjklñzxcvbnm")


def weak_password_reason(password: str, email: str = "") -> str | None:
    """Motivo por el que una contraseña es demasiado fácil de adivinar, o None si está bien."""
    low = password.lower()
    if len(set(low)) < 4:
        return "La contraseña repite muy pocos caracteres. Elegí otra."
    if low in _COMMON_PASSWORDS or any(low in seq or low in seq[::-1] for seq in _SEQUENCES):
        return "Esa contraseña es de las más usadas. Elegí otra."
    user = email.split("@")[0].lower()
    if len(user) >= 4 and user in low:
        return "La contraseña no puede contener tu email. Elegí otra."
    return None
