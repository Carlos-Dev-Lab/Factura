"""Almacenamiento de archivos de facturas, aislado por usuario.

El tipo se determina por la firma binaria del archivo (no por la extensión que
envía el cliente) y el nombre en disco es aleatorio. Para escalar a varias
instancias, sustituir esta clase por una implementación S3 con la misma interfaz.
"""

import re
import time
import uuid
from pathlib import Path

from app.core.errors import NotFoundError

_SIGNATURES: list[tuple[bytes, str]] = [
    (b"%PDF-", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
]
_KEY_RE = re.compile(r"^[a-f0-9]{32}\.(pdf|png|jpg|webp|xml)$")
MEDIA_TYPES = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "webp": "image/webp",
    "xml": "application/xml",
}
# Tipos que el navegador puede mostrar sin riesgo. El XML se descarga: un XML puede traer
# XHTML con scripts y, abierto en el mismo origen, sería una puerta para XSS.
INLINE_TYPES = {"pdf", "png", "jpg", "webp"}


def detect_file_type(content: bytes) -> str | None:
    """Tipo real del archivo según su contenido (no según el nombre o lo que diga el navegador)."""
    for signature, ext in _SIGNATURES:
        if content.startswith(signature):
            return ext
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    from app.services.sifen import looks_like_sifen_xml  # import local: sifen depende del parser

    if looks_like_sifen_xml(content):
        return "xml"
    return None


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _user_dir(self, user_id: int) -> Path:
        d = self.root / str(user_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save(self, user_id: int, data: bytes, ext: str) -> str:
        key = f"{uuid.uuid4().hex}.{ext}"
        (self._user_dir(user_id) / key).write_bytes(data)
        return key

    def path(self, user_id: int, key: str) -> Path:
        if not _KEY_RE.fullmatch(key):
            raise NotFoundError("Archivo")
        p = self._user_dir(user_id) / key
        if not p.is_file():
            raise NotFoundError("Archivo")
        return p

    def delete(self, user_id: int, key: str) -> None:
        if _KEY_RE.fullmatch(key):
            (self._user_dir(user_id) / key).unlink(missing_ok=True)

    def keys_older_than(self, user_id: int, seconds: float) -> list[str]:
        """Archivos del usuario que no se modificaron en los últimos `seconds` segundos."""
        limit = time.time() - seconds
        return [
            p.name for p in self._user_dir(user_id).iterdir() if _KEY_RE.fullmatch(p.name) and p.stat().st_mtime < limit
        ]
