import datetime as dt

from pydantic import BaseModel, Field, computed_field, field_serializer

from app.models import PaymentMethod, TransactionKind
from app.schemas.common import CategoryRef, Date, InputModel, Money, Month, ORMModel, PaymentName, PositiveMoney, RefId


class ScheduledIn(InputModel):
    name: PaymentName
    kind: TransactionKind = TransactionKind.expense
    amount: PositiveMoney
    variable_amount: bool = False
    day_of_month: int = Field(ge=1, le=31)
    # Mes de inicio (AAAA-MM); por defecto, el actual. Con `end_month` es un plan de cuotas.
    start_month: Month | None = None
    end_month: Month | None = None
    category_id: RefId | None = None
    account_id: RefId | None = None
    active: bool = True


class ScheduledUpdate(InputModel):
    name: PaymentName | None = None
    kind: TransactionKind | None = None
    amount: PositiveMoney | None = None
    variable_amount: bool | None = None
    day_of_month: int | None = Field(None, ge=1, le=31)
    start_month: Month | None = None
    end_month: Month | None = None  # null explícito = sin fin
    category_id: RefId | None = None
    account_id: RefId | None = None
    active: bool | None = None


class ScheduledPayIn(InputModel):
    month: Month
    paid_on: Date | None = None
    method: PaymentMethod = PaymentMethod.transfer
    # Monto real de este mes (servicios que varían). Sin valor, se usa el monto cargado.
    amount: PositiveMoney | None = None
    account_id: RefId | None = None


class ScheduledOut(ORMModel):
    id: int
    name: str
    kind: TransactionKind
    amount: PositiveMoney
    variable_amount: bool
    day_of_month: int
    start_month: dt.date
    end_month: dt.date | None
    category: CategoryRef | None
    account_id: int | None
    active: bool

    @field_serializer("start_month", "end_month")
    def _as_month(self, v: dt.date | None) -> str | None:
        return v.strftime("%Y-%m") if v else None

    @computed_field
    @property
    def installments(self) -> int | None:
        """Cantidad total de cuotas si el pago tiene fin."""
        if not self.end_month:
            return None
        return (self.end_month.year - self.start_month.year) * 12 + self.end_month.month - self.start_month.month + 1


class PaymentHistoryItem(BaseModel):
    transaction_id: int
    date: dt.date
    amount: Money


class ScheduledHistory(BaseModel):
    """Pagos anteriores, para sugerir el monto y avisar si subió."""

    items: list[PaymentHistoryItem]
    last_amount: Money | None
    average: Money | None
