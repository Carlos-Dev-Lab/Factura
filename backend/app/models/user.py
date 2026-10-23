from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Vacío en las cuentas creadas con Google que todavía no eligieron una contraseña.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(80), default="")
    currency: Mapped[str] = mapped_column(String(3), default="PYG")
    monthly_budget: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    daily_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    # Se incrementa al cambiar la contraseña para invalidar las sesiones existentes.
    session_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # ---------- Avisos ----------
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Hora local (0-23) del resumen diario y cuántos días antes avisar un vencimiento.
    notify_hour: Mapped[int] = mapped_column(SmallInteger, default=8, server_default="8")
    notify_days_before: Mapped[int] = mapped_column(SmallInteger, default=3, server_default="3")
    telegram_chat_id: Mapped[str | None] = mapped_column(String(32))
    # Código de un solo uso para vincular Telegram con "/start <código>".
    telegram_link_code: Mapped[str | None] = mapped_column(String(32), index=True)
    telegram_link_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Email: destino ya verificado y, mientras se confirma uno nuevo, el pendiente con su código.
    email_notify_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    notify_email: Mapped[str | None] = mapped_column(String(254))
    email_pending: Mapped[str | None] = mapped_column(String(254))
    email_code_hash: Mapped[str | None] = mapped_column(String(64))
    email_code_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ---------- Google ----------
    # Identificador estable de la cuenta de Google ("sub"); el email puede cambiar, este no.
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    google_email: Mapped[str | None] = mapped_column(String(254))

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None
