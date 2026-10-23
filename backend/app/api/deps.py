"""Dependencias compartidas por los endpoints."""

import secrets
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Path, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AuthError, ForbiddenError
from app.core.rate_limit import LoginAttemptLimiter
from app.core.security import ACCESS_COOKIE, CSRF_COOKIE, CSRF_HEADER, decode_access_token
from app.models import User
from app.schemas.common import MAX_DB_ID
from app.services.storage import LocalStorage

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# scope="function": el commit ocurre ANTES de enviar la respuesta. Desde FastAPI 0.118 el
# valor por defecto lo hace después, y un commit fallido devolvería 200 sin guardar nada.
DB = Annotated[Session, Depends(get_db, scope="function")]


@lru_cache
def get_storage() -> LocalStorage:
    return LocalStorage(get_settings().storage_dir)


@lru_cache
def get_login_limiter() -> LoginAttemptLimiter:
    s = get_settings()
    return LoginAttemptLimiter(s.login_max_attempts, s.login_window_seconds)


# Avisos por email: hasta 3 códigos de verificación y 5 intentos de código cada 15 minutos por
# usuario. Así nadie usa el servidor para llenar de correos una dirección ajena ni adivina el código.
EMAIL_WINDOW_SECONDS = 15 * 60


@lru_cache
def get_email_send_limiter() -> LoginAttemptLimiter:
    return LoginAttemptLimiter(3, EMAIL_WINDOW_SECONDS)


@lru_cache
def get_email_code_limiter() -> LoginAttemptLimiter:
    return LoginAttemptLimiter(5, EMAIL_WINDOW_SECONDS)


def verify_csrf(request: Request) -> None:
    """Doble envío: el header debe coincidir con la cookie CSRF (no legible por otros sitios)."""
    if request.method in SAFE_METHODS:
        return
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not secrets.compare_digest(cookie, header):
        raise ForbiddenError("Token CSRF inválido. Recargá la página.")


def current_user(request: Request, db: DB) -> User:
    decoded = decode_access_token(request.cookies.get(ACCESS_COOKIE, ""))
    if decoded is None:
        raise AuthError("Sesión no iniciada o expirada")
    user_id, version = decoded
    user = db.get(User, user_id)
    if not user or user.session_version != version:
        raise AuthError("Sesión no iniciada o expirada")
    return user


def client_ip(request: Request) -> str:
    # Nginx define X-Real-IP; uvicorn corre con --proxy-headers detrás de él.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "desconocido")


CurrentUser = Annotated[User, Depends(current_user)]
# Id en la ruta (/transactions/{id}): con tope, igual que los ids que llegan en el cuerpo.
PathId = Annotated[int, Path(ge=1, le=MAX_DB_ID)]
Storage = Annotated[LocalStorage, Depends(get_storage)]
LoginLimiter = Annotated[LoginAttemptLimiter, Depends(get_login_limiter)]
EmailSendLimiter = Annotated[LoginAttemptLimiter, Depends(get_email_send_limiter)]
EmailCodeLimiter = Annotated[LoginAttemptLimiter, Depends(get_email_code_limiter)]
