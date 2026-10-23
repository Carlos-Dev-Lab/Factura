import csv
import io
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.models import Category, CategoryKind, Invoice, InvoiceStatus, Transaction, TransactionKind, User
from app.schemas.report import (
    BudgetStatus,
    CalendarDay,
    CalendarMonth,
    CategoryTotal,
    CategoryYear,
    DailyTotal,
    DueItem,
    DueKind,
    DueState,
    FiscalReport,
    FiscalRow,
    MonthSummary,
    MonthTotal,
    Projection,
    YearReport,
)
from app.services import accounts, scheduled
from app.services.dates import month_range

UNCATEGORIZED_COLOR = "#A3ADC8"
UPCOMING_LIMIT = 12
ZERO = Decimal(0)
WARN_PCT, OVER_PCT = 80, 100


def _pct(part: Decimal, whole: Decimal) -> float | None:
    return round(float(part / whole * 100), 1) if whole else None


def _invoice_state(inv: Invoice, today: date) -> DueState:
    if inv.status == InvoiceStatus.paid:
        return DueState.paid
    return DueState.overdue if inv.due_date and inv.due_date < today else DueState.pending


def _invoice_due(inv: Invoice, today: date) -> DueItem:
    return DueItem(
        kind=DueKind.invoice,
        id=inv.id,
        name=inv.supplier or "Factura",
        amount=inv.total,
        date=inv.due_date or inv.issue_date,
        state=_invoice_state(inv, today),
    )


def _scheduled_dues(db: Session, user: User, start: date, end: date, today: date) -> list[DueItem]:
    paid = scheduled.paid_in_range(db, user, start, end)
    items = []
    for sp in scheduled.list_payments(db, user, only_active=True):
        applies = scheduled.applies_to(sp, start)
        # Fuera de su período (antes de empezar o después de la última cuota) no corresponde.
        if not applies and sp.id not in paid:
            continue
        when = scheduled.occurrence(sp, start)
        is_paid = sp.id in paid
        state = DueState.paid if is_paid else (DueState.overdue if when < today else DueState.pending)
        items.append(
            DueItem(
                kind=DueKind.scheduled,
                id=sp.id,
                name=sp.name,
                amount=paid.get(sp.id, sp.amount),
                date=when,
                state=state,
                direction="in" if sp.kind == TransactionKind.income else "out",
                detail=scheduled.installment_label(sp, start) if applies else None,
                estimated=sp.variable_amount and not is_paid,
            )
        )
    return items


def _card_dues(db: Session, user: User, today: date) -> list[DueItem]:
    """Resúmenes de tarjeta cerrados que falta pagar (el más reciente de cada tarjeta)."""
    return [
        DueItem(
            kind=DueKind.card,
            id=acc.id,
            name=f"Tarjeta {acc.name}",
            amount=status.statement_amount,
            date=status.due_date,
            state=DueState.overdue if status.due_date < today else DueState.pending,
            detail=f"Resumen al {status.last_closing.strftime('%d/%m')}",
        )
        for acc, status in accounts.pending_card_statements(db, user, today)
    ]


def _month_transactions(db: Session, user: User, start: date, end: date) -> list[Transaction]:
    return list(
        db.scalars(select(Transaction).where(Transaction.user_id == user.id, Transaction.date.between(start, end)))
    )


def _expense_on(db: Session, user: User, day: date) -> Decimal:
    """Total gastado en un día (el panel siempre muestra el de hoy, aunque se mire otro mes)."""
    stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.user_id == user.id, Transaction.kind == TransactionKind.expense, Transaction.date == day
    )
    return db.scalar(stmt) or ZERO


def budget_statuses(categories: dict[int, Category], spent: dict[int | None, Decimal]) -> list[BudgetStatus]:
    out = []
    for cat in categories.values():
        if cat.kind != CategoryKind.expense or not cat.monthly_budget:
            continue
        used = spent.get(cat.id, ZERO)
        pct = round(float(used / cat.monthly_budget * 100), 1)
        state = "over" if pct >= OVER_PCT else "warn" if pct >= WARN_PCT else "ok"
        out.append(
            BudgetStatus(
                category_id=cat.id,
                name=cat.name,
                color=cat.color,
                budget=cat.monthly_budget,
                spent=used,
                pct=pct,
                state=state,
            )
        )
    return sorted(out, key=lambda b: -b.pct)


