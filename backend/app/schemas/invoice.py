import datetime as dt
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field

from app.models import InvoiceStatus, PaymentMethod
from app.schemas.common import CategoryRef, Date, InputModel, Money, ORMModel, RefId

FILE_KEY_PATTERN = r"^[a-f0-9]{32}\.(pdf|png|jpg|webp|xml)$"
CDC_PATTERN = r"^[0-9]{44}$"  # [0-9]: \d también acepta dígitos de otros alfabetos


class InvoiceFilter(StrEnum):
    pending = "pending"
    overdue = "overdue"
    paid = "paid"


class InvoiceIn(InputModel):
    supplier: str = Field("", max_length=120)
    ruc: str = Field("", max_length=20)
    number: str = Field("", max_length=40)
    stamp: str = Field("", max_length=20)
    cdc: str | None = Field(None, pattern=CDC_PATTERN)
    issue_date: Date | None = None
    due_date: Date | None = None
    total: Money
    iva10: Money = 0
    iva5: Money = 0
    exempt: Money = 0
    irp_deductible: bool = False
    category_id: RefId | None = None
    notes: str = Field("", max_length=2000)
    file_key: str | None = Field(None, pattern=FILE_KEY_PATTERN)
    already_paid: bool = False
    account_id: RefId | None = None  # cuenta del pago si `already_paid`
    # Guardar aunque coincida con una factura ya cargada (mismo CDC o mismo RUC y número).
    allow_duplicate: bool = False


class InvoiceUpdate(InputModel):
    supplier: str | None = Field(None, max_length=120)
    ruc: str | None = Field(None, max_length=20)
    number: str | None = Field(None, max_length=40)
    stamp: str | None = Field(None, max_length=20)
    cdc: str | None = Field(None, pattern=CDC_PATTERN)
    issue_date: Date | None = None
    due_date: Date | None = None
    total: Money | None = None
    iva10: Money | None = None
    iva5: Money | None = None
    exempt: Money | None = None
    irp_deductible: bool | None = None
    category_id: RefId | None = None
    notes: str | None = Field(None, max_length=2000)


class InvoicePayIn(InputModel):
    paid_on: Date | None = None
    method: PaymentMethod = PaymentMethod.transfer
    account_id: RefId | None = None


class InvoiceOut(ORMModel):
    id: int
    supplier: str
    ruc: str
    number: str
    stamp: str
    cdc: str | None
    issue_date: dt.date | None
    due_date: dt.date | None
    total: Money
    iva10: Money
    iva5: Money
    exempt: Money
    irp_deductible: bool
    category: CategoryRef | None
    status: InvoiceStatus
    notes: str
    paid_on: dt.date | None
    file_key: str | None = Field(exclude=True)

    @computed_field
    @property
    def has_file(self) -> bool:
        return self.file_key is not None

    @computed_field
    @property
    def file_type(self) -> str | None:
        return self.file_key.rsplit(".", 1)[-1] if self.file_key else None

    @computed_field
    @property
    def overdue(self) -> bool:
        return self.status == InvoiceStatus.pending and self.due_date is not None and self.due_date < dt.date.today()


class DuplicateRef(BaseModel):
    id: int
    label: str
    status: InvoiceStatus


class InvoiceDraft(BaseModel):
    """Resultado del análisis automático de un documento, para revisar antes de guardar."""

    file_key: str
    supplier: str | None
    ruc: str | None
    number: str | None
    stamp: str | None
    cdc: str | None
    issue_date: dt.date | None
    due_date: dt.date | None
    total: Money | None
    iva10: Money | None
    iva5: Money | None
    exempt: Money | None
    category_id: int | None
    confidence: float
    # Cómo se leyó: "xml" (factura electrónica), "qr", "cdc", "pdf" (texto), "ocr" o "none".
    method: str
    # True/False si el RUC trae dígito verificador y se pudo comprobar; None si no hay RUC.
    ruc_valid: bool | None
    duplicate_of: DuplicateRef | None
    raw_text: str
