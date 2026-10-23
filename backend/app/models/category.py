import enum
from decimal import Decimal

from sqlalchemy import Enum, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import OwnedMixin


class CategoryKind(enum.StrEnum):
    expense = "expense"
    income = "income"


class Category(OwnedMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "name", "kind", name="uq_category_user_name_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40))
    color: Mapped[str] = mapped_column(String(7))
    kind: Mapped[CategoryKind] = mapped_column(Enum(CategoryKind, native_enum=False, length=10))
    # Tope de gasto mensual de la categoría (solo para gastos). None = sin presupuesto.
    monthly_budget: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
