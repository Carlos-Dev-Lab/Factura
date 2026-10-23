import datetime as dt
import enum
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import OwnedMixin, TimestampMixin


class AccountType(enum.StrEnum):
    cash = "cash"
    bank = "bank"
    card = "card"  # tarjeta de crédito: el saldo negativo es deuda
    wallet = "wallet"  # billetera electrónica (Tigo Money, Personal, etc.)


class Account(OwnedMixin, TimestampMixin, Base):
    """Dónde está la plata: efectivo, cuenta bancaria, tarjeta de crédito o billetera."""

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_account_user_name"),
        CheckConstraint("closing_day IS NULL OR closing_day BETWEEN 1 AND 31", name="ck_account_closing_day"),
        CheckConstraint("due_day IS NULL OR due_day BETWEEN 1 AND 31", name="ck_account_due_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    type: Mapped[AccountType] = mapped_column(Enum(AccountType, native_enum=False, length=10))
    color: Mapped[str] = mapped_column(String(7), default="#5AB8FF")
    # Saldo al empezar a usar la app. En una tarjeta, un número negativo es la deuda inicial.
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, server_default="0")
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Solo tarjetas de crédito: día de cierre del resumen y día de vencimiento del pago.
    closing_day: Mapped[int | None] = mapped_column(SmallInteger)
    due_day: Mapped[int | None] = mapped_column(SmallInteger)
    credit_limit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))


class Transfer(OwnedMixin, TimestampMixin, Base):
    """Movimiento de plata entre cuentas propias (no es gasto ni ingreso).

    Ejemplos: retirar efectivo del cajero, pagar el resumen de la tarjeta desde el banco.
    """

    __tablename__ = "transfers"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transfer_amount_positive"),
        CheckConstraint("from_account_id <> to_account_id", name="ck_transfer_distinct_accounts"),
        Index("ix_transfers_user_date", "user_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    to_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    date: Mapped[dt.date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(160), default="", server_default="")
