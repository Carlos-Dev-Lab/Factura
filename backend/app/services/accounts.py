"""Cuentas (efectivo, banco, tarjeta, billetera), sus saldos y transferencias entre ellas."""

from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import fetch
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models import Account, AccountType, Transaction, TransactionKind, Transfer, User
from app.schemas.account import AccountIn, AccountOut, AccountUpdate, CardStatus, TransferIn, TransferOut
from app.schemas.common import AccountRef
from app.services.dates import add_months, day_in_month

ZERO = Decimal(0)
DEFAULT_ACCOUNTS: list[tuple[str, AccountType, str]] = [("Efectivo", AccountType.cash, "#3EE6B0")]


def seed_defaults(db: Session, user: User) -> None:
    db.add_all(Account(user_id=user.id, name=n, type=t, color=c) for n, t, c in DEFAULT_ACCOUNTS)


def get_owned(db: Session, user: User, account_id: int, *, lock: bool = False) -> Account:
    acc = fetch(db, Account, account_id, lock=lock)
    if not acc or acc.user_id != user.id:
        raise NotFoundError("Cuenta")
    return acc


def resolve(db: Session, user: User, account_id: int | None) -> int | None:
    """Valida que la cuenta exista, sea del usuario y no esté archivada."""
    if account_id is None:
        return None
    acc = get_owned(db, user, account_id)
    if acc.archived:
        raise ValidationError("La cuenta está archivada")
    return acc.id


# ---------- Saldos ----------


def _balances(db: Session, user: User, until: date | None = None) -> dict[int, tuple[Decimal, int]]:
    """(saldo, cantidad de movimientos) por cuenta, opcionalmente hasta una fecha inclusive."""
    signed = case((Transaction.kind == TransactionKind.income, Transaction.amount), else_=-Transaction.amount)
    tx = select(Transaction.account_id, func.coalesce(func.sum(signed), 0), func.count()).where(
        Transaction.user_id == user.id, Transaction.account_id.is_not(None)
    )
    out_tr = select(Transfer.from_account_id, func.coalesce(func.sum(Transfer.amount), 0), func.count()).where(
        Transfer.user_id == user.id
    )
    in_tr = select(Transfer.to_account_id, func.coalesce(func.sum(Transfer.amount), 0), func.count()).where(
        Transfer.user_id == user.id
    )
    if until is not None:
        tx, out_tr, in_tr = (
            tx.where(Transaction.date <= until),
            out_tr.where(Transfer.date <= until),
            in_tr.where(Transfer.date <= until),
        )
    totals: dict[int, tuple[Decimal, int]] = {}

    def add(rows: object, sign: int) -> None:
        for acc_id, amount, count in rows:  # type: ignore[attr-defined]
            bal, n = totals.get(acc_id, (ZERO, 0))
            totals[acc_id] = (bal + sign * Decimal(amount), n + count)

    add(db.execute(tx.group_by(Transaction.account_id)), 1)
    add(db.execute(out_tr.group_by(Transfer.from_account_id)), -1)
    add(db.execute(in_tr.group_by(Transfer.to_account_id)), 1)
    return totals


def _closing_on_or_before(day: int, ref: date) -> date:
    this_month = day_in_month(ref.replace(day=1), day)
    if this_month <= ref:
        return this_month
    return day_in_month(add_months(ref.replace(day=1), -1), day)


def card_cycle(acc: Account, today: date) -> tuple[date, date, date]:
    """(último cierre, próximo cierre, vencimiento del último resumen)."""
    assert acc.closing_day and acc.due_day
    last_close = _closing_on_or_before(acc.closing_day, today)
    next_close = day_in_month(add_months(last_close.replace(day=1), 1), acc.closing_day)
    # El vencimiento cae después del cierre: el mismo mes si el día es mayor, si no, el siguiente.
    due_month = last_close.replace(day=1) if acc.due_day > acc.closing_day else add_months(last_close.replace(day=1), 1)
    return last_close, next_close, day_in_month(due_month, acc.due_day)


