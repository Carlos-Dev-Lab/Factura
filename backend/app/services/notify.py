"""Entrega de avisos fuera de la app: notificaciones push del navegador, Telegram y email.

- Push: las claves VAPID se generan solas la primera vez y se guardan en la base.
  Necesita HTTPS (o localhost) en el navegador.
- Telegram: opcional. Se activa con TELEGRAM_BOT_TOKEN; cada usuario vincula su
  chat mandando "/start <código>" al bot.
- Email: opcional. Se activa con SMTP_USER y SMTP_PASSWORD (una cuenta del servidor, por
  ejemplo Gmail con contraseña de aplicación); cada usuario confirma su dirección con un código.
"""

import base64
import json
import logging
import secrets
import urllib.error
import urllib.request
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlparse

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from pywebpush import WebPushException, webpush
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotConfiguredError, NotFoundError, UpstreamError, ValidationError
from app.core.security import keyed_hash
from app.models import NotificationLog, PushSubscription, ServerKey, User
from app.schemas.support import (
    Alert,
    AlertLevel,
    EmailStartOut,
    NotificationSettings,
    NotificationSettingsUpdate,
    PushSubscriptionIn,
    TelegramLink,
    TestResult,
)
from app.services import alerts as alerts_service
from app.services import mailer

logger = logging.getLogger(__name__)

# Solo se aceptan suscripciones de los servicios push de los navegadores. Así nadie puede
# registrar una URL interna (http://db:5432, la red de la casa...) para que el servidor la llame.
PUSH_HOSTS = (
    "fcm.googleapis.com",
    "push.services.mozilla.com",
    "notify.windows.com",
    "push.apple.com",
)
TELEGRAM_API = "https://api.telegram.org"
LINK_MINUTES = 15
EMAIL_CODE_MINUTES = 15
DIGEST_MAX_LINES = 6
QUIET_FROM_HOUR = 22  # no se mandan avisos de noche


# ---------- Claves del servidor ----------


def _get_key(db: Session, name: str) -> str | None:
    row = db.get(ServerKey, name)
    return row.value if row else None


def _set_key(db: Session, name: str, value: str, *, only_if_missing: bool = False) -> str:
    stmt = insert(ServerKey).values(name=name, value=value)
    stmt = (
        stmt.on_conflict_do_nothing(index_elements=["name"])
        if only_if_missing
        else stmt.on_conflict_do_update(index_elements=["name"], set_={"value": value})
    )
    db.execute(stmt)
    db.flush()
    stored = db.scalar(select(ServerKey.value).where(ServerKey.name == name).execution_options(populate_existing=True))
    return stored or value


def _vapid(db: Session) -> Vapid:
    pem = _get_key(db, "vapid_private_pem")
    if pem is None:
        fresh = Vapid()
        fresh.generate_keys()
        # Si dos procesos generan a la vez, queda la primera clave guardada.
        pem = _set_key(db, "vapid_private_pem", fresh.private_pem().decode(), only_if_missing=True)
    return Vapid.from_pem(pem.encode())


def public_key(db: Session) -> str:
    """Clave pública VAPID (applicationServerKey) en base64url, para el navegador."""
    raw = _vapid(db).public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


# ---------- Preferencias ----------


def settings_for(db: Session, user: User) -> NotificationSettings:
    count = db.scalar(select(func.count()).select_from(PushSubscription).where(PushSubscription.user_id == user.id))
    return NotificationSettings(
        notifications_enabled=user.notifications_enabled,
        notify_hour=user.notify_hour,
        notify_days_before=user.notify_days_before,
        push_available=True,
        push_devices=count or 0,
        telegram_available=bool(get_settings().telegram_bot_token),
        telegram_linked=user.telegram_chat_id is not None,
        email_available=mailer.available(),
        email_enabled=user.email_notify_enabled and user.notify_email is not None,
        email_address=user.notify_email,
        email_pending=user.email_pending if _code_alive(user) else None,
    )


def update_settings(db: Session, user: User, data: NotificationSettingsUpdate) -> NotificationSettings:
    values = data.model_dump(exclude_unset=True, exclude_none=True)
    if (email_on := values.pop("email_enabled", None)) is not None:
        if email_on and not user.notify_email:
            raise ValidationError("Primero confirmá a qué email te llegan los avisos")
        user.email_notify_enabled = email_on
    for field, value in values.items():
        setattr(user, field, value)
    db.flush()
    return settings_for(db, user)


