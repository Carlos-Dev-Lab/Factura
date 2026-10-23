from fastapi import APIRouter, Depends, File, Path, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import DB, CurrentUser, PathId, Storage, verify_csrf
from app.core.config import get_settings
from app.models import Invoice
from app.schemas.invoice import (
    FILE_KEY_PATTERN,
    InvoiceDraft,
    InvoiceFilter,
    InvoiceIn,
    InvoiceOut,
    InvoicePayIn,
    InvoiceUpdate,
)
from app.schemas.support import DeletedOut
from app.services import invoices
from app.services.storage import INLINE_TYPES, MEDIA_TYPES

router = APIRouter(prefix="/invoices", tags=["facturas"], dependencies=[Depends(verify_csrf)])


@router.get("", response_model=list[InvoiceOut])
def list_invoices(
    user: CurrentUser,
    db: DB,
    status_filter: InvoiceFilter | None = Query(None, alias="status"),
    q: str | None = Query(None, max_length=80),
) -> list[Invoice]:
    return invoices.list_invoices(db, user, status_filter, q)


@router.post("/analyze", response_model=InvoiceDraft)
def analyze_invoice(user: CurrentUser, db: DB, storage: Storage, file: UploadFile = File(...)) -> InvoiceDraft:
    # Lee como máximo el límite + 1 byte para rechazar archivos grandes sin cargarlos completos.
    content = file.file.read(get_settings().max_upload_bytes + 1)
    return invoices.analyze(db, user, storage, content)


@router.delete("/uploads/{file_key}", status_code=status.HTTP_204_NO_CONTENT)
def discard_upload(user: CurrentUser, db: DB, storage: Storage, file_key: str = Path(pattern=FILE_KEY_PATTERN)) -> None:
    invoices.discard_upload(db, user, storage, file_key)


@router.post("", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def create_invoice(data: InvoiceIn, user: CurrentUser, db: DB, storage: Storage) -> Invoice:
    return invoices.create(db, user, storage, data)


@router.patch("/{invoice_id}", response_model=InvoiceOut)
def update_invoice(invoice_id: PathId, data: InvoiceUpdate, user: CurrentUser, db: DB) -> Invoice:
    return invoices.update(db, user, invoice_id, data)


@router.post("/{invoice_id}/pay", response_model=InvoiceOut)
def pay_invoice(invoice_id: PathId, data: InvoicePayIn, user: CurrentUser, db: DB) -> Invoice:
    return invoices.pay(db, user, invoice_id, data)


@router.post("/{invoice_id}/unpay", response_model=InvoiceOut)
def unpay_invoice(invoice_id: PathId, user: CurrentUser, db: DB) -> Invoice:
    return invoices.unpay(db, user, invoice_id)


@router.delete("/{invoice_id}", response_model=DeletedOut)
def delete_invoice(invoice_id: PathId, user: CurrentUser, db: DB) -> DeletedOut:
    return DeletedOut(trash_id=invoices.delete(db, user, invoice_id))


@router.get("/{invoice_id}/file")
def invoice_file(invoice_id: PathId, user: CurrentUser, db: DB, storage: Storage) -> FileResponse:
    path = invoices.file_path(db, user, storage, invoice_id)
    ext = path.suffix.lstrip(".")
    inline = ext in INLINE_TYPES
    headers = {"X-Content-Type-Options": "nosniff"}
    if inline:
        headers["Content-Disposition"] = "inline"
    else:
        # El XML se descarga y, por si algún navegador lo abriera igual, sin poder ejecutar nada.
        headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return FileResponse(
        path,
        media_type=MEDIA_TYPES[ext],
        filename=None if inline else f"factura-{invoice_id}.{ext}",
        content_disposition_type="inline" if inline else "attachment",
        headers=headers,
    )