def card_status(db: Session, user: User, acc: Account, balance: Decimal, today: date) -> CardStatus:
    last_close, next_close, due = card_cycle(acc, today)
    # El saldo inicial es la deuda del día en que se cargó la tarjeta: entra en el primer resumen que
    # cierre después de esa fecha. Antes se sumaba al último resumen ya cerrado y una tarjeta recién
    # cargada con deuda aparecía al instante como "vencida".
    opened = acc.created_at.astimezone().date() if acc.created_at else today
    opening = acc.opening_balance if opened <= last_close else ZERO
    at_close = opening + _balances(db, user, until=last_close).get(acc.id, (ZERO, 0))[0]
    payments_after = (
        db.scalar(
            select(func.coalesce(func.sum(Transfer.amount), 0)).where(
                Transfer.user_id == user.id, Transfer.to_account_id == acc.id, Transfer.date > last_close
            )
        )
        or ZERO
    )
    spent_after = (
        db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user.id,
                Transaction.account_id == acc.id,
                Transaction.kind == TransactionKind.expense,
                Transaction.date > last_close,
            )
        )
        or ZERO
    )
    debt = max(ZERO, -balance)
    statement = max(ZERO, -at_close - Decimal(payments_after))
    available = max(ZERO, acc.credit_limit - debt) if acc.credit_limit else None
    # Vencimiento del resumen que cierra en `next_close` (el que se muestra si no hay nada pendiente).
    _, _, next_due = card_cycle(acc, next_close)
    return CardStatus(
        last_closing=last_close,
        next_closing=next_close,
        due_date=due,
        next_due_date=next_due,
        statement_amount=statement,
        current_period=Decimal(spent_after),
        debt=debt,
        available=available,
    )


def to_out(db: Session, user: User, acc: Account, totals: dict[int, tuple[Decimal, int]], today: date) -> AccountOut:
    moved, count = totals.get(acc.id, (ZERO, 0))
    out = AccountOut.model_validate(acc)
    out.balance = acc.opening_balance + moved
    out.movement_count = count
    if acc.type == AccountType.card and acc.closing_day and acc.due_day:
        out.card = card_status(db, user, acc, out.balance, today)
    return out


def list_accounts(db: Session, user: User, *, include_archived: bool = True) -> list[AccountOut]:
    stmt = select(Account).where(Account.user_id == user.id)
    if not include_archived:
        stmt = stmt.where(Account.archived.is_(False))
    accounts = list(db.scalars(stmt.order_by(Account.archived, Account.id)))
    totals = _balances(db, user)
    today = date.today()
    return [to_out(db, user, a, totals, today) for a in accounts]


def get_out(db: Session, user: User, account_id: int) -> AccountOut:
    return to_out(db, user, get_owned(db, user, account_id), _balances(db, user), date.today())


# ---------- Alta, edición y baja ----------


