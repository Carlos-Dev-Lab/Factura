from datetime import date
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import contains_pattern, fetch
from app.core.errors import ConflictError, NotFoundError, PayloadTooLargeError, ValidationError
from app.models import CategoryKind, Invoice, InvoiceStatus, Transaction, TransactionKind, User
from app.schemas.invoice import DuplicateRef, InvoiceDraft, InvoiceFilter, InvoiceIn, InvoicePayIn, InvoiceUpdate
from app.services import accounts, categories, ocr, rules, sifen, trash
from app.services.invoice_parser import ParsedInvoice, parse_invoice_text
from app.services.storage import LocalStorage, detect_file_type

RAW_TEXT_LIMIT = 4000
# Un archivo analizado que no se guardó como factura en este plazo se considera abandonado.
ORPHAN_UPLOAD_SECONDS = 24 * 3600


def get_owned(db: Session, user: User, invoice_id: int, *, lock: bool = False) -> Invoice:
    inv = fetch(db, Invoice, invoice_id, lock=lock)
    if not inv or inv.user_id != user.id:
        raise NotFoundError("Factura")
    return inv


def label(inv: Invoice) -> str:
    return " ".join(p for p in (inv.supplier or "Factura", inv.number) if p)


def list_invoices(db: Session, user: User, status: InvoiceFilter | None, q: str | None) -> list[Invoice]:
    stmt = select(Invoice).where(Invoice.user_id == user.id)
    if status == InvoiceFilter.paid:
        stmt = stmt.where(Invoice.status == InvoiceStatus.paid)
    elif status == InvoiceFilter.pending:
        stmt = stmt.where(Invoice.status == InvoiceStatus.pending)
    elif status == InvoiceFilter.overdue:
        stmt = stmt.where(Invoice.status == InvoiceStatus.pending, Invoice.due_date < date.today())
    if q:
        like = contains_pattern(q)
        stmt = stmt.where(
            or_(
                Invoice.supplier.ilike(like, escape="\\"),
                Invoice.ruc.ilike(like, escape="\\"),
                Invoice.number.ilike(like, escape="\\"),
                Invoice.cdc.ilike(like, escape="\\"),
            )
        )
    order = Invoice.due_date.desc().nulls_last(), Invoice.issue_date.desc().nulls_last(), Invoice.id.desc()
    return list(db.scalars(stmt.order_by(*order)))


# ---------- Duplicados ----------


def find_duplicate(
    db: Session,
    user: User,
    *,
    cdc: str | None,
    ruc: str | None,
    number: str | None,
    stamp: str | None,
    exclude_id: int | None = None,
) -> Invoice | None:
    """Misma factura ya cargada: mismo CDC, o mismo RUC y número (y timbrado si ambos lo tienen)."""
    conditions = []
    if cdc:
        conditions.append(Invoice.cdc == cdc)
    if ruc and number:
        same = (Invoice.ruc == ruc.strip()) & (Invoice.number == number.strip())
        if stamp:
            same &= or_(Invoice.stamp == stamp.strip(), Invoice.stamp == "")
        conditions.append(same)
    if not conditions:
        return None
    stmt = select(Invoice).where(Invoice.user_id == user.id, or_(*conditions))
    if exclude_id is not None:
        stmt = stmt.where(Invoice.id != exclude_id)
    return db.scalars(stmt.order_by(Invoice.id).limit(1)).first()


# ---------- Análisis de documentos ----------


def purge_orphan_uploads(db: Session, user: User, storage: LocalStorage) -> int:
    """Borra archivos analizados hace más de un día que nunca se asociaron a una factura.

    Cubre el caso de cerrar el navegador sin guardar ni cancelar: sin esto, el disco se
    llenaría con archivos de hasta 15 MB que nadie puede ver. Los archivos de facturas
    que están en la papelera no se tocan (se pueden restaurar).
    """
    old = storage.keys_older_than(user.id, ORPHAN_UPLOAD_SECONDS)
    if not old:
        return 0
    used = set(db.scalars(select(Invoice.file_key).where(Invoice.user_id == user.id, Invoice.file_key.in_(old))))
    used |= trash.held_file_keys(db, user)
    orphans = [k for k in old if k not in used]
    for key in orphans:
        storage.delete(user.id, key)
    return len(orphans)


