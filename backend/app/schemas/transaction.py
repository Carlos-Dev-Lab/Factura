import datetime as dt

from pydantic import BaseModel, Field

from app.models import PaymentMethod, TransactionKind
from app.schemas.common import AccountRef, Amount, CategoryRef, Date, InputModel, ORMModel, PositiveMoney, RefId


class TransactionIn(InputModel):
    kind: TransactionKind = TransactionKind.expense
    amount: PositiveMoney
    date: Date
    description: str = Field("", max_length=160)
    method: PaymentMethod = PaymentMethod.cash
    category_id: RefId | None = None
    account_id: RefId | None = None


class TransactionUpdate(InputModel):
    kind: TransactionKind | None = None
    amount: PositiveMoney | None = None
    date: Date | None = None
    description: str | None = Field(None, max_length=160)
    method: PaymentMethod | None = None
    category_id: RefId | None = None
    account_id: RefId | None = None


class TransactionOut(ORMModel):
    id: int
    kind: TransactionKind
    amount: Amount
    date: dt.date
    description: str
    method: PaymentMethod
    category: CategoryRef | None
    account: AccountRef | None
    invoice_id: int | None
    scheduled_payment_id: int | None


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    # Sumas de TODOS los resultados del filtro (no solo de la página).
    expense_total: Amount = 0
    income_total: Amount = 0