def _flush_unique(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        raise ConflictError("Ya tenés una cuenta con ese nombre") from exc


def _check_name(db: Session, user: User, name: str, exclude_id: int | None = None) -> None:
    """Sin cuentas repetidas aunque cambien mayúsculas ("Banco" y "banco")."""
    stmt = select(Account.id).where(Account.user_id == user.id, func.lower(Account.name) == name.strip().lower())
    if exclude_id is not None:
        stmt = stmt.where(Account.id != exclude_id)
    if db.scalar(stmt):
        raise ConflictError("Ya tenés una cuenta con ese nombre")


def create(db: Session, user: User, data: AccountIn) -> AccountOut:
    _check_name(db, user, data.name)
    is_card = data.type == AccountType.card
    acc = Account(
        user_id=user.id,
        name=data.name,
        type=data.type,
        color=data.color,
        opening_balance=data.opening_balance,
        closing_day=data.closing_day if is_card else None,
        due_day=data.due_day if is_card else None,
        credit_limit=data.credit_limit if is_card else None,
    )
    db.add(acc)
    _flush_unique(db)
    return get_out(db, user, acc.id)


def update(db: Session, user: User, account_id: int, data: AccountUpdate) -> AccountOut:
    acc = get_owned(db, user, account_id, lock=True)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("name"):
        _check_name(db, user, changes["name"], exclude_id=acc.id)
    card_fields = {"closing_day", "due_day", "credit_limit"}
    for field, value in changes.items():
        if field in card_fields and acc.type != AccountType.card:
            continue
        if value is None and field not in ("credit_limit",):
            continue
        setattr(acc, field, value)
    if acc.type == AccountType.card and (acc.closing_day is None or acc.due_day is None):
        raise ValidationError("Una tarjeta de crédito necesita día de cierre y de vencimiento")
    _flush_unique(db)
    return get_out(db, user, acc.id)


def delete(db: Session, user: User, account_id: int) -> None:
    """Solo se borra una cuenta sin movimientos; si tiene historia, se archiva."""
    acc = get_owned(db, user, account_id, lock=True)
    if _balances(db, user).get(acc.id, (ZERO, 0))[1]:
        raise ConflictError("La cuenta tiene movimientos: archivala en lugar de borrarla")
    db.delete(acc)


# ---------- Transferencias ----------


def _transfer_out(t: Transfer, accounts: dict[int, Account]) -> TransferOut:
    return TransferOut(
        id=t.id,
        from_account=AccountRef.model_validate(accounts[t.from_account_id]),
        to_account=AccountRef.model_validate(accounts[t.to_account_id]),
        amount=t.amount,
        date=t.date,
        description=t.description,
    )


def list_transfers(
    db: Session, user: User, *, start: date | None = None, end: date | None = None, account_id: int | None = None
) -> list[TransferOut]:
    stmt = select(Transfer).where(Transfer.user_id == user.id)
    if start:
        stmt = stmt.where(Transfer.date >= start)
    if end:
        stmt = stmt.where(Transfer.date <= end)
    if account_id:
        stmt = stmt.where((Transfer.from_account_id == account_id) | (Transfer.to_account_id == account_id))
    transfers = list(db.scalars(stmt.order_by(Transfer.date.desc(), Transfer.id.desc()).limit(500)))
    accounts = {a.id: a for a in db.scalars(select(Account).where(Account.user_id == user.id))}
    return [_transfer_out(t, accounts) for t in transfers]


def create_transfer(db: Session, user: User, data: TransferIn) -> TransferOut:
    src = get_owned(db, user, data.from_account_id)
    dst = get_owned(db, user, data.to_account_id)
    if src.archived or dst.archived:
        raise ValidationError("No se puede transferir con una cuenta archivada")
    t = Transfer(
        user_id=user.id,
        from_account_id=src.id,
        to_account_id=dst.id,
        amount=data.amount,
        date=data.date,
        description=data.description.strip(),
    )
    db.add(t)
    db.flush()
    return _transfer_out(t, {src.id: src, dst.id: dst})


def delete_transfer(db: Session, user: User, transfer_id: int) -> None:
    t = fetch(db, Transfer, transfer_id, lock=True)
    if not t or t.user_id != user.id:
        raise NotFoundError("Transferencia")
    db.delete(t)


def pending_card_statements(db: Session, user: User, today: date) -> list[tuple[Account, CardStatus]]:
    """Tarjetas con un resumen cerrado que todavía falta pagar (visto desde hoy)."""
    out = []
    totals = _balances(db, user)
    cards = select(Account).where(
        Account.user_id == user.id, Account.type == AccountType.card, Account.archived.is_(False)
    )
    for acc in db.scalars(cards):
        if not (acc.closing_day and acc.due_day):
            continue
        balance = acc.opening_balance + totals.get(acc.id, (ZERO, 0))[0]
        status = card_status(db, user, acc, balance, today)
        if status.statement_amount > 0:
            out.append((acc, status))
    return out
