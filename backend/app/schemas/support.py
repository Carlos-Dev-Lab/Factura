"""Esquemas de reglas, avisos, papelera, respaldos e importación."""

import datetime as dt
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, StringConstraints

from app.models import PaymentMethod, TransactionKind
from app.schemas.common import Amount, CategoryRef, Date, InputModel, Money, ORMModel, PositiveMoney, RefId

# ---------- Reglas de categorías ----------


class RuleMatch(StrEnum):
    ruc = "ruc"
    contains = "contains"


class RuleIn(InputModel):
    match: RuleMatch = RuleMatch.contains
    pattern: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
    category_id: RefId


class RuleOut(ORMModel):
    id: int
    match: RuleMatch
    pattern: str
    learned: bool
    category: CategoryRef


class SuggestionOut(BaseModel):
    category_id: int | None
    source: str | None  # "ruc", "regla", "historial" o "sugerencia"


# ---------- Avisos ----------


class AlertLevel(StrEnum):
    info = "info"
    warn = "warn"
    danger = "danger"


class Alert(BaseModel):
    key: str
    level: AlertLevel
    title: str
    body: str
    link: str
    date: dt.date | None = None


class NotificationSettings(BaseModel):
    notifications_enabled: bool
    notify_hour: int
    notify_days_before: int
    push_available: bool
    push_devices: int
    telegram_available: bool
    telegram_linked: bool
    email_available: bool
    email_enabled: bool
    email_address: str | None  # destino ya verificado
    email_pending: str | None  # dirección esperando el código


class NotificationSettingsUpdate(InputModel):
    notifications_enabled: bool | None = None
    email_enabled: bool | None = None
    notify_hour: int | None = Field(None, ge=0, le=23)
    notify_days_before: int | None = Field(None, ge=0, le=15)


class PushKeys(InputModel):
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)


class PushSubscriptionIn(InputModel):
    endpoint: str = Field(max_length=1000)
    keys: PushKeys
    label: str = Field("", max_length=80)


class PushUnsubscribeIn(InputModel):
    endpoint: str = Field(max_length=1000)


class TelegramLink(BaseModel):
    url: str
    code: str
    expires_at: dt.datetime


class EmailStartIn(InputModel):
    address: Annotated[EmailStr, Field(max_length=254)]


class EmailStartOut(BaseModel):
    # True: quedó activo sin código (es el email de tu cuenta de Google, que Google ya verificó).
    verified: bool


class EmailConfirmIn(InputModel):
    code: str = Field(pattern=r"^[0-9]{6}$")


class TestResult(BaseModel):
    push_sent: int
    telegram_sent: bool
    email_sent: bool


# ---------- Papelera ----------


class TrashOut(ORMModel):
    id: int
    entity: str
    label: str
    deleted_at: dt.datetime


class DeletedOut(BaseModel):
    """Respuesta de un borrado: permite ofrecer "Deshacer"."""

    trash_id: int


class RestoredOut(BaseModel):
    entity: str
    id: int


# ---------- Respaldos ----------


class BackupOut(BaseModel):
    name: str
    size: int
    created_at: dt.datetime


# ---------- Importación de extractos ----------


class ImportMapping(InputModel):
    """Qué columna (índice desde 0) contiene cada dato."""

    date: int = Field(ge=0)
    description: int | None = Field(None, ge=0)
    amount: int | None = Field(None, ge=0)  # una columna con signo (negativo = gasto)
    debit: int | None = Field(None, ge=0)  # o dos columnas: débito (gasto) y crédito (ingreso)
    credit: int | None = Field(None, ge=0)
    header_row: int = Field(0, ge=0)
    day_first: bool = True


class ImportRow(BaseModel):
    line: int
    date: dt.date | None
    description: str
    amount: Money | None
    kind: TransactionKind
    category_id: int | None
    duplicate: bool
    error: str | None


class ImportPreview(BaseModel):
    columns: list[str]
    mapping: ImportMapping | None
    rows: list[ImportRow]
    skipped: int


class ImportItem(InputModel):
    date: Date
    description: str = Field("", max_length=160)
    amount: PositiveMoney
    kind: TransactionKind
    category_id: RefId | None = None
    method: PaymentMethod = PaymentMethod.transfer


class ImportCommit(InputModel):
    account_id: RefId | None = None
    items: list[ImportItem] = Field(min_length=1, max_length=2000)


class ImportResult(BaseModel):
    created: int
    total: Amount
