"""Papelera, importación de extractos, exportación completa y respaldos."""

import json
import os

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import ValidationError as PydanticValidationError
from starlette.background import BackgroundTask

from app.api.deps import DB, CurrentUser, PathId, Storage, verify_csrf
from app.core.errors import ForbiddenError, ValidationError
from app.models import TrashItem
from app.schemas.support import (
    BackupOut,
    ImportCommit,
    ImportMapping,
    ImportPreview,
    ImportResult,
    RestoredOut,
    TrashOut,
)
from app.services import export, imports, trash, users

router = APIRouter(tags=["datos"], dependencies=[Depends(verify_csrf)])


# ---------- Papelera ----------


@router.get("/trash", response_model=list[TrashOut])
def list_trash(user: CurrentUser, db: DB) -> list[TrashItem]:
    return trash.list_items(db, user)


@router.post("/trash/{item_id}/restore", response_model=RestoredOut)
def restore(item_id: PathId, user: CurrentUser, db: DB) -> RestoredOut:
    entity, obj_id = trash.restore(db, user, item_id)
    return RestoredOut(entity=entity, id=obj_id)


@router.delete("/trash/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_trash(item_id: PathId, user: CurrentUser, db: DB, storage: Storage) -> None:
    trash.remove(db, user, storage, item_id)


@router.delete("/trash", status_code=status.HTTP_204_NO_CONTENT)
def empty_trash(user: CurrentUser, db: DB, storage: Storage) -> None:
    trash.empty(db, user, storage)


# ---------- Importación de extractos ----------


@router.post("/imports/preview", response_model=ImportPreview)
def import_preview(
    user: CurrentUser, db: DB, file: UploadFile = File(...), mapping: str | None = Form(None)
) -> ImportPreview:
    chosen = None
    if mapping:
        try:
            chosen = ImportMapping.model_validate(json.loads(mapping))
        except (json.JSONDecodeError, PydanticValidationError) as exc:
            raise ValidationError("Columnas elegidas inválidas") from exc
    content = file.file.read(imports.MAX_IMPORT_BYTES + 1)
    return imports.preview(db, user, content, chosen)


@router.post("/imports/commit", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
def import_commit(data: ImportCommit, user: CurrentUser, db: DB) -> ImportResult:
    return imports.commit(db, user, data)


# ---------- Exportación y respaldos ----------


@router.get("/export/full.zip")
def full_export(user: CurrentUser, db: DB, storage: Storage) -> FileResponse:
    path = export.full_export(db, user, storage)
    return FileResponse(
        path, media_type="application/zip", filename="factura_mis_datos.zip", background=BackgroundTask(os.remove, path)
    )


@router.get("/system/backups", response_model=list[BackupOut])
def list_backups(user: CurrentUser, db: DB) -> list[dict]:
    """Respaldos automáticos del servidor (solo nombre, tamaño y fecha; no se descargan desde la web).

    Son de todo el servidor, no de una cuenta: solo los ve quien lo administra.
    """
    if not users.is_admin(db, user):
        raise ForbiddenError("Solo quien administra el servidor ve los respaldos")
    return export.list_backups()