def _projection(
    user: User,
    start: date,
    end: date,
    today: date,
    income: Decimal,
    expense: Decimal,
    dues: list[DueItem],
) -> Projection:
    if end < today:
        # Mes cerrado: lo que pasó es lo que hay.
        return Projection(
            pending_income=ZERO,
            pending_expense=ZERO,
            projected_balance=income - expense,
            days_left=0,
            daily_allowance=None,
            budget_daily_allowance=None,
        )
    current = start <= today <= end

    def counts(d: DueItem) -> bool:
        if d.state == DueState.paid or d.date is None:
            return False
        # En el mes actual cuentan también los atrasados de meses anteriores.
        return d.date <= end and (current or d.date >= start)

    pending_in = sum((d.amount for d in dues if d.direction == "in" and counts(d)), ZERO)
    pending_out = sum((d.amount for d in dues if d.direction == "out" and counts(d)), ZERO)
    projected = income - expense + pending_in - pending_out
    days_left = (end - max(today, start)).days + 1
    allowance = (max(ZERO, projected) / days_left).quantize(Decimal("1"))
    budget_allowance = None
    if user.monthly_budget:
        remaining = max(ZERO, user.monthly_budget - expense - pending_out)
        budget_allowance = (remaining / days_left).quantize(Decimal("1"))
    return Projection(
        pending_income=pending_in,
        pending_expense=pending_out,
        projected_balance=projected,
        days_left=days_left,
        daily_allowance=allowance,
        budget_daily_allowance=budget_allowance,
    )


def summary(db: Session, user: User, month: str) -> MonthSummary:
    start, end = month_range(month)
    today = date.today()
    txs = _month_transactions(db, user, start, end)

    income = sum((t.amount for t in txs if t.kind == TransactionKind.income), ZERO)
    expense = sum((t.amount for t in txs if t.kind == TransactionKind.expense), ZERO)

    by_cat: dict[int | None, Decimal] = defaultdict(Decimal)
    daily: dict[date, list[Decimal]] = {start + timedelta(days=i): [ZERO, ZERO] for i in range((end - start).days + 1)}
    for t in txs:
        slot = daily[t.date]
        if t.kind == TransactionKind.expense:
            slot[0] += t.amount
            by_cat[t.category_id] += t.amount
        else:
            slot[1] += t.amount
    cat_info = {c.id: c for c in db.scalars(select(Category).where(Category.user_id == user.id))}
    by_category = sorted(
        (
            CategoryTotal(
                category_id=cid,
                name=cat_info[cid].name if cid in cat_info else "Sin categoría",
                color=cat_info[cid].color if cid in cat_info else UNCATEGORIZED_COLOR,
                amount=amt,
            )
            for cid, amt in by_cat.items()
        ),
        key=lambda c: -c.amount,
    )

    prev_end = start - timedelta(days=1)
    previous = (
        db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user.id,
                Transaction.kind == TransactionKind.expense,
                Transaction.date.between(prev_end.replace(day=1), prev_end),
            )
        )
        or ZERO
    )

    pending = db.scalars(select(Invoice).where(Invoice.user_id == user.id, Invoice.status == InvoiceStatus.pending))
    dues = [_invoice_due(i, today) for i in pending]
    dues += _scheduled_dues(db, user, start, end, today)
    if end >= today:
        dues += _card_dues(db, user, today)
    upcoming = sorted((d for d in dues if d.state != DueState.paid), key=lambda d: d.date or date.max)
    to_pay = [d for d in upcoming if d.direction == "out"]

    return MonthSummary(
        month=month,
        income=income,
        expense=expense,
        balance=float(income - expense),
        budget=user.monthly_budget,
        budget_used_pct=_pct(expense, user.monthly_budget),
        previous_expense=previous,
        expense_change_pct=_pct(expense - previous, previous),
        due_total=sum((d.amount for d in to_pay), ZERO),
        overdue_count=sum(1 for d in to_pay if d.state == DueState.overdue),
        transaction_count=len(txs),
        today_expense=_expense_on(db, user, today),
        daily_limit=user.daily_limit,
        by_category=by_category,
        budgets=budget_statuses(cat_info, by_cat),
        projection=_projection(user, start, end, today, income, expense, dues),
        daily=[DailyTotal(date=d, expense=v[0], income=v[1]) for d, v in daily.items()],
        upcoming=upcoming[:UPCOMING_LIMIT],
    )