# ---------- Push ----------


def _allowed_endpoint(endpoint: str) -> bool:
    url = urlparse(endpoint)
    host = (url.hostname or "").lower()
    return url.scheme == "https" and any(host == h or host.endswith("." + h) for h in PUSH_HOSTS)


def subscribe(db: Session, user: User, data: PushSubscriptionIn) -> None:
    if not _allowed_endpoint(data.endpoint):
        raise ValidationError("Servicio de notificaciones no reconocido")
    stmt = insert(PushSubscription).values(
        user_id=user.id, endpoint=data.endpoint, p256dh=data.keys.p256dh, auth=data.keys.auth, label=data.label
    )
    # Si el mismo navegador se vuelve a suscribir (por ejemplo con otra cuenta), queda con la última.
    stmt = stmt.on_conflict_do_update(
        index_elements=["endpoint"],
        set_={"user_id": user.id, "p256dh": data.keys.p256dh, "auth": data.keys.auth, "label": data.label},
    )
    db.execute(stmt)


def unsubscribe_all(db: Session, user: User) -> None:
    """Ningún dispositivo vuelve a recibir avisos de esta cuenta (por ejemplo, un celular perdido)."""
    db.execute(delete(PushSubscription).where(PushSubscription.user_id == user.id))


def unsubscribe(db: Session, user: User, endpoint: str) -> None:
    db.execute(
        delete(PushSubscription).where(PushSubscription.user_id == user.id, PushSubscription.endpoint == endpoint)
    )


def _subject(user: User) -> str:
    public = get_settings().public_url
    return public if public.startswith("https://") else f"mailto:{user.email}"


def send_push(db: Session, user: User, title: str, body: str, url: str = "/", tag: str = "factura") -> int:
    subs = list(db.scalars(select(PushSubscription).where(PushSubscription.user_id == user.id)))
    if not subs:
        return 0
    vapid = _vapid(db)
    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag})
    sent = 0
    for sub in subs:
        info = {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}
        try:
            webpush(info, payload, vapid_private_key=vapid, vapid_claims={"sub": _subject(user)}, ttl=86400, timeout=10)
            sent += 1
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (404, 410):  # el navegador se dio de baja: se borra la suscripción
                db.delete(sub)
            else:
                logger.warning("Falló un push (%s): %s", status, exc)
        except Exception:  # red caída, DNS, etc.
            logger.exception("Falló un push")
    db.flush()
    return sent


# ---------- Telegram ----------


def _telegram(method: str, http_timeout: float = 10, **params: object) -> object:
    token = get_settings().telegram_bot_token
    if not token:
        raise NotFoundError("Telegram no está configurado")
    req = urllib.request.Request(
        f"{TELEGRAM_API}/bot{token}/{method}",
        data=json.dumps(params).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=http_timeout) as resp:
        body = json.loads(resp.read())
    if not body.get("ok"):
        raise RuntimeError(f"Telegram respondió: {body.get('description')}")
    return body["result"]


def _bot_username(db: Session) -> str:
    if name := _get_key(db, "telegram_bot_username"):
        return name
    me = _telegram("getMe")
    return _set_key(db, "telegram_bot_username", str(me["username"]))  # type: ignore[index]


def telegram_link(db: Session, user: User) -> TelegramLink:
    # 128 bits: cualquiera puede escribirle al bot, así que el código no se tiene que poder adivinar
    # probando (con 8 caracteres hexadecimales, alguien insistente podía terminar recibiendo tus avisos).
    code = secrets.token_urlsafe(16)
    user.telegram_link_code = code
    user.telegram_link_expires = datetime.now(UTC) + timedelta(minutes=LINK_MINUTES)
    db.flush()
    return TelegramLink(
        url=f"https://t.me/{_bot_username(db)}?start={code}", code=code, expires_at=user.telegram_link_expires
    )


def telegram_unlink(db: Session, user: User) -> None:
    user.telegram_chat_id = None
    user.telegram_link_code = None
    db.flush()


def send_telegram(user: User, text: str) -> bool:
    if not user.telegram_chat_id or not get_settings().telegram_bot_token:
        return False
    try:
        _telegram("sendMessage", chat_id=user.telegram_chat_id, text=text, disable_web_page_preview=True)
        return True
    except (urllib.error.URLError, RuntimeError, TimeoutError):
        logger.exception("Falló el envío a Telegram")
        return False


