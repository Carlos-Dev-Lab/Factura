"""Tareas en segundo plano: avisos (push y Telegram) y limpieza diaria.

Se ejecuta como un servicio aparte (`python -m app.worker`). Si hay varias copias,
solo una trabaja: toma un bloqueo de PostgreSQL y las demás esperan.
"""

import logging
import signal
import time
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select, text

from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.models import LoginAttempt, User
from app.services import invoices, notify, trash
from app.services.storage import LocalStorage

logger = logging.getLogger("factura.worker")
LEADER_LOCK_ID = 727_003
TICK_SECONDS = 30
URGENT_EVERY = timedelta(minutes=30)  # cada cuánto se revisan avisos importantes nuevos
MAINTENANCE_HOUR = 4

_running = True


def _stop(*_: object) -> None:
    global _running
    _running = False


def run_notifications(now: datetime, last_urgent: dict[int, datetime]) -> None:
    with SessionLocal() as db:
        users = list(db.scalars(select(User).where(User.notifications_enabled.is_(True))))
        for user in users:
            try:
                if not notify.has_channel(db, user):
                    continue
                if notify.should_send_digest(db, user, now):
                    sent = notify.run_digest(db, user, now)
                    last_urgent[user.id] = now
                    logger.info("Resumen de avisos para el usuario %s: %s nuevos", user.id, sent)
                elif (
                    user.notify_hour <= now.hour < notify.QUIET_FROM_HOUR
                    and now - last_urgent.get(user.id, datetime.min) >= URGENT_EVERY
                ):
                    last_urgent[user.id] = now
                    if sent := notify.deliver(db, user, now, digest=False):
                        logger.info("Avisos importantes para el usuario %s: %s", user.id, sent)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("Fallaron los avisos del usuario %s", user.id)


def run_maintenance() -> None:
    storage = LocalStorage(get_settings().storage_dir)
    with SessionLocal() as db:
        purged = trash.purge_expired(db, storage)
        orphans = sum(invoices.purge_orphan_uploads(db, u, storage) for u in db.scalars(select(User)))
        db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < datetime.now(UTC) - timedelta(days=1)))
        notify.prune_log(db, date.today() - timedelta(days=120))
        db.commit()
    logger.info("Mantenimiento: %s de la papelera, %s archivos abandonados", purged, orphans)


def poll_telegram() -> None:
    if not get_settings().telegram_bot_token:
        return
    with SessionLocal() as db:
        try:
            notify.poll_telegram(db, timeout=TICK_SECONDS - 5)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Falló la lectura de Telegram")
            time.sleep(5)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    with engine.connect() as leader:
        lock = text("SELECT pg_try_advisory_lock(:id)")
        while _running and not leader.execute(lock, {"id": LEADER_LOCK_ID}).scalar():
            logger.info("Otro worker está activo; espero")
            time.sleep(60)
        leader.commit()
        logger.info("Worker activo")
        last_urgent: dict[int, datetime] = {}
        last_maintenance: date | None = None
        while _running:
            started = time.monotonic()
            now = datetime.now()
            run_notifications(now, last_urgent)
            if now.hour == MAINTENANCE_HOUR and last_maintenance != now.date():
                run_maintenance()
                last_maintenance = now.date()
            if get_settings().telegram_bot_token:
                poll_telegram()  # espera mensajes nuevos hasta ~25 s (long polling)
            else:
                time.sleep(max(1.0, TICK_SECONDS - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
