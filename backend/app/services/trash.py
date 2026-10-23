"""Papelera: lo borrado se guarda 30 días y se puede restaurar (o "Deshacer" al instante).

Se guarda una foto (JSON) de la fila y de lo que dependía de ella, por ejemplo el
pago de una factura o los movimientos que tenían una categoría. Al restaurar se
vuelve a insertar con el mismo id y se rehacen esos vínculos.
"""

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, Numeric, delete, func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import Base, fetch, on_commit
from app.core.errors import ConflictError, NotFoundError
from app.models import (
    Account,
    Category,
    CategoryRule,
    Invoice,
    InvoiceStatus,
    ScheduledPayment,
    Transaction,
    TrashItem,
    User,
)
from app.services.storage import LocalStorage

# ---------- Serialización de filas ----------


def snapshot(obj: Base) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in obj.__table__.columns:
        value = getattr(obj, col.key)
        if isinstance(value, Decimal):
            value = str(value)
        elif isinstance(value, dt.date | dt.datetime):
            value = value.isoformat()
        elif hasattr(value, "value"):  # enums
            value = value.value
        out[col.key] = value
    return out


def _revive(model: type[Base], data: dict[str, Any]) -> Base:
    kwargs: dict[str, Any] = {}
    for col in model.__table__.columns:
        if col.key not in data:
            continue
        value = data[col.key]
        if value is not None:
            if isinstance(col.type, Numeric):
                value = Decimal(value)
            elif isinstance(col.type, DateTime):
                value = dt.datetime.fromisoformat(value)
            elif isinstance(col.type, Date):
                value = dt.date.fromisoformat(value)
        kwargs[col.key] = value
    return model(**kwargs)


def _add(db: Session, user: User, entity: str, label: str, payload: dict, file_key: str | None = None) -> TrashItem:
    item = TrashItem(user_id=user.id, entity=entity, label=label[:200], payload=payload, file_key=file_key)
    db.add(item)
    db.flush()
    return item


# ---------- Mandar a la papelera ----------


def trash_transaction(db: Session, user: User, tx: Transaction) -> TrashItem:
    label = tx.description or (tx.category.name if tx.category else "Movimiento")
    return _add(db, user, "transaction", f"{label} · {tx.amount:,.0f}".replace(",", "."), {"row": snapshot(tx)})


def trash_invoice(db: Session, user: User, inv: Invoice, payment: Transaction | None) -> TrashItem:
    payload = {"row": snapshot(inv), "payment": snapshot(payment) if payment else None}
    label = " ".join(p for p in ("Factura", inv.supplier, inv.number) if p)
    return _add(db, user, "invoice", label, payload, file_key=inv.file_key)


def trash_scheduled(db: Session, user: User, sp: ScheduledPayment) -> TrashItem:
    linked = list(db.scalars(select(Transaction.id).where(Transaction.scheduled_payment_id == sp.id)))
    return _add(db, user, "scheduled", f"Pago fijo {sp.name}", {"row": snapshot(sp), "transactions": linked})


def trash_category(db: Session, user: User, cat: Category) -> TrashItem:
    def ids(model: type[Base]) -> list[int]:
        return list(db.scalars(select(model.id).where(model.category_id == cat.id)))  # type: ignore[attr-defined]

    rules = [snapshot(r) for r in db.scalars(select(CategoryRule).where(CategoryRule.category_id == cat.id))]
    payload = {
        "row": snapshot(cat),
        "transactions": ids(Transaction),
        "invoices": ids(Invoice),
        "scheduled": ids(ScheduledPayment),
        "rules": rules,
    }
    return _add(db, user, "category", f"Categoría {cat.name}", payload)


# ---------- Restaurar ----------


def list_items(db: Session, user: User) -> list[TrashItem]:
    stmt = select(TrashItem).where(TrashItem.user_id == user.id).order_by(TrashItem.deleted_at.desc())
    return list(db.scalars(stmt.limit(200)))


def _get(db: Session, user: User, item_id: int) -> TrashItem:
    # Bloqueado: dos "Restaurar" a la vez reinsertaban la misma fila y fallaban con error 500.
    item = fetch(db, TrashItem, item_id, lock=True)
    if not item or item.user_id != user.id:
        raise NotFoundError("Elemento de la papelera")
    return item


def _exists(db: Session, model: type[Base], obj_id: int | None, user: User) -> bool:
    if obj_id is None:
        return False
    row = db.get(model, obj_id)
    return row is not None and row.user_id == user.id  # type: ignore[attr-defined]


def _clean_links(db: Session, user: User, row: dict[str, Any]) -> dict[str, Any]:
    """Quita referencias a cosas que ya no existen (una categoría borrada después, etc.)."""
    row = dict(row)
    for key, model in (("category_id", Category), ("account_id", Account)):
        if key in row and not _exists(db, model, row[key], user):
            row[key] = None
    return row


def _insert(db: Session, model: type[Base], row: dict[str, Any]) -> Base:
    if db.get(model, row["id"]) is not None:
        raise ConflictError("Ya existe un elemento con ese identificador")
    obj = _revive(model, row)
    db.add(obj)
    db.flush()
    return obj


