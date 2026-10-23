"""Motor y sesiones de SQLAlchemy."""

import logging
from collections.abc import Callable, Iterator
from typing import TypeVar

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)
T = TypeVar("T")


class Base(DeclarativeBase):
    pass


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def fetch(db: Session, model: type[T], obj_id: int, *, lock: bool = False) -> T | None:
    """Busca por id. Con `lock` bloquea la fila hasta el fin de la transacción.

    Así dos pedidos simultáneos sobre el mismo registro (un doble toque en "Pagar", dos
    dispositivos a la vez) se atienden de a uno: el segundo ve lo que dejó el primero y no
    duplica el pago ni choca al restaurar. "OF tabla": no bloquea las tablas unidas con JOIN.
    """
    if lock:
        return db.get(model, obj_id, with_for_update={"of": model}, populate_existing=True)
    return db.get(model, obj_id)


def on_commit(db: Session, action: Callable[[], None]) -> None:
    """Ejecuta `action` solo si la transacción se confirma.

    Sirve para efectos fuera de la base (como borrar archivos): si el commit
    falla, el archivo no se pierde y los datos quedan coherentes.
    """

    def _run(_: Session) -> None:
        try:
            action()
        except Exception:
            logger.exception("Falló una acción posterior al commit")

    event.listen(db, "after_commit", _run, once=True)


def contains_pattern(text: str) -> str:
    """Patrón LIKE que busca `text` literal (sin que % o _ actúen como comodines)."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
