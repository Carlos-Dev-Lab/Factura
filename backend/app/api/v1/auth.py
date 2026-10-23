from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import DB, CurrentUser, LoginLimiter, client_ip, verify_csrf
from app.core.config import get_settings
from app.core.errors import AuthError, TooManyRequestsError, ValidationError
from app.core.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    create_access_token,
    new_csrf_token,
    weak_password_reason,
)
from app.models import User
from app.schemas.auth import AuthConfigOut, LoginIn, PasswordChangeIn, ProfileUpdate, RegisterIn, UserOut
from app.services import google_auth, notify, users

router = APIRouter(prefix="/auth", tags=["autenticación"])


def start_session(response: Response, user: User) -> None:
    s = get_settings()
    max_age = s.access_token_minutes * 60
    common = {"max_age": max_age, "secure": s.cookie_secure, "samesite": "strict", "path": "/"}
    response.set_cookie(ACCESS_COOKIE, create_access_token(user.id, user.session_version), httponly=True, **common)
    response.set_cookie(CSRF_COOKIE, new_csrf_token(), httponly=False, **common)


def end_session(response: Response) -> None:
    for name in (ACCESS_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/")


@router.get("/config", response_model=AuthConfigOut)
def auth_config(request: Request, db: DB) -> AuthConfigOut:
    return AuthConfigOut(
        registration_open=users.registration_open(db),
        first_user=not users.has_users(db),
        google_login=google_auth.redirect_uri(request.headers.get("host", ""), request.url.scheme) is not None,
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterIn, response: Response, db: DB) -> User:
    user = users.register(db, data)
    start_session(response, user)
    return user


@router.post("/login", response_model=UserOut)
def login(data: LoginIn, request: Request, response: Response, db: DB, limiter: LoginLimiter) -> User:
    key = f"{client_ip(request)}:{data.email.lower()}"
    if limiter.is_blocked(key):
        raise TooManyRequestsError("Demasiados intentos. Esperá unos minutos y volvé a probar.")
    try:
        user = users.authenticate(db, data.email, data.password.get_secret_value())
    except AuthError:
        limiter.hit(key)
        raise
    limiter.reset(key)
    start_session(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(verify_csrf)])
def logout(response: Response) -> None:
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