def restore(db: Session, user: User, item_id: int) -> tuple[str, int]:
    item = _get(db, user, item_id)
    payload = item.payload
    row = _clean_links(db, user, payload["row"])
    if row.get("user_id") != user.id:  # pragma: no cover - defensa en profundidad
        raise NotFoundError("Elemento de la papelera")

    if item.entity == "transaction":
        _restore_transaction(db, user, row)
    elif item.entity == "invoice":
        _insert(db, Invoice, row)
        if payment := payload.get("payment"):
            _insert(db, Transaction, _clean_links(db, user, payment))
    elif item.entity == "scheduled":
        _insert(db, ScheduledPayment, row)
        _relink(db, user, Transaction, "scheduled_payment_id", row["id"], payload.get("transactions", []))
    elif item.entity == "category":
        clash = db.scalar(
            select(Category.id).where(
                Category.user_id == user.id,
                func.lower(Category.name) == row["name"].lower(),
                Category.kind == row["kind"],
            )
        )
        if clash:
            raise ConflictError(f"Ya existe otra categoría llamada «{row['name']}»")
        _insert(db, Category, row)
        for model, key in ((Transaction, "transactions"), (Invoice, "invoices"), (ScheduledPayment, "scheduled")):
            _relink(db, user, model, "category_id", row["id"], payload.get(key, []))
        for rule in payload.get("rules", []):
            if not db.get(CategoryRule, rule["id"]):
                db.add(_revive(CategoryRule, rule))
    else:  # pragma: no cover
        raise NotFoundError("Elemento de la papelera")

    entity, obj_id = item.entity, row["id"]
    db.delete(item)
    db.flush()
    return entity, obj_id


def _restore_transaction(db: Session, user: User, row: dict[str, Any]) -> None:
    invoice_id = row.get("invoice_id")
    invoice = db.get(Invoice, invoice_id) if invoice_id else None
    if invoice is None or invoice.user_id != user.id:
        row["invoice_id"] = None  # la factura ya no está: vuelve como un gasto común
    elif invoice.status == InvoiceStatus.paid:
        # Se volvió a pagar después de borrar este pago: restaurarlo contaría el gasto dos veces.
        name = invoice.supplier or "la factura"
        raise ConflictError(f"{name} ya tiene otro pago registrado: restaurar este lo duplicaría.")
    sp_id = row.get("scheduled_payment_id")
    if not _exists(db, ScheduledPayment, sp_id, user):
        row["scheduled_payment_id"] = None
    else:
        day = dt.date.fromisoformat(row["date"])
        first = day.replace(day=1)
        last = (first + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
        repaid = db.scalar(
            select(Transaction.id).where(
                Transaction.user_id == user.id,
                Transaction.scheduled_payment_id == sp_id,
                Transaction.date.between(first, last),
            )
        )
        if repaid:
            from app.services.alerts import MONTH_NAMES  # import local: alerts depende de muchos servicios

            sp = db.get(ScheduledPayment, sp_id)
            raise ConflictError(
                f"«{sp.name}» ya tiene un pago registrado en {MONTH_NAMES[first.month - 1]}: "  # type: ignore[union-attr]
                "restaurar este lo duplicaría."
            )
    _insert(db, Transaction, row)
    if row["invoice_id"] and invoice is not None:
        # Era el pago de la factura: al volver, la factura queda pagada otra vez.
        invoice.status = InvoiceStatus.paid
        invoice.paid_on = dt.date.fromisoformat(row["date"])


def _relink(db: Session, user: User, model: type[Base], column: str, value: int, ids: list[int]) -> None:
    if not ids:
        return
    col = getattr(model, column)
    db.execute(
        update(model)
        .where(model.id.in_(ids), model.user_id == user.id, col.is_(None))  # type: ignore[attr-defined]
        .values({column: value})
    )


# ---------- Vaciar ----------


def remove(db: Session, user: User, storage: LocalStorage, item_id: int) -> None:
    _purge_items(db, storage, [_get(db, user, item_id)])


def empty(db: Session, user: User, storage: LocalStorage) -> int:
    items = list(db.scalars(select(TrashItem).where(TrashItem.user_id == user.id)))
    _purge_items(db, storage, items)
    return len(items)


def purge_expired(db: Session, storage: LocalStorage) -> int:
    """Borra definitivamente lo que lleva más de `trash_days` en la papelera (lo llama el worker)."""
    limit = dt.datetime.now(dt.UTC) - dt.timedelta(days=get_settings().trash_days)
    items = list(db.scalars(select(TrashItem).where(TrashItem.deleted_at < limit)))
    _purge_items(db, storage, items)
    return len(items)


def _purge_items(db: Session, storage: LocalStorage, items: list[TrashItem]) -> None:
    files = [(i.user_id, i.file_key) for i in items if i.file_key]
    if items:
        db.execute(delete(TrashItem).where(TrashItem.id.in_([i.id for i in items])))
        db.flush()
    for user_id, key in files:
        # El archivo de una factura se borra recién cuando su foto sale de la papelera.
        on_commit(db, lambda u=user_id, k=key: storage.delete(u, k))


def held_file_keys(db: Session, user: User) -> set[str]:
    """Archivos de facturas en la papelera: no se consideran abandonados."""
    stmt = select(TrashItem.file_key).where(TrashItem.user_id == user.id, TrashItem.file_key.is_not(None))
    return set(db.scalars(stmt))
