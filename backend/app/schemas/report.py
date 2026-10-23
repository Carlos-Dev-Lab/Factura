import datetime as dt
from enum import StrEnum

from pydantic import BaseModel

from app.schemas.common import Amount


class DueKind(StrEnum):
    invoice = "invoice"
    scheduled = "scheduled"
    card = "card"  # resumen de tarjeta de crédito


class DueState(StrEnum):
    pending = "pending"
    overdue = "overdue"
    paid = "paid"


class DueItem(BaseModel):
    kind: DueKind
    id: int
    name: str
    amount: Amount
    date: dt.date | None
    state: DueState
    # "out" = hay que pagar; "in" = cobro esperado (sueldo programado).
    direction: str = "out"
    # Texto extra, por ejemplo "Cuota 3 de 12".
    detail: str | None = None
    # El monto es una estimación (servicio que varía cada mes).
    estimated: bool = False


class CategoryTotal(BaseModel):
    category_id: int | None
    name: str
    color: str
    amount: Amount


class BudgetStatus(BaseModel):
    category_id: int
    name: str
    color: str
    budget: Amount
    spent: Amount
    pct: float
    state: str  # ok, warn (≥ 80 %), over (≥ 100 %)


class Projection(BaseModel):
    """¿Cómo cierra el mes? Lo que ya pasó más lo que falta pagar y cobrar."""

    pending_income: Amount
    pending_expense: Amount
    projected_balance: Amount
    days_left: int
    # Cuánto se puede gastar por día sin quedar en rojo (None si el mes ya pasó).
    daily_allowance: Amount | None
    # Cuánto por día para no pasarse del presupuesto mensual (None si no hay presupuesto).
    budget_daily_allowance: Amount | None


class DailyTotal(BaseModel):
    date: dt.date
    expense: Amount
    income: Amount


class MonthSummary(BaseModel):
    month: str
    income: Amount
    expense: Amount
    balance: float
    budget: Amount
    budget_used_pct: float | None
    previous_expense: Amount
    expense_change_pct: float | None
    due_total: Amount
    overdue_count: int
    transaction_count: int
    today_expense: Amount
    daily_limit: Amount
    by_category: list[CategoryTotal]
    budgets: list[BudgetStatus]
    projection: Projection
    daily: list[DailyTotal]
    upcoming: list[DueItem]


class CalendarDay(BaseModel):
    date: dt.date
    expense: Amount
    income: Amount
    dues: list[DueItem]


class CalendarMonth(BaseModel):
    month: str
    days: list[CalendarDay]


class MonthTotal(BaseModel):
    month: str
    income: Amount
    expense: Amount
    balance: Amount


class CategoryYear(BaseModel):
    category_id: int | None
    name: str
    color: str
    total: Amount
    months: list[Amount]


class YearReport(BaseModel):
    year: int
    months: list[MonthTotal]
    categories: list[CategoryYear]
    income: Amount
    expense: Amount
    balance: Amount
    average_expense: Amount
    # Promedio mensual de gasto, solo sobre los meses que ya pasaron o están en curso.
    months_counted: int


class FiscalRow(BaseModel):
    invoice_id: int
    issue_date: dt.date | None
    supplier: str
    ruc: str
    stamp: str
    number: str
    cdc: str | None
    total: Amount
    taxed10: Amount
    iva10: Amount
    taxed5: Amount
    iva5: Amount
    exempt: Amount
    irp_deductible: bool
    status: str
    has_file: bool


class FiscalReport(BaseModel):
    month: str
    rows: list[FiscalRow]
    total: Amount
    taxed10: Amount
    iva10: Amount
    taxed5: Amount
    iva5: Amount
    exempt: Amount
    irp_total: Amount
    # Facturas sin desglose de IVA cargado (conviene revisarlas antes de mandarlas al contador).
    missing_iva: int
