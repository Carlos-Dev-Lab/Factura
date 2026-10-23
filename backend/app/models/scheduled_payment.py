import datetime as dt
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, Enum, ForeignKey, Numeric, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.category import Category
from app.models.mixins import OwnedMixin, TimestampMixin
from app.models.transaction import TransactionKind


class ScheduledPayment(OwnedMixin, TimestampMixin, Base):
    """Pago o cobro que se repite cada mes (alquiler, cuotas, servicios, sueldo)."""

    __tablename__ = "scheduled_payments"
    __table_args__ = (
        CheckConstraint("day_of_month BETWEEN 1 AND 31", name="ck_scheduled_day"),
        CheckConstraint("end_month IS NULL OR end_month >= start_month", name="ck_scheduled_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[TransactionKind] = mapped_column(
        Enum(TransactionKind, native_enum=False, length=10),
        default=TransactionKind.expense,
        server_default=TransactionKind.expense.value,
    )
    # Monto esperado. Si `variable_amount`, es una estimación y se confirma el real al pagar.
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    variable_amount: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    day_of_month: Mapped[int] = mapped_column(SmallInteger)
    # Primer y último mes (día 1) en que corresponde. Sin fin = se repite siempre; con fin = cuotas.
    start_month: Mapped[dt.date] = mapped_column(Date, server_default=text("date_trunc('month', now())::date"))
    end_month: Mapped[dt.date | None] = mapped_column(Date)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    category: Mapped[Category | None] = relationship(lazy="joined")
