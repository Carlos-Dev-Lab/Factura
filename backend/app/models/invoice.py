import enum
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.category import Category
from app.models.mixins import OwnedMixin, TimestampMixin


class InvoiceStatus(enum.StrEnum):
    pending = "pending"
    paid = "paid"


class Invoice(OwnedMixin, TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_user_due", "user_id", "due_date"),
        Index("ix_invoices_user_ruc_number", "user_id", "ruc", "number"),
        # Un archivo pertenece a una sola factura: borrar una no puede dejar a otra sin archivo.
        UniqueConstraint("file_key", name="uq_invoices_file_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier: Mapped[str] = mapped_column(String(120), default="")
    ruc: Mapped[str] = mapped_column(String(20), default="")
    number: Mapped[str] = mapped_column(String(40), default="")
    stamp: Mapped[str] = mapped_column(String(20), default="")
    # Código de control de la factura electrónica (SIFEN), 44 dígitos.
    cdc: Mapped[str | None] = mapped_column(String(44), index=True)
    issue_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    # Liquidación del IVA (montos de impuesto, no la base) y monto exento.
    iva10: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, server_default="0")
    iva5: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, server_default="0")
    exempt: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, server_default="0")
    # Gasto personal que se puede deducir del IRP.
    irp_deductible: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, native_enum=False, length=10), default=InvoiceStatus.pending
    )
    file_key: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str] = mapped_column(Text, default="")
    paid_on: Mapped[date | None] = mapped_column(Date)

    category: Mapped[Category | None] = relationship(lazy="joined")