def calendar_month(db: Session, user: User, month: str) -> CalendarMonth:
    start, end = month_range(month)
    today = date.today()
    days = {
        start + timedelta(days=i): CalendarDay(date=start + timedelta(days=i), expense=ZERO, income=ZERO, dues=[])
        for i in range((end - start).days + 1)
    }
    for t in _month_transactions(db, user, start, end):
        if t.kind == TransactionKind.expense:
            days[t.date].expense += t.amount
        else:
            days[t.date].income += t.amount

    due_date = func.coalesce(Invoice.due_date, Invoice.issue_date)
    for inv in db.scalars(select(Invoice).where(Invoice.user_id == user.id, due_date.between(start, end))):
        item = _invoice_due(inv, today)
        days[item.date].dues.append(item)  # type: ignore[index]
    for item in _scheduled_dues(db, user, start, end, today):
        days[item.date].dues.append(item)  # type: ignore[index]
    for item in _card_dues(db, user, today):
        if item.date and start <= item.date <= end:
            days[item.date].dues.append(item)
    return CalendarMonth(month=month, days=list(days.values()))


def year_report(db: Session, user: User, year: int) -> YearReport:
    start, end = date(year, 1, 1), date(year, 12, 31)
    month_col = extract("month", Transaction.date)
    rows = db.execute(
        select(month_col, Transaction.kind, Transaction.category_id, func.sum(Transaction.amount))
        .where(Transaction.user_id == user.id, Transaction.date.between(start, end))
        .group_by(month_col, Transaction.kind, Transaction.category_id)
    )
    income = [ZERO] * 12
    expense = [ZERO] * 12
    by_cat: dict[int | None, list[Decimal]] = defaultdict(lambda: [ZERO] * 12)
    for mon, kind, cat_id, amount in rows:
        i = int(mon) - 1
        if kind == TransactionKind.income:
            income[i] += amount
        else:
            expense[i] += amount
            by_cat[cat_id][i] += amount
    cat_info = {c.id: c for c in db.scalars(select(Category).where(Category.user_id == user.id))}
    categories = sorted(
        (
            CategoryYear(
                category_id=cid,
                name=cat_info[cid].name if cid in cat_info else "Sin categoría",
                color=cat_info[cid].color if cid in cat_info else UNCATEGORIZED_COLOR,
                total=sum(months, ZERO),
                months=months,
            )
            for cid, months in by_cat.items()
        ),
        key=lambda c: -c.total,
    )
    today = date.today()
    last = 12 if year < today.year else (today.month if year == today.year else 0)
    # El promedio arranca en el primer mes con movimientos: si se empezó a usar la app en
    # octubre, no tiene sentido dividir por los meses de enero a septiembre.
    first = next((i for i in range(12) if income[i] or expense[i]), last)
    counted = max(0, last - first)
    total_in, total_out = sum(income, ZERO), sum(expense, ZERO)
    spent_counted = sum(expense[first:last], ZERO)
    return YearReport(
        year=year,
        months=[
            MonthTotal(
                month=f"{year}-{i + 1:02d}", income=income[i], expense=expense[i], balance=income[i] - expense[i]
            )
            for i in range(12)
        ],
        categories=categories,
        income=total_in,
        expense=total_out,
        balance=total_in - total_out,
        average_expense=(spent_counted / counted).quantize(Decimal("1")) if counted else ZERO,
        months_counted=counted,
    )