def poll_telegram(db: Session, timeout: int = 20) -> int:
    """Procesa los mensajes nuevos del bot (vinculación con "/start <código>"). Lo llama el worker."""
    offset = int(_get_key(db, "telegram_offset") or 0)
    updates = _telegram(
        "getUpdates", http_timeout=timeout + 10, offset=offset, timeout=timeout, allowed_updates=["message"]
    )
    handled = 0
    for update in updates:  # type: ignore[attr-defined]
        offset = max(offset, int(update["update_id"]) + 1)
        message = update.get("message") or {}
        chat_id = str((message.get("chat") or {}).get("id", ""))
        text = (message.get("text") or "").strip()
        if not chat_id:
            continue
        handled += 1
        if text.startswith("/start"):
            code = text.split(maxsplit=1)[1].strip() if " " in text else ""
            user = db.scalar(select(User).where(User.telegram_link_code == code)) if code else None
            if user and user.telegram_link_expires and user.telegram_link_expires > datetime.now(UTC):
                user.telegram_chat_id = chat_id
                user.telegram_link_code = None
                _reply(chat_id, "Listo: vas a recibir aquí los avisos de vencimientos y presupuestos de Factura.")
            else:
                _reply(chat_id, "El código no es válido o venció. Generá uno nuevo en Ajustes → Avisos.")
        elif text == "/stop":
            for user in db.scalars(select(User).where(User.telegram_chat_id == chat_id)):
                user.telegram_chat_id = None
            _reply(chat_id, "Listo, ya no vas a recibir avisos. Podés volver a vincular desde la app.")
    _set_key(db, "telegram_offset", str(offset))
    return handled


def _reply(chat_id: str, text: str) -> None:
    try:
        _telegram("sendMessage", chat_id=chat_id, text=text)
    except (urllib.error.URLError, RuntimeError, TimeoutError):
        logger.exception("No se pudo responder en Telegram")


# ---------- Email ----------


def _code_alive(user: User) -> bool:
    return bool(user.email_pending and user.email_code_expires and user.email_code_expires > datetime.now(UTC))


def _code_hash(user: User, address: str, code: str) -> str:
    # Ligado al usuario y a la dirección: un código no sirve para confirmar otra cuenta u otro email.
    return keyed_hash("email-code", f"{user.id}:{address}:{code}")


def email_start(db: Session, user: User, address: str) -> EmailStartOut:
    """Empieza a usar `address` para los avisos. Si no es el email de Google del usuario, manda un código."""
    if not mailer.available():
        raise NotConfiguredError("El envío de emails no está configurado en el servidor")
    address = address.strip().lower()
    if address in (user.google_email, user.notify_email):
        # Google ya verificó que esa dirección es de esta persona, o ya se confirmó con un código.
        user.notify_email, user.email_notify_enabled = address, True
        user.email_pending = user.email_code_hash = user.email_code_expires = None
        db.flush()
        return EmailStartOut(verified=True)
    code = f"{secrets.randbelow(1_000_000):06d}"
    user.email_pending = address
    user.email_code_hash = _code_hash(user, address, code)
    user.email_code_expires = datetime.now(UTC) + timedelta(minutes=EMAIL_CODE_MINUTES)
    db.flush()
    text = (
        f"Tu código para recibir los avisos de Factura en esta dirección es:\n\n    {code}\n\n"
        f"Vence en {EMAIL_CODE_MINUTES} minutos. Si no lo pediste, ignorá este correo: no se activa nada."
    )
    if not mailer.send_mail(address, "Factura: código de verificación", text):
        raise UpstreamError("No se pudo enviar el email. Revisá la configuración de correo del servidor.")
    return EmailStartOut(verified=False)


def email_confirm(db: Session, user: User, code: str) -> bool:
    """True si el código es el correcto y está vigente: la dirección pendiente pasa a ser el destino."""
    if not _code_alive(user) or not user.email_code_hash:
        raise ValidationError("El código venció. Pedí uno nuevo.")
    address = user.email_pending or ""
    if not secrets.compare_digest(user.email_code_hash, _code_hash(user, address, code)):
        return False
    user.notify_email, user.email_notify_enabled = address, True
    user.email_pending = user.email_code_hash = user.email_code_expires = None  # un solo uso
    db.flush()
    return True


def email_cancel_code(db: Session, user: User) -> None:
    """Anula el código pendiente (por ejemplo, después de demasiados intentos fallidos)."""
    user.email_pending = user.email_code_hash = user.email_code_expires = None
    db.flush()


