"""Ingreso con Google y vínculo de la cuenta de Google desde Ajustes.

El ida y vuelta con Google pasa por el navegador: `start` (o `link`) guarda en una cookie firmada
los valores de un solo uso (state, PKCE, nonce) y manda a Google; Google vuelve a `callback`
con un código que se canjea directo con Google y se valida antes de abrir la sesión.
"""

import logging
import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import DB, CurrentUser, LoginLimiter, client_ip, trusted_device, verify_csrf
from app.api.v1.auth import start_session
from app.core.config import get_settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.security import create_signed, decode_signed
from app.models import User
from app.schemas.auth import GoogleLinkOut
from app.services import google_auth, users

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/google", tags=["autenticación"])

STATE_COOKIE = "factura_oauth"
STATE_PATH = "/api/v1/auth/google"
STATE_AUDIENCE = "google-oauth-state"
STATE_MINUTES = 10

# Destinos fijos de la vuelta: nunca se redirige a una dirección que venga en el pedido.
LOGIN_PAGE = "/ingresar"
SETTINGS_PAGE = "/ajustes?seccion=seguridad"
LOGIN_DONE = "/?ingreso=google"  # la app reclama para esta cuenta las notificaciones del dispositivo

Mode = Literal["login", "link"]


def _redirect_uri(request: Request) -> str | None:
    return google_auth.redirect_uri(request.headers.get("host", ""), request.url.scheme)


def _set_state(
    response: Response, req: google_auth.AuthRequest, redirect_uri: str, mode: Mode, **extra: object
) -> None:
    token = create_signed(
        {"st": req.state, "cv": req.verifier, "nn": req.nonce, "ru": redirect_uri, "mode": mode, **extra},
        STATE_AUDIENCE,
        STATE_MINUTES,
    )
    # Lax (no Strict): la vuelta desde Google es una navegación que viene de otro sitio y una
    # cookie Strict no llegaría. Solo viaja a /api/v1/auth/google y dura 10 minutos.
    response.set_cookie(
        STATE_COOKIE,
        token,
        max_age=STATE_MINUTES * 60,
        path=STATE_PATH,
        secure=get_settings().cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _back(target: str) -> RedirectResponse:
    response = RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(STATE_COOKIE, path=STATE_PATH)  # un solo uso
    return response


def _failed(mode: object, reason: str) -> RedirectResponse:
    page = SETTINGS_PAGE + "&" if mode == "link" else LOGIN_PAGE + "?"
    return _back(f"{page}google={reason}")


@router.get("/start")
def start(request: Request) -> RedirectResponse:
    """Botón "Continuar con Google" de la pantalla de ingreso."""
    redirect_uri = _redirect_uri(request)
    if redirect_uri is None:
        return _back(f"{LOGIN_PAGE}?google=no-disponible")
    req = google_auth.new_request(redirect_uri)
    response = RedirectResponse(req.url, status_code=status.HTTP_303_SEE_OTHER)
    _set_state(response, req, redirect_uri, "login")
    return response


@router.post("/link", response_model=GoogleLinkOut, dependencies=[Depends(verify_csrf)])
def link(request: Request, response: Response, user: CurrentUser) -> GoogleLinkOut:
    """Ajustes → Seguridad → Vincular: devuelve la dirección de Google a la que ir."""
    redirect_uri = _redirect_uri(request)
    if redirect_uri is None:
        raise NotFoundError("Ingreso con Google")
    req = google_auth.new_request(redirect_uri)
    # Al volver de Google la cookie de sesión (Strict) no llega: la cuenta va firmada en esta
    # cookie, junto con la versión de sesión (si se cierran todas las sesiones, deja de valer).
    _set_state(response, req, redirect_uri, "link", uid=user.id, sv=user.session_version)
    return GoogleLinkOut(url=req.url)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(verify_csrf)])
def unlink(user: CurrentUser, db: DB) -> None:
    users.google_unlink(db, user)


@router.get("/callback")
def callback(
    request: Request,
    db: DB,
    limiter: LoginLimiter,
    code: Annotated[str | None, Query(max_length=2048)] = None,
    state: Annotated[str | None, Query(max_length=256)] = None,
    error: Annotated[str | None, Query(max_length=100)] = None,
) -> RedirectResponse:
    data = decode_signed(request.cookies.get(STATE_COOKIE, ""), STATE_AUDIENCE)
    mode = data.get("mode") if data else "login"
    # Igual que en el ingreso con contraseña: un dispositivo de confianza no comparte la cuenta de
    # intentos con los demás que llegan con la misma IP.
    device = trusted_device(request)
    key = f"google:device:{device}" if device else f"google:{client_ip(request)}"
    if limiter.is_blocked(key):
        return _failed(mode, "demasiados")
    if data is None:
        return _failed(mode, "expirado")  # cookie vencida, ausente o alterada
    if error:
        return _failed(mode, "cancelado" if error == "access_denied" else "error")
    # El state tiene que ser el de este navegador: si no, alguien intenta hacerte entrar con su
    # cuenta (CSRF de login) o reusar una vuelta vieja.
    if not code or not state or not secrets.compare_digest(state, str(data.get("st", ""))):
        limiter.hit(key)
        return _failed(mode, "expirado")
    try:
        id_token = google_auth.exchange_code(code, str(data["ru"]), str(data["cv"]))
        identity = google_auth.verify_id_token(id_token, str(data["nn"]))
    except (google_auth.GoogleAuthError, KeyError) as exc:
        limiter.hit(key)
        logger.warning("Ingreso con Google rechazado: %s", exc)
        return _failed(mode, "error")

    if mode == "link":
        uid = data.get("uid")
        user = db.get(User, uid) if isinstance(uid, int) else None
        if not user or user.session_version != data.get("sv"):
            return _failed(mode, "expirado")
        try:
            users.google_link(db, user, identity)
        except ConflictError:
            db.rollback()
            return _failed(mode, "ya-vinculada")
        return _back(f"{SETTINGS_PAGE}&google=vinculado")

    try:
        user = users.google_login(db, identity)
    except (ForbiddenError, ConflictError) as exc:
        db.rollback()
        return _failed(mode, "sin-cuenta" if isinstance(exc, ForbiddenError) else "vincular")
    limiter.reset(key)
    response = _back(LOGIN_DONE)
    start_session(response, user)
    return response
