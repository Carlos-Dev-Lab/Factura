from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import (
    DB,
    CurrentUser,
    LoginIpLimiter,
    LoginLimiter,
    RegisterLimiter,
    client_ip,
    current_session,
    trusted_device,
    verify_csrf,
)
from app.core.config import get_settings
from app.core.errors import AuthError, TooManyRequestsError, ValidationError
from app.core.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    DEVICE_COOKIE,
    DEVICE_DAYS,
    create_access_token,
    create_device_token,
    new_csrf_token,
    weak_password_reason,
)
from app.models import RevokedSession, User
from app.schemas.auth import AuthConfigOut, LoginIn, PasswordChangeIn, ProfileUpdate, RegisterIn, UserOut
from app.services import google_auth, notify, users

router = APIRouter(prefix="/auth", tags=["autenticación"])

TOO_MANY = "Demasiados intentos. Esperá unos minutos y volvé a probar."


def start_session(response: Response, user: User) -> None:
    s = get_settings()
    max_age = s.access_token_minutes * 60
    common = {"max_age": max_age, "secure": s.cookie_secure, "samesite": "strict", "path": "/"}
    response.set_cookie(ACCESS_COOKIE, create_access_token(user.id, user.session_version), httponly=True, **common)
    response.set_cookie(CSRF_COOKIE, new_csrf_token(), httponly=False, **common)
    # Lax: tiene que llegar también a la vuelta del ingreso con Google (viene de otro sitio). No da
    # acceso a nada; solo hace que los intentos fallidos de otros no bloqueen a este dispositivo.
    response.set_cookie(
        DEVICE_COOKIE,
        create_device_token(user.email, user.session_version),
        max_age=DEVICE_DAYS * 24 * 3600,
        secure=s.cookie_secure,
        httponly=True,
        samesite="lax",
        path="/",
    )


def end_session(response: Response) -> None:
    # La cookie de dispositivo se conserva: este navegador sigue siendo de confianza para el ingreso.
    for name in (ACCESS_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/")


def revoke_current(request: Request, db: DB) -> None:
    """El token de este pedido deja de valer, aunque alguien lo haya copiado antes."""
    if token := current_session(request, db):
        stmt = insert(RevokedSession).values(jti=token.jti, expires_at=token.expires_at)
        db.execute(stmt.on_conflict_do_nothing(index_elements=["jti"]))


@router.get("/config", response_model=AuthConfigOut)
def auth_config(request: Request, db: DB) -> AuthConfigOut:
    return AuthConfigOut(
        registration_open=users.registration_open(db),
        first_user=not users.has_users(db),
        google_login=google_auth.redirect_uri(request.headers.get("host", ""), request.url.scheme) is not None,
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterIn, request: Request, response: Response, db: DB, limiter: RegisterLimiter) -> User:
    key = f"register:{client_ip(request)}"
    if limiter.is_blocked(key):
        raise TooManyRequestsError(TOO_MANY)
    limiter.hit(key)
    user = users.register(db, data)
    start_session(response, user)
    return user


@router.post("/login", response_model=UserOut)
def login(
    data: LoginIn, request: Request, response: Response, db: DB, limiter: LoginLimiter, ip_limiter: LoginIpLimiter
) -> User:
    email = data.email.lower()
    version = db.scalar(select(User.session_version).where(User.email == email))
    # Detrás de Docker Desktop o de `tailscale serve` todos llegan con la misma IP: contar los
    # intentos por IP dejaría que cualquiera bloquee el ingreso del dueño. Un dispositivo donde ya
    # se entró bien tiene su propia cuenta de intentos; los demás se cuentan por IP y email.
    device = trusted_device(request, email, version) if version is not None else None
    key = f"device:{device}:{email}" if device else f"{client_ip(request)}:{email}"
    ip_key = None if device else f"login-ip:{client_ip(request)}"
    if limiter.is_blocked(key) or (ip_key and ip_limiter.is_blocked(ip_key)):
        raise TooManyRequestsError(TOO_MANY)
    try:
        user = users.authenticate(db, email, data.password.get_secret_value())
    except AuthError:
        limiter.hit(key)
        if ip_key:
            ip_limiter.hit(ip_key)
        raise
    limiter.reset(key)
    start_session(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(verify_csrf)])
def logout(request: Request, response: Response, db: DB) -> None:
    revoke_current(request, db)
    end_session(response)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(verify_csrf)])
def logout_everywhere(response: Response, user: CurrentUser, db: DB) -> None:
    """Invalida todas las sesiones (por ejemplo, si perdiste el celular). Hay que volver a entrar."""
    user.session_version += 1
    # Y ningún dispositivo sigue recibiendo notificaciones con montos y proveedores de esta cuenta.
    notify.unsubscribe_all(db, user)
    end_session(response)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserOut, dependencies=[Depends(verify_csrf)])
def update_me(data: ProfileUpdate, user: CurrentUser, db: DB) -> User:
    return users.update_profile(db, user, data)


@router.post("/password", response_model=UserOut, dependencies=[Depends(verify_csrf)])
def change_password(
    data: PasswordChangeIn, response: Response, user: CurrentUser, db: DB, limiter: LoginLimiter
) -> User:
    # Antes del límite de intentos: elegir una contraseña nueva débil no es un intento fallido.
    if reason := weak_password_reason(data.new_password.get_secret_value(), user.email):
        raise ValidationError(reason)
    # Con una sesión robada no se puede probar contraseñas sin límite para descubrir la actual.
    key = f"password-change:{user.id}"
    if limiter.is_blocked(key):
        raise TooManyRequestsError("Demasiados intentos. Esperá unos minutos y volvé a probar.")
    try:
        users.change_password(db, user, data)
    except ValidationError:
        limiter.hit(key)
        raise
    limiter.reset(key)
    start_session(response, user)  # las demás sesiones quedan invalidadas
    return user