def _read_document(path: Path, ext: str, content: bytes) -> tuple[ParsedInvoice, str, str]:
    """(datos, método, texto) del documento."""
    if ext == "xml":
        parsed = sifen.parse_xml(content)
        text = sifen.xml_text(content)
        return (parsed, "xml", text) if parsed else (ParsedInvoice(source="none"), "none", text)
    extracted = ocr.extract(path, get_settings().ocr_languages)
    parsed = parse_invoice_text(extracted.text)
    for payload in extracted.qr:
        if qr := sifen.parse_qr(payload):
            sifen.apply_qr(parsed, qr)
            break
    method = parsed.source if parsed.source in ("qr", "cdc") else extracted.method if extracted.text.strip() else "none"
    return parsed, method, extracted.text


def analyze(db: Session, user: User, storage: LocalStorage, content: bytes) -> InvoiceDraft:
    settings = get_settings()
    if len(content) > settings.max_upload_bytes:
        raise PayloadTooLargeError(f"El archivo supera {settings.max_upload_mb} MB")
    ext = detect_file_type(content)
    if not ext:
        raise ValidationError("Formato no soportado. Usá PDF, JPG, PNG, WEBP o el XML de la factura electrónica.")
    purge_orphan_uploads(db, user, storage)
    key = storage.save(user.id, content, ext)
    try:
        parsed, method, text = _read_document(storage.path(user.id, key), ext, content)
        suggestion = rules.suggest(
            db, user, CategoryKind.expense, text=f"{parsed.supplier or ''}\n{text}", ruc=parsed.ruc or ""
        )
        duplicate = find_duplicate(db, user, cdc=parsed.cdc, ruc=parsed.ruc, number=parsed.number, stamp=parsed.stamp)
        return InvoiceDraft(
            file_key=key,
            supplier=parsed.supplier,
            ruc=parsed.ruc,
            number=parsed.number,
            stamp=parsed.stamp,
            cdc=parsed.cdc,
            issue_date=parsed.issue_date,
            due_date=parsed.due_date,
            total=parsed.total,
            iva10=parsed.iva10,
            iva5=parsed.iva5,
            exempt=parsed.exempt,
            category_id=suggestion.category_id,
            confidence=1.0 if method in ("xml", "qr") else parsed.confidence,
            method=method,
            ruc_valid=parsed.ruc_valid,
            duplicate_of=(
                DuplicateRef(id=duplicate.id, label=label(duplicate), status=duplicate.status) if duplicate else None
            ),
            raw_text=text[:RAW_TEXT_LIMIT],
        )
    except Exception:
        storage.delete(user.id, key)  # el usuario no recibe la clave: el archivo quedaría huérfano
        raise


def discard_upload(db: Session, user: User, storage: LocalStorage, key: str) -> None:
    """Elimina un archivo analizado que finalmente no se guardó como factura."""
    in_use = db.scalar(select(Invoice.id).where(Invoice.user_id == user.id, Invoice.file_key == key))
    if not in_use and key not in trash.held_file_keys(db, user):
        storage.delete(user.id, key)


# ---------- Alta, edición y pago ----------


def create(db: Session, user: User, storage: LocalStorage, data: InvoiceIn) -> Invoice:
    if data.file_key:
        storage.path(user.id, data.file_key)  # valida que el archivo exista y sea del usuario
        if db.scalar(select(Invoice.id).where(Invoice.file_key == data.file_key)):
            raise ConflictError("Ese archivo ya está asociado a otra factura")
    if not data.allow_duplicate and (
        dup := find_duplicate(db, user, cdc=data.cdc, ruc=data.ruc, number=data.number, stamp=data.stamp)
    ):
        raise ConflictError(f"Ya cargaste esta factura ({label(dup)}). Marcá «Guardar igual» si es otra.")
    category_id = categories.resolve(db, user, data.category_id, CategoryKind.expense)
    inv = Invoice(
        user_id=user.id,
        supplier=data.supplier.strip(),
        ruc=data.ruc.strip(),
        number=data.number.strip(),
        stamp=data.stamp.strip(),
        cdc=data.cdc,
        issue_date=data.issue_date,
        due_date=data.due_date,
        total=data.total,
        iva10=data.iva10,
        iva5=data.iva5,
        exempt=data.exempt,
        irp_deductible=data.irp_deductible,
        category_id=category_id,
        notes=data.notes,
        file_key=data.file_key,
    )
    _check_taxes(inv)
    db.add(inv)
    db.flush()
    rules.learn_from_invoice(db, user, inv.ruc, category_id)
    if data.already_paid:
        return pay(db, user, inv.id, InvoicePayIn(paid_on=data.issue_date, account_id=data.account_id))
    db.refresh(inv)
    return inv


