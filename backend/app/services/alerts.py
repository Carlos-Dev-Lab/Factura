"""Avisos del día: vencimientos cercanos o atrasados y presupuestos al límite.

Cada aviso tiene una clave estable (por ejemplo "inv:12:hoy") que sirve para
mandarlo por push o Telegram una sola vez. Los atrasados cambian de clave cada
semana, así se recuerdan una vez por semana y no todos los días.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category, Invoice, InvoiceStatus, Transaction, TransactionKind, User
from app.schemas.support import Alert, AlertLevel
from app.services import accounts, scheduled
from app.services.dates import add_months, month_key, month_range
from app.services.reports import WARN_PCT, budget_statuses

LEVEL_ORDER = {AlertLevel.danger: 0, AlertLevel.warn: 1, AlertLevel.info: 2}
MONTH_NAMES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def _money(value: Decimal, currency: str) -> str:
    symbol = {"PYG": "₲", "USD": "US$", "ARS": "$", "BRL": "R$", "EUR": "€"}.get(currency, "")
    digits = 0 if currency == "PYG" else 2
    text = f"{value:,.{digits}f}"
    if currency == "PYG":
        text = text.replace(",", ".")
    return f"{symbol} {text}".strip()


def _when(d: date, today: date) -> str:
    diff = (d - today).days
    if diff == 0:
        return "hoy"
    if diff == 1:
        return "mañana"
    if diff > 1:
        return f"en {diff} días"
    return "ayer" if diff == -1 else f"hace {-diff} días"


def _week(today: date) -> str:
    year, week, _ = today.isocalendar()
    return f"{year}w{week}"


def _due_alert(
    kind: str, ref: int, name: str, amount: Decimal, due: date, today: date, days_before: int, currency: str, link: str
) -> Alert | None:
    money = _money(amount, currency)
    if due < today:
        return Alert(
            key=f"{kind}:{ref}:atraso:{_week(today)}",
            level=AlertLevel.danger,
            # "venció" sirve para cualquier nombre ("La factura de…", "El resumen de…", "Alquiler").
            title=f"{name} venció {_when(due, today)}",
            body=money,
            link=link,
            date=due,
        )
    if due == today:
        return Alert(
            key=f"{kind}:{ref}:hoy:{due.isoformat()}",
            level=AlertLevel.warn,
            title=f"{name} vence hoy",
            body=money,
            link=link,
            date=due,
        )
    if (due - today).days <= days_before:
        return Alert(
            key=f"{kind}:{ref}:pronto:{due.isoformat()}",
            level=AlertLevel.info,
            title=f"{name} vence {_when(due, today)}",
            body=money,
            link=link,
            date=due,
        )
    return None


def compute(db: Session, user: User, today: date | None = None) -> list[Alert]:
    today = today or date.today()
    days = user.notify_days_before
    cur = user.currency
    alerts: list[Alert] = []

    # Facturas pendientes con vencimiento.
    pending = db.scalars(
        select(Invoice).where(
            Invoice.user_id == user.id, Invoice.status == InvoiceStatus.pending, Invoice.due_date.is_not(None)
        )
    )
    for inv in pending:
        name = f"La factura de {inv.supplier}" if inv.supplier else "Una factura"
        if a := _due_alert("inv", inv.id, name, inv.total, inv.due_date, today, days, cur, "/facturas"):  # type: ignore[arg-type]
            alerts.append(a)

    # Pagos fijos de este mes y del anterior (por si quedó uno sin pagar).
    this_month = today.replace(day=1)
    for first in (add_months(this_month, -1), this_month):
        start, end = month_range(month_key(first))
        paid = scheduled.paid_ids_in_range(db, user, start, end)
        for sp in scheduled.list_payments(db, user, only_active=True):
            if sp.kind != TransactionKind.expense or sp.id in paid or not scheduled.applies_to(sp, first):
                continue
            due = scheduled.occurrence(sp, first)
            # Si quedó impago el del mes anterior, el título dice de qué mes es (si no, se ven dos iguales).
            label = (
                f"El pago de {sp.name}"
                if first == this_month
                else f"El pago de {sp.name} de {MONTH_NAMES[first.month - 1]}"
            )
            if a := _due_alert(f"fijo{first:%Y%m}", sp.id, label, sp.amount, due, today, days, cur, "/calendario"):
                alerts.append(a)

    # Resúmenes de tarjeta.
    for acc, status in accounts.pending_card_statements(db, user, today):
        name = f"El resumen de {acc.name}"
        if a := _due_alert(
            "tarjeta", acc.id, name, status.statement_amount, status.due_date, today, days, cur, "/cuentas"
        ):
            alerts.append(a)

    alerts += _budget_alerts(db, user, today)

    # Límite diario.
    if user.daily_limit:
        spent = db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user.id,
                Transaction.kind == TransactionKind.expense,
                Transaction.date == today,
            )
        ) or Decimal(0)
        if spent > user.daily_limit:
            alerts.append(
                Alert(
                    key=f"diario:{today.isoformat()}",
                    level=AlertLevel.warn,
                    title="Pasaste el límite diario",
                    body=f"Llevás {_money(spent, cur)} hoy (límite {_money(user.daily_limit, cur)})",
                    link=f"/gastos?dia={today.isoformat()}",
                    date=today,
                )
            )
    return sorted(alerts, key=lambda a: (LEVEL_ORDER[a.level], a.date or date.max))


def _budget_alerts(db: Session, user: User, today: date) -> list[Alert]:
    start, end = month_range(month_key(today))
    spent_rows = db.execute(
        select(Transaction.category_id, func.sum(Transaction.amount))
        .where(
            Transaction.user_id == user.id,
            Transaction.kind == TransactionKind.expense,
            Transaction.date.between(start, end),
        )
        .group_by(Transaction.category_id)
    )
    spent = {cid: amount for cid, amount in spent_rows}
    cats = {c.id: c for c in db.scalars(select(Category).where(Category.user_id == user.id))}
    out = []
    month = month_key(today)
    for b in budget_statuses(cats, spent):
        if b.pct < WARN_PCT:
            continue
        over = b.state == "over"
        out.append(
            Alert(
                key=f"presupuesto:{b.category_id}:{'100' if over else '80'}:{month}",
                level=AlertLevel.danger if over else AlertLevel.warn,
                title=f"{b.name}: {'superaste' if over else 'llegaste al ' + str(int(b.pct)) + ' % de'} tu presupuesto",
                body=f"{_money(b.spent, user.currency)} de {_money(b.budget, user.currency)}",
                link="/",
            )
        )
    total = sum(spent.values(), Decimal(0))
    if user.monthly_budget and total >= user.monthly_budget * WARN_PCT / 100:
        over = total >= user.monthly_budget
        out.append(
            Alert(
                key=f"presupuesto:total:{'100' if over else '80'}:{month}",
                level=AlertLevel.danger if over else AlertLevel.warn,
                title="Superaste el presupuesto del mes" if over else "Estás cerca del presupuesto del mes",
                body=f"{_money(total, user.currency)} de {_money(user.monthly_budget, user.currency)}",
                link="/",
            )
        )
    return out
