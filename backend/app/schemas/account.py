import datetime as dt

from pydantic import BaseModel, Field, model_validator

from app.models import AccountType
from app.schemas.common import (
    AccountName,
    AccountRef,
    Amount,
    Date,
    HexColor,
    InputModel,
    Money,
    ORMModel,
    PositiveMoney,
    RefId,
    SignedMoney,
)


class AccountIn(InputModel):
    name: AccountName
    type: AccountType = AccountType.cash
    color: HexColor = "#5AB8FF"
    opening_balance: SignedMoney = 0
    closing_day: int | None = Field(None, ge=1, le=31)
    due_day: int | None = Field(None, ge=1, le=31)
    credit_limit: Money | None = None

    @model_validator(mode="after")
    def _card_days(self) -> "AccountIn":
        if self.type == AccountType.card and (self.closing_day is None or self.due_day is None):
            raise ValueError("Una tarjeta de crédito necesita día de cierre y de vencimiento")
        return self


class AccountUpdate(InputModel):
    name: AccountName | None = None
    color: HexColor | None = None
    opening_balance: SignedMoney | None = None
    closing_day: int | None = Field(None, ge=1, le=31)
    due_day: int | None = Field(None, ge=1, le=31)
    credit_limit: Money | None = None
    archived: bool | None = None


class CardStatus(BaseModel):
    """Resumen de una tarjeta de crédito."""

    last_closing: dt.date
    next_closing: dt.date
    due_date: dt.date  # vencimiento del último resumen cerrado
    next_due_date: dt.date  # vencimiento del resumen que cierra en next_closing
    statement_amount: Amount  # lo que falta pagar del último resumen
    current_period: Amount  # consumos desde el último cierre
    debt: Amount  # deuda total a hoy
    available: Amount | None  # límite - deuda


class AccountOut(ORMModel):
    id: int
    name: str
    type: AccountType
    color: str
    opening_balance: SignedMoney
    archived: bool
    closing_day: int | None
    due_day: int | None
    credit_limit: Money | None
    balance: Amount = 0
    movement_count: int = 0
    card: CardStatus | None = None


class TransferIn(InputModel):
    from_account_id: RefId
    to_account_id: RefId
    amount: PositiveMoney
    date: Date
    description: str = Field("", max_length=160)

    @model_validator(mode="after")
    def _distinct(self) -> "TransferIn":
        if self.from_account_id == self.to_account_id:
            raise ValueError("Elegí dos cuentas distintas")
        return self


class TransferOut(ORMModel):
    id: int
    from_account: AccountRef
    to_account: AccountRef
    amount: PositiveMoney
    date: dt.date
    description: str
