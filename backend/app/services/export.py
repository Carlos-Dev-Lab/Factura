"""Exportaciones en ZIP: todos los datos del usuario y el paquete mensual para el contador."""

import json
import re
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.models import (
    Account,
    Category,
    CategoryRule,
    Invoice,
    ScheduledPayment,
    Transaction,
    Transfer,
    User,
)
from app.services import reports
from app.services.storage import LocalStorage
from app.services.trash import snapshot

_UNSAFE = re.compile(r"[^\w.-]+")


def _safe(name: str, limit: int = 60) -> str:
    return _UNSAFE.sub("_", name).strip("_")[:limit] or "sin_nombre"


def _invoice_filename(inv: Invoice) -> str:
    when = inv.issue_date.isoformat() if inv.issue_date else "sin_fecha"
    ext = inv.file_key.rsplit(".", 1)[-1] if inv.file_key else "bin"
    return f"{when}_{_safe(inv.supplier or 'factura')}_{_safe(inv.number or str(inv.id))}_{inv.id}.{ext}"


def _temp_zip() -> tuple[Path, zipfile.ZipFile]:
    tmp = tempfile.NamedTemporaryFile(prefix="factura-", suffix=".zip", delete=False)  # noqa: SIM115
    tmp.close()
    path = Path(tmp.name)
    return path, zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED)


def full_export(db: Session, user: User, storage: LocalStorage) -> Path:
    """ZIP con todos los datos (JSON), los movimientos (CSV) y los archivos de las facturas."""

    def rows(model: type) -> list[dict]:
        return [snapshot(r) for r in db.scalars(select(model).where(model.user_id == user.id).order_by(model.id))]

    data = {
        "exported_at": datetime.now(UTC).isoformat(),
        "user": {"email": user.email, "name": user.name, "currency": user.currency},
        "categories": rows(Category),
        "accounts": rows(Account),
        "transactions": rows(Transaction),
        "transfers": rows(Transfer),
        "invoices": rows(Invoice),
        "scheduled_payments": rows(ScheduledPayment),
        "category_rules": rows(CategoryRule),
    }
    path, zf = _temp_zip()
    with zf:
        zf.writestr("datos.json", json.dumps(data, ensure_ascii=False, indent=2))
        zf.writestr("movimientos.csv", reports.export_csv(db, user, None))
        for inv in db.scalars(select(Invoice).where(Invoice.user_id == user.id, Invoice.file_key.is_not(None))):
            try:
                zf.write(storage.path(user.id, inv.file_key), f"facturas/{_invoice_filename(inv)}")  # type: ignore[arg-type]
            except NotFoundError:
                continue
    return path


def fiscal_zip(db: Session, user: User, storage: LocalStorage, month: str) -> Path:
    """Paquete para el contador: planilla del mes y los archivos de esas facturas."""
    report = reports.fiscal_report(db, user, month)
    path, zf = _temp_zip()
    with zf:
        zf.writestr(f"compras_{month}.csv", reports.fiscal_csv(report))
        ids = [r.invoice_id for r in report.rows if r.has_file]
        for inv in db.scalars(select(Invoice).where(Invoice.id.in_(ids), Invoice.user_id == user.id)):
            try:
                zf.write(storage.path(user.id, inv.file_key), f"facturas/{_invoice_filename(inv)}")  # type: ignore[arg-type]
            except NotFoundError:
                continue
    return path


def list_backups(limit: int = 10) -> list[dict]:
    """Respaldos automáticos más recientes (los genera el contenedor "db" con backup/backup.sh)."""
    folder = get_settings().backups_dir
    if not folder.is_dir():
        return []
    files = [p for p in folder.iterdir() if p.is_file() and p.name.startswith("factura-")]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {"name": p.name, "size": p.stat().st_size, "created_at": datetime.fromtimestamp(p.stat().st_mtime, UTC)}
        for p in files[:limit]
    ]
