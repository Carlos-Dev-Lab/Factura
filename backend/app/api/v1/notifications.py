from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.api.deps import DB, CurrentUser, EmailCodeLimiter, EmailSendLimiter, verify_csrf
from app.core.errors import TooManyRequestsError
from app.schemas.support import (
    Alert,
    EmailConfirmIn,
    EmailStartIn,
    EmailStartOut,
    NotificationSettings,
    NotificationSettingsUpdate,
    PushSubscriptionIn,
    PushUnsubscribeIn,
    TelegramLink,
    TestResult,
)
from app.services import alerts, notify

router = APIRouter(tags=["avisos"], dependencies=[Depends(verify_csrf)])


@router.get("/alerts", response_model=list[Alert])
def list_alerts(user: CurrentUser, db: DB) -> list[Alert]:
    """Avisos de hoy: vencimientos cercanos o atrasados y presupuestos al límite."""
    return alerts.compute(db, user)


@router.get("/notifications/settings", response_model=NotificationSettings)
def get_settings_(user: CurrentUser, db: DB) -> NotificationSettings:
    return notify.settings_for(db, user)


@router.patch("/notifications/settings", response_model=NotificationSettings)
def update_settings(data: NotificationSettingsUpdate, user: CurrentUser, db: DB) -> NotificationSettings:
    return notify.update_settings(db, user, data)


@router.get("/notifications/push/key")
def push_key(user: CurrentUser, db: DB) -> dict[str, str]:
    return {"public_key": notify.public_key(db)}


@router.post("/notifications/push", status_code=status.HTTP_204_NO_CONTENT)
def push_subscribe(data: PushSubscriptionIn, user: CurrentUser, db: DB) -> None:
    notify.subscribe(db, user, data)


@router.post("/notifications/push/remove", status_code=status.HTTP_204_NO_CONTENT)
def push_unsubscribe(data: PushUnsubscribeIn, user: CurrentUser, db: DB) -> None:
    notify.unsubscribe(db, user, data.endpoint)


@router.post("/notifications/telegram", response_model=TelegramLink)
def telegram_link(user: CurrentUser, db: DB) -> TelegramLink:
    return notify.telegram_link(db, user)


@router.delete("/notifications/telegram", status_code=status.HTTP_204_NO_CONTENT)
def telegram_unlink(user: CurrentUser, db: DB) -> None:
    notify.telegram_unlink(db, user)


@router.post("/notifications/email", response_model=EmailStartOut)
def email_start(
    data: EmailStartIn, user: CurrentUser, db: DB, sends: EmailSendLimiter, codes: EmailCodeLimiter
) -> EmailStartOut:
    """Elegir a qué email llegan los avisos. Manda un código, salvo que Google ya haya verificado la dirección."""
    key = f"email-send:{user.id}"
    if sends.is_blocked(key):
        raise TooManyRequestsError("Ya pediste varios códigos. Esperá unos minutos y volvé a probar.")
    result = notify.email_start(db, user, data.address)
    if not result.verified:
        sends.hit(key)
        codes.reset(f"email-code:{user.id}")  # código nuevo: se vuelve a contar desde cero
    return result


@router.post("/notifications/email/confirm", response_model=NotificationSettings)
def email_confirm(
    data: EmailConfirmIn, user: CurrentUser, db: DB, codes: EmailCodeLimiter
) -> NotificationSettings | JSONResponse:
    key = f"email-code:{user.id}"
    if not codes.is_blocked(key) and notify.email_confirm(db, user, data.code):
        codes.reset(key)
        return notify.settings_for(db, user)
    codes.hit(key)  # queda registrado aunque el pedido termine en error (conexión propia)
    if codes.is_blocked(key):
        # Al quinto intento el código se anula. Se responde sin lanzar un error para que la
        # anulación se guarde (un error revierte la transacción).
        notify.email_cancel_code(db, user)
        return JSONResponse({"detail": "Demasiados intentos. Pedí un código nuevo."}, status_code=429)
    return JSONResponse({"detail": "El código no es correcto"}, status_code=422)


@router.delete("/notifications/email", status_code=status.HTTP_204_NO_CONTENT)
def email_remove(user: CurrentUser, db: DB) -> None:
    notify.email_remove(db, user)


@router.post("/notifications/test", response_model=TestResult)
def send_test(user: CurrentUser, db: DB) -> TestResult:
    return notify.test_send(db, user)
