from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.core.database import contains_pattern, fetch
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models import Category, CategoryKind, Invoice, InvoiceStatus, ScheduledPayment, Transaction, TransactionKind, User
from app.schemas.scheduled import ScheduledIn
from app.schemas.transaction import TransactionIn, TransactionUpdate
from app.services import accounts, categories, invoices, rules, scheduled
from app.services.dates import month_key, month_start


def _category_kind(kind: TransactionKind) -> CategoryKind:
    return CategoryKind(kind.value)


def get_owned(db: Session, user: User, tx_id: int, *, lock: bool = False) -> Transaction:
    tx = fetch(db, Transaction, tx_id, lock=lock)
    if not tx or tx.user_id != user.id:
        raise NotFoundError("Movimiento")
    return tx


def list_transactions(
    db: Session,
    user: User,
    *,
    start: date | None,
    end: date | None,
    kind: TransactionKind | None,
    q: str | None,
    limit: int,
    offset: int,
    account_id: int | None = None,
    category_id: int | None = None,
) -> tuple[list[Transaction], int, Decimal, Decimal]:
    """Devuelve (página, total de resultados, suma de gastos, suma de ingresos) del filtro."""
    stmt = select(Transaction).where(Transaction.user_id == user.id)
    if start:
        stmt = stmt.where(Transaction.date >= start)
    if end:
        stmt = stmt.where(Transaction.date <= end)
    if kind:
        stmt = stmt.where(Transaction.kind == kind)
    if account_id:
        stmt = stmt.where(Transaction.account_id == account_id)
    if category_id:
        stmt = stmt.where(Transaction.category_id == category_id)
    if q:
        like = contains_pattern(q)
        stmt = stmt.outerjoin(Category, Transaction.category_id == Category.id).where(
            or_(Transaction.description.ilike(like, escape="\\"), Category.name.ilike(like, escape="\\"))
        )
    sub = stmt.subquery()
    expense = func.coalesce(func.sum(case((sub.c.kind == TransactionKind.expense.value, sub.c.amount))), 0)
    income = func.coalesce(func.sum(case((sub.c.kind == TransactionKind.income.value, sub.c.amount))), 0)
    total, expense_total, income_total = db.execute(select(func.count(), expense, income).select_from(sub)).one()
    items = db.scalars(stmt.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(limit).offset(offset))
    return list(items), total, Decimal(expense_total), Decimal(income_total)


def create(db: Session, user: User, data: TransactionIn, *, learn: bool = True) -> Transaction:
    description = data.description.strip()
    category_id = categories.resolve(db, user, data.category_id, _category_kind(data.kind))
    tx = Transaction(
        user_id=user.id,
        kind=data.kind,
        amount=data.amount,
        date=data.date,
        description=description,
        method=data.method,
        category_id=category_id,
        account_id=accounts.resolve(db, user, data.account_id),
    )
    db.add(tx)
    db.flush()
    if learn:
        rules.learn_from_text(db, user, description, category_id)
    db.refresh(tx)
    return tx


def schedule_expense(db: Session, user: User, tx_id: int, data: ScheduledIn) -> ScheduledPayment:
    """Crea la recurrencia y vincula el gasto existente sin registrar otro movimiento."""
    tx = get_owned(db, user, tx_id, lock=True)
    if tx.kind != TransactionKind.expense or data.kind != TransactionKind.expense:
        raise ValidationError("Solo se puede convertir un gasto en un pago fijo")
    if tx.scheduled_payment_id is not None or tx.invoice_id is not None:
        raise ConflictError("El gasto ya está vinculado a un pago fijo o a una factura")

    paid_month = tx.date.replace(day=1)
    earliest_start = max(paid_month, date.today().replace(day=1))
    start = month_start(data.start_month) if data.start_month else earliest_start
    if start < earliest_start:
        raise ValidationError(f"El pago fijo puede empezar desde {month_key(earliest_start)}")
    payment = scheduled.create(db, user, data.model_copy(update={"start_month": month_key(start)}))
    tx.scheduled_payment_id = payment.id
    tx.scheduled_month = paid_month
    db.flush()
    return payment


def _check_linked_change(tx: Transaction, changes: dict) -> None:
    """Un pago de factura o de pago fijo tiene reglas propias para no desincronizarse."""
    if tx.invoice_id is None and tx.scheduled_payment_id is None:
        return
    if changes.get("kind") not in (None, tx.kind):
        raise ValidationError("El tipo de un pago de factura o de un pago fijo no se puede cambiar")
    new_date = changes.get("date")
    if tx.scheduled_payment_id is not None and new_date:
        period = tx.scheduled_month or tx.date.replace(day=1)
        if new_date < period:
            raise ValidationError("La fecha de pago no puede ser anterior al mes de la cuota")
        tx.scheduled_month = period


def update(db: Session, user: User, tx_id: int, data: TransactionUpdate) -> Transaction:
    tx = get_owned(db, user, tx_id, lock=True)
    changes = data.model_dump(exclude_unset=True)
    _check_linked_change(tx, changes)
    for field in ("kind", "amount", "date", "method"):
        if changes.get(field) is not None:
            setattr(tx, field, changes[field])
    if changes.get("description") is not None:
        tx.description = changes["description"].strip()
    if "account_id" in changes:
        tx.account_id = accounts.resolve(db, user, changes["account_id"])
    if "category_id" in changes or "kind" in changes:
        cat_id = changes.get("category_id", tx.category_id)
        tx.category_id = categories.resolve(db, user, cat_id, _category_kind(tx.kind))
        if "category_id" in changes and tx.invoice_id is None and tx.scheduled_payment_id is None:
            rules.learn_from_text(db, user, tx.description, tx.category_id)
    if tx.invoice_id is not None and (invoice := fetch(db, Invoice, tx.invoice_id, lock=True)):
        # La factura pagada refleja lo que se corrigió en su pago.
        if tx.amount != invoice.total:
            invoices.check_taxes(invoice, total=tx.amount)
        invoice.total = tx.amount
        invoice.paid_on = tx.date
        invoice.category_id = tx.category_id
    db.flush()
    db.refresh(tx)
    return tx


def delete(db: Session, user: User, tx_id: int) -> int:
    """Manda el movimiento a la papelera y devuelve el id del elemento de la papelera."""
    from app.services import trash

    tx = get_owned(db, user, tx_id, lock=True)
    item = trash.trash_transaction(db, user, tx)
    if tx.invoice_id is not None:
        # Borrar el pago de una factura la vuelve a dejar pendiente.
        invoice = db.get(Invoice, tx.invoice_id)
        if invoice:
            invoice.status = InvoiceStatus.pending
            invoice.paid_on = None
    db.delete(tx)
    db.flush()
    return item.id