def fiscal_report(db: Session, user: User, month: str) -> FiscalReport:
    """Compras del mes para el contador: IVA 10 %, 5 %, exentas y gastos deducibles de IRP."""
    start, end = month_range(month)
    invoices = db.scalars(
        select(Invoice)
        .where(Invoice.user_id == user.id, Invoice.issue_date.between(start, end))
        .order_by(Invoice.issue_date, Invoice.id)
    )
    rows = [
        FiscalRow(
            invoice_id=i.id,
            issue_date=i.issue_date,
            supplier=i.supplier,
            ruc=i.ruc,
            stamp=i.stamp,
            number=i.number,
            cdc=i.cdc,
            total=i.total,
            taxed10=i.iva10 * 11,
            iva10=i.iva10,
            taxed5=i.iva5 * 21,
            iva5=i.iva5,
            exempt=i.exempt,
            irp_deductible=i.irp_deductible,
            status=i.status.value,
            has_file=i.file_key is not None,
        )
        for i in invoices
    ]

    def total(attr: str) -> Decimal:
        return sum((getattr(r, attr) for r in rows), ZERO)

    return FiscalReport(
        month=month,
        rows=rows,
        total=total("total"),
        taxed10=total("taxed10"),
        iva10=total("iva10"),
        taxed5=total("taxed5"),
        iva5=total("iva5"),
        exempt=total("exempt"),
        irp_total=sum((r.total for r in rows if r.irp_deductible), ZERO),
        missing_iva=sum(1 for r in rows if r.total > 0 and not (r.iva10 or r.iva5 or r.exempt)),
    )


def fiscal_csv(report: FiscalReport) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(
        [
            "Fecha de emisión",
            "RUC",
            "Proveedor",
            "Timbrado",
            "Número",
            "CDC",
            "Gravado 10% (IVA incluido)",
            "IVA 10%",
            "Gravado 5% (IVA incluido)",
            "IVA 5%",
            "Exentas",
            "Total",
            "Deducible IRP",
            "Estado",
        ]
    )
    for r in report.rows:
        writer.writerow(
            [
                r.issue_date.isoformat() if r.issue_date else "",
                # Todos los textos que carga el usuario, no solo el proveedor: un "=..." en el RUC
                # o en el número se ejecutaba como fórmula al abrir la planilla en Excel.
                _csv_safe(r.ruc),
                _csv_safe(r.supplier),
                _csv_safe(r.stamp),
                _csv_safe(r.number),
                r.cdc or "",
                f"{r.taxed10:.2f}",
                f"{r.iva10:.2f}",
                f"{r.taxed5:.2f}",
                f"{r.iva5:.2f}",
                f"{r.exempt:.2f}",
                f"{r.total:.2f}",
                "Sí" if r.irp_deductible else "No",
                "Pagada" if r.status == "paid" else "Pendiente",
            ]
        )
    return "﻿" + buf.getvalue()


def export_csv(db: Session, user: User, month: str | None) -> str:
    stmt = select(Transaction).where(Transaction.user_id == user.id)
    if month:
        start, end = month_range(month)
        stmt = stmt.where(Transaction.date.between(start, end))
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Fecha", "Tipo", "Categoría", "Descripción", "Cuenta", "Método", "Monto"])
    labels = {TransactionKind.expense: "Gasto", TransactionKind.income: "Ingreso"}
    for t in db.scalars(stmt.order_by(Transaction.date, Transaction.id)):
        writer.writerow(
            [
                t.date.isoformat(),
                labels[t.kind],
                _csv_safe(t.category.name) if t.category else "",
                _csv_safe(t.description),
                _csv_safe(t.account.name) if t.account else "",
                t.method.value,
                f"{t.amount:.2f}",
            ]
        )
    return "﻿" + buf.getvalue()  # BOM: Excel detecta UTF-8 y muestra bien los acentos


_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: str) -> str:
    """Evita inyección de fórmulas al abrir el CSV en Excel (en todo texto que escribe el usuario)."""
    return f"'{value}" if value.startswith(_FORMULA_PREFIXES) else value
