"""Pagos y cobros fijos mensuales: alquiler, servicios, cuotas, sueldo."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import fetch
from app.core.errors import NotFoundError, ValidationError
from app.models import CategoryKind, ScheduledPayment, Transaction, TransactionKind, User
from app.schemas.scheduled import PaymentHistoryItem, ScheduledHistory, ScheduledIn, ScheduledPayIn, ScheduledUpdate
from app.services import accounts, categories
from app.services.dates import day_in_month, month_range, month_start, months_between

HISTORY_SIZE = 12

__all__ = ["month_range"]  # se reexporta por compatibilidad con módulos que lo importan desde aquí


def occurrence(payment: ScheduledPayment, first_of_month: date) -> date:
    """Fecha del pago en el mes; el día 31 se ajusta al último día de meses cortos."""
    return day_in_month(first_of_month, payment.day_of_month)


def applies_to(payment: ScheduledPayment, first_of_month: date) -> bool:
    """True si el mes está dentro del período del pago (desde su inicio hasta la última cuota)."""
    if first_of_month < payment.start_month:
        return False
    return payment.end_month is None or first_of_month <= payment.end_month


def installment_label(payment: ScheduledPayment, first_of_month: date) -> str | None:
    """ "Cuota 3 de 12" para planes con fin; None si el pago no termina."""
    if payment.end_month is None:
        return None
    number = months_between(payment.start_month, first_of_month) + 1
    total = months_between(payment.start_month, payment.end_month) + 1
    return f"Cuota {number} de {total}"


def get_owned(db: Session, user: User, payment_id: int, *, lock: bool = False) -> ScheduledPayment:
    sp = fetch(db, ScheduledPayment, payment_id, lock=lock)
    if not sp or sp.user_id != user.id:
        raise NotFoundError("Pago fijo")
    return sp


def list_payments(db: Session, user: User, *, only_active: bool = False) -> list[ScheduledPayment]:
    stmt = select(ScheduledPayment).where(ScheduledPayment.user_id == user.id)
    if only_active:
        stmt = stmt.where(ScheduledPayment.active.is_(True))
    return list(db.scalars(stmt.order_by(ScheduledPayment.kind, ScheduledPayment.day_of_month, ScheduledPayment.id)))


def paid_in_range(db: Session, user: User, start: date, end: date) -> dict[int, Decimal]:
    """Monto registrado por cada pago fijo dentro del rango."""
    rows = db.execute(
        select(Transaction.scheduled_payment_id, Transaction.amount).where(
            Transaction.user_id == user.id,
            Transaction.scheduled_payment_id.is_not(None),
            Transaction.date.between(start, end),
        )
    )
    return {sp_id: amount for sp_id, amount in rows}


def paid_ids_in_range(db: Session, user: User, start: date, end: date) -> set[int]:
    return set(paid_in_range(db, user, start, end))


def _period(start: str | None, end: str | None) -> tuple[date, date | None]:
    first = month_start(start) if start else date.today().replace(day=1)
    last = month_start(end) if end else None
    if last is not None and last < first:
        raise ValidationError("El último mes no puede ser anterior al primero")
    return first, last


def create(db: Session, user: User, data: ScheduledIn) -> ScheduledPayment:
    start, end = _period(data.start_month, data.end_month)
    sp = ScheduledPayment(
        user_id=user.id,
        name=data.name.strip(),
        kind=data.kind,
        amount=data.amount,
        variable_amount=data.variable_amount,
        day_of_month=data.day_of_month,
        start_month=start,
        end_month=end,
        active=data.active,
        category_id=categories.resolve(db, user, data.category_id, CategoryKind(data.kind.value)),
        account_id=accounts.resolve(db, user, data.account_id),
    )
    db.add(sp)
    db.flush()
    db.refresh(sp)
    return sp


def update(db: Session, user: User, payment_id: int, data: ScheduledUpdate) -> ScheduledPayment:
    sp = get_owned(db, user, payment_id, lock=True)
    changes = data.model_dump(exclude_unset=True)
    if "start_month" in changes or "end_month" in changes:
        start = changes.pop("start_month", None) or sp.start_month.strftime("%Y-%m")
        end = changes.pop("end_month") if "end_month" in changes else (sp.end_month and sp.end_month.strftime("%Y-%m"))
        sp.start_month, sp.end_month = _period(start, end)
    if changes.get("kind") is not None:
        sp.kind = changes.pop("kind")
    changes.pop("kind", None)
    if "account_id" in changes:
        sp.account_id = accounts.resolve(db, user, changes.pop("account_id"))
    # La categoría tiene que coincidir con el tipo (gasto/ingreso), también si cambió el tipo.
    cat_id = changes.pop("category_id", sp.category_id)
    sp.category_id = categories.resolve(db, user, cat_id, CategoryKind(sp.kind.value)) if cat_id else None
    for field, value in changes.items():
        if value is not None:
            setattr(sp, field, value.strip() if isinstance(value, str) else value)
    db.flush()
    db.refresh(sp)
    return sp


def delete(db: Session, user: User, payment_id: int) -> int:
    from app.services import trash

    sp = get_owned(db, user, payment_id, lock=True)
    item = trash.trash_scheduled(db, user, sp)
    db.delete(sp)
    db.flush()
    return item.id


def history(db: Session, user: User, payment_id: int) -> ScheduledHistory:
    sp = get_owned(db, user, payment_id)
    rows = db.scalars(
        select(Transaction)
        .where(Transaction.user_id == user.id, Transaction.scheduled_payment_id == sp.id)
        .order_by(Transaction.date.desc())
        .limit(HISTORY_SIZE)
    )
    items = [PaymentHistoryItem(transaction_id=t.id, date=t.date, amount=t.amount) for t in rows]
    average = (sum((i.amount for i in items), Decimal(0)) / len(items)).quantize(Decimal("0.01")) if items else None
    return ScheduledHistory(items=items, last_amount=items[0].amount if items else None, average=average)


def pay(db: Session, user: User, payment_id: int, data: ScheduledPayIn) -> Transaction:
    """Registra el pago (o cobro) del mes indicado. Es idempotente: no duplica si ya estaba registrado."""
    sp = get_owned(db, user, payment_id, lock=True)
    start, end = month_range(data.month)
    if data.paid_on and not start <= data.paid_on <= end:
        raise ValidationError("La fecha de pago debe estar dentro del mes indicado")
    if not applies_to(sp, start):
        raise ValidationError("Ese mes está fuera del período de este pago fijo")
    existing = db.scalar(
        select(Transaction).where(
            Transaction.user_id == user.id,
            Transaction.scheduled_payment_id == sp.id,
            Transaction.date.between(start, end),
        )
    )
    if existing:
        return existing
    detail = installment_label(sp, start)
    tx = Transaction(
        user_id=user.id,
        kind=sp.kind if isinstance(sp.kind, TransactionKind) else TransactionKind(sp.kind),
        amount=data.amount or sp.amount,
        date=data.paid_on or occurrence(sp, start),
        method=data.method,
        category_id=sp.category_id,
        account_id=accounts.resolve(db, user, data.account_id) if data.account_id else sp.account_id,
        description=f"{sp.name} · {detail}"[:160] if detail else sp.name,
        scheduled_payment_id=sp.id,
    )
    db.add(tx)
    db.flush()
    db.refresh(tx)
    return tx
