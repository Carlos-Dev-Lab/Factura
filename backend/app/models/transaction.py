import datetime as dt
import enum
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, Enum, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.account import Account
from app.models.category import Category
from app.models.mixins import OwnedMixin, TimestampMixin


class TransactionKind(enum.StrEnum):
    expense = "expense"
    income = "income"


class PaymentMethod(enum.StrEnum):
    cash = "cash"
    debit = "debit"
    credit = "credit"
    transfer = "transfer"
    qr = "qr"


class Transaction(OwnedMixin, TimestampMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transaction_amount_positive"),
        Index("ix_transactions_user_date", "user_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[TransactionKind] = mapped_column(Enum(TransactionKind, native_enum=False, length=10))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    date: Mapped[dt.date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(160), default="")
    method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, native_enum=False, length=10), default=PaymentMethod.cash
    )
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), index=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), unique=True)
    scheduled_payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("scheduled_payments.id", ondelete="SET NULL"), index=True
    )

    category: Mapped[Category | None] = relationship(lazy="joined")
    account: Mapped[Account | None] = relationship(lazy="joined")