def _check_taxes(inv: Invoice) -> None:
    if inv.iva10 + inv.iva5 + inv.exempt > inv.total and inv.total > 0:
        raise ValidationError("El IVA y las exentas no pueden superar el total de la factura")


def linked_payment(db: Session, invoice_id: int) -> Transaction | None:
    return db.scalar(select(Transaction).where(Transaction.invoice_id == invoice_id))


def update(db: Session, user: User, invoice_id: int, data: InvoiceUpdate) -> Invoice:
    inv = get_owned(db, user, invoice_id, lock=True)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if field == "category_id":
            inv.category_id = categories.resolve(db, user, value, CategoryKind.expense)
        elif value is not None or field in ("issue_date", "due_date", "cdc"):
            setattr(inv, field, value.strip() if isinstance(value, str) and field != "notes" else value)
    _check_taxes(inv)
    if "category_id" in changes or "ruc" in changes:
        rules.learn_from_invoice(db, user, inv.ruc, inv.category_id)
    if payment := linked_payment(db, inv.id):
        # El gasto registrado refleja siempre la factura pagada.
        if inv.total <= 0:
            raise ValidationError("Una factura pagada debe tener un monto mayor a cero")
        payment.amount = inv.total
        payment.category_id = inv.category_id
        if "supplier" in changes or "number" in changes:
            payment.description = _payment_description(inv)
    db.flush()
    db.refresh(inv)
    return inv


def _payment_description(inv: Invoice) -> str:
    return " ".join(p for p in ("Factura", inv.supplier, inv.number) if p)[:160]


def pay(db: Session, user: User, invoice_id: int, data: InvoicePayIn) -> Invoice:
    inv = get_owned(db, user, invoice_id, lock=True)
    if inv.status == InvoiceStatus.paid:
        return inv
    if inv.total <= 0:
        raise ValidationError("La factura no tiene monto para registrar el pago")
    paid_on = data.paid_on or date.today()
    inv.status = InvoiceStatus.paid
    inv.paid_on = paid_on
    db.add(
        Transaction(
            user_id=user.id,
            kind=TransactionKind.expense,
            amount=inv.total,
            date=paid_on,
            method=data.method,
            category_id=inv.category_id,
            account_id=accounts.resolve(db, user, data.account_id),
            description=_payment_description(inv),
            invoice_id=inv.id,
        )
    )
    db.flush()
    db.refresh(inv)
    return inv


def unpay(db: Session, user: User, invoice_id: int) -> Invoice:
    inv = get_owned(db, user, invoice_id, lock=True)
    if payment := linked_payment(db, inv.id):
        db.delete(payment)
    inv.status = InvoiceStatus.pending
    inv.paid_on = None
    db.flush()
    db.refresh(inv)
    return inv


def delete(db: Session, user: User, invoice_id: int) -> int:
    """Manda la factura (y su pago) a la papelera. El archivo se conserva hasta vaciarla."""
    inv = get_owned(db, user, invoice_id, lock=True)
    item = trash.trash_invoice(db, user, inv, linked_payment(db, inv.id))
    db.delete(inv)
    db.flush()
    return item.id


def file_path(db: Session, user: User, storage: LocalStorage, invoice_id: int) -> Path:
    inv = get_owned(db, user, invoice_id)
    if not inv.file_key:
        raise NotFoundError("Archivo")
    return storage.path(user.id, inv.file_key)
