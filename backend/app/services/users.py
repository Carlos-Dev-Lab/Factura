from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AuthError, ConflictError, ForbiddenError, ValidationError
from app.core.security import hash_password, verify_password, weak_password_reason
from app.models import User
from app.schemas.auth import PasswordChangeIn, ProfileUpdate, RegisterIn
from app.services import accounts, categories
from app.services.google_auth import GoogleIdentity

# Hash fijo para igualar el tiempo de respuesta cuando el email no existe.
_DUMMY_HASH = hash_password("timing-equalizer-password")
# Bloqueo de PostgreSQL que serializa los registros (número fijo y arbitrario).
_REGISTER_LOCK_ID = 727_002


def has_users(db: Session) -> bool:
    return db.scalar(select(User.id).limit(1)) is not None


def is_admin(db: Session, user: User) -> bool:
    """La primera cuenta creada administra el servidor (por ejemplo, ve los respaldos)."""
    return db.scalar(select(func.min(User.id))) == user.id


def registration_open(db: Session) -> bool:
    return get_settings().allow_registration or not has_users(db)


def _lock_registrations(db: Session) -> None:
    # Sin este bloqueo, dos registros simultáneos podrían ver "0 usuarios" y crear dos cuentas
    # aunque el registro esté cerrado. Se libera solo al terminar la transacción.
    db.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _REGISTER_LOCK_ID})


def _create_user(
    db: Session, email: str, name: str, password_hash: str | None, *, google: GoogleIdentity | None = None
) -> User:
    """Crea la cuenta con sus categorías y cuentas iniciales. Requiere `_lock_registrations`."""
    if db.scalar(select(User.id).where(User.email == email)):
        raise ConflictError("Ya existe una cuenta con ese email")
    user = User(email=email, password_hash=password_hash, name=name)
    if google:
        user.google_sub, user.google_email = google.sub, google.email
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        raise ConflictError("Ya existe una cuenta con ese email") from exc
    categories.seed_defaults(db, user)
    accounts.seed_defaults(db, user)
    db.flush()
    return user


def register(db: Session, data: RegisterIn) -> User:
    _lock_registrations(db)
    if not registration_open(db):
        raise ForbiddenError("El registro de nuevos usuarios está deshabilitado")
    email = data.email.lower()
    if reason := weak_password_reason(data.password.get_secret_value(), email):
        raise ValidationError(reason)
    return _create_user(db, email, data.name.strip(), hash_password(data.password.get_secret_value()))


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))
    # Si la cuenta no existe o no tiene contraseña (solo Google), se compara igual contra un hash
    # fijo: la respuesta tarda lo mismo y no revela qué cuentas existen.
    stored = user.password_hash if user and user.password_hash else _DUMMY_HASH
    if not verify_password(password, stored) or not user or not user.password_hash:
        raise AuthError("Email o contraseña incorrectos")
    return user


# ---------- Google ----------


def google_login(db: Session, identity: GoogleIdentity) -> User:
    """Cuenta para un ingreso con Google: la ya vinculada o una nueva.

    ConflictError: ya hay una cuenta con ese email. Nunca se vincula sola: el registro con
    contraseña no comprueba el email, así que esa cuenta pudo crearla otra persona con la
    dirección de la víctima (y conservaría su contraseña). Se vincula desde Ajustes, con la
    sesión iniciada. ForbiddenError: no hay cuenta y el registro está cerrado.
    """
    user = db.scalar(select(User).where(User.google_sub == identity.sub))
    if user:
        user.google_email = identity.email  # la persona pudo cambiar el email de su cuenta de Google
        return user
    if db.scalar(select(User.id).where(User.email == identity.email)):
        raise ConflictError("Esa cuenta existe: entrá con tu contraseña y vinculá Google desde Ajustes")
    _lock_registrations(db)
    if not registration_open(db):
        raise ForbiddenError("El registro de nuevos usuarios está deshabilitado")
    return _create_user(db, identity.email, identity.name, None, google=identity)


def google_link(db: Session, user: User, identity: GoogleIdentity) -> None:
    other = db.scalar(select(User.id).where(User.google_sub == identity.sub, User.id != user.id))
    if other:
        raise ConflictError("Esa cuenta de Google ya está vinculada a otro usuario")
    user.google_sub, user.google_email = identity.sub, identity.email
    try:
        db.flush()
    except IntegrityError as exc:  # otro pedido la vinculó al mismo tiempo
        raise ConflictError("Esa cuenta de Google ya está vinculada a otro usuario") from exc


def google_unlink(db: Session, user: User) -> None:
    if not user.has_password:
        raise ValidationError("Primero creá una contraseña: sin Google no tendrías otra forma de entrar.")
    user.google_sub = None
    user.google_email = None
    db.flush()


def update_profile(db: Session, user: User, data: ProfileUpdate) -> User:
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(user, field, value.strip() if isinstance(value, str) else value)
    db.flush()
    return user


def change_password(db: Session, user: User, data: PasswordChangeIn) -> None:
    # Una cuenta creada con Google puede elegir su primera contraseña sin la actual (no tiene).
    if user.password_hash is not None:
        current = data.current_password.get_secret_value() if data.current_password else ""
        if not current or not verify_password(current, user.password_hash):
            # 422 y no 401: la sesión sigue siendo válida, solo el dato ingresado es incorrecto.
            raise ValidationError("La contraseña actual no es correcta")
    user.password_hash = hash_password(data.new_password.get_secret_value())
    user.session_version += 1