def email_remove(db: Session, user: User) -> None:
    user.notify_email, user.email_notify_enabled = None, False
    email_cancel_code(db, user)


def send_email(user: User, title: str, body: str) -> bool:
    if not (user.email_notify_enabled and user.notify_email and mailer.available()):
        return False
    link = _link("/")
    text = f"{body}\n\n" + (f"Abrí Factura: {link}\n\n" if link.startswith("http") else "")
    text += "—\nTe llega porque activaste los avisos por email. Para dejar de recibirlos: Ajustes → Avisos."
    return mailer.send_mail(user.notify_email, title, text)


# ---------- Resumen de avisos ----------


def _link(path: str) -> str:
    base = get_settings().public_url.rstrip("/")
    return f"{base}{path}" if base else path


def _digest_text(items: list[Alert]) -> tuple[str, str]:
    urgent = sum(1 for a in items if a.level == AlertLevel.danger)
    title = f"Factura: {len(items)} aviso{'s' if len(items) != 1 else ''}" + (f" ({urgent} urgente)" if urgent else "")
    lines = [f"• {a.title} — {a.body}" for a in items[:DIGEST_MAX_LINES]]
    if len(items) > DIGEST_MAX_LINES:
        lines.append(f"… y {len(items) - DIGEST_MAX_LINES} más")
    return title, "\n".join(lines)


def _already_sent(db: Session, user: User, keys: list[str]) -> set[str]:
    if not keys:
        return set()
    stmt = select(NotificationLog.key).where(NotificationLog.user_id == user.id, NotificationLog.key.in_(keys))
    return set(db.scalars(stmt))


def _mark_sent(db: Session, user: User, keys: list[str]) -> None:
    if keys:
        stmt = insert(NotificationLog).values([{"user_id": user.id, "key": k} for k in keys])
        db.execute(stmt.on_conflict_do_nothing(constraint="uq_notification_user_key"))


def has_channel(db: Session, user: User) -> bool:
    if user.telegram_chat_id and get_settings().telegram_bot_token:
        return True
    if user.email_notify_enabled and user.notify_email and mailer.available():
        return True
    return db.scalar(select(PushSubscription.id).where(PushSubscription.user_id == user.id).limit(1)) is not None


def deliver(db: Session, user: User, now: datetime, *, digest: bool) -> int:
    """Manda los avisos que el usuario todavía no recibió. Devuelve cuántos avisos nuevos se mandaron.

    `digest=True` es el resumen diario (todos los avisos nuevos). Fuera del resumen solo se
    mandan los importantes (vencen hoy, atrasados, presupuesto superado).
    """
    today = now.date()
    current = alerts_service.compute(db, user, today)
    candidates = current if digest else [a for a in current if a.level != AlertLevel.info]
    sent_before = _already_sent(db, user, [a.key for a in candidates])
    new = [a for a in candidates if a.key not in sent_before]
    if not new:
        return 0
    title, body = _digest_text(new if not digest else current)
    pushed = send_push(db, user, title, body, url=_link(new[0].link), tag=f"avisos-{today.isoformat()}")
    texted = send_telegram(user, f"{title}\n\n{body}\n\n{_link('/')}")
    mailed = send_email(user, title, body)
    if pushed or texted or mailed:
        _mark_sent(db, user, [a.key for a in new])
        return len(new)
    return 0


def should_send_digest(db: Session, user: User, now: datetime) -> bool:
    if not user.notifications_enabled or not (user.notify_hour <= now.hour < QUIET_FROM_HOUR):
        return False
    return not _already_sent(db, user, [f"resumen:{now.date().isoformat()}"])


def run_digest(db: Session, user: User, now: datetime) -> int:
    sent = deliver(db, user, now, digest=True)
    _mark_sent(db, user, [f"resumen:{now.date().isoformat()}"])
    return sent


def test_send(db: Session, user: User) -> TestResult:
    title = "Factura: notificación de prueba"
    body = "Si ves esto, los avisos llegan bien a este dispositivo."
    return TestResult(
        push_sent=send_push(db, user, title, body, url="/ajustes?seccion=avisos", tag="prueba"),
        telegram_sent=send_telegram(user, f"{title}\n{body}"),
        email_sent=send_email(user, title, "Si ves esto, los avisos por email llegan bien."),
    )


def prune_log(db: Session, older_than: date) -> None:
    db.execute(delete(NotificationLog).where(NotificationLog.sent_at < older_than))
