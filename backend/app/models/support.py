"""Tablas de apoyo: reglas de categorías, avisos, papelera y claves del servidor."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.category import Category
from app.models.mixins import OwnedMixin, TimestampMixin


class CategoryRule(OwnedMixin, Base):
    """Regla para categorizar solo: por RUC del proveedor o por texto contenido en la descripción."""

    __tablename__ = "category_rules"
    __table_args__ = (UniqueConstraint("user_id", "match", "pattern", name="uq_rule_user_match_pattern"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match: Mapped[str] = mapped_column(String(10))  # "ruc" o "contains"
    pattern: Mapped[str] = mapped_column(String(80))  # normalizado: minúsculas y sin acentos
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    learned: Mapped[bool] = mapped_column(Boolean, default=True)  # False = la creó el usuario
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    category: Mapped[Category] = relationship(lazy="joined")


class PushSubscription(OwnedMixin, TimestampMixin, Base):
    """Un navegador o celular que acepta notificaciones push."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(80), default="")


class NotificationLog(OwnedMixin, Base):
    """Avisos ya enviados, para no repetir el mismo aviso."""

    __tablename__ = "notification_log"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_notification_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class TrashItem(OwnedMixin, Base):
    """Elemento borrado que se puede restaurar durante 30 días."""

    __tablename__ = "trash"
    __table_args__ = (Index("ix_trash_user_deleted", "user_id", "deleted_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entity: Mapped[str] = mapped_column(String(20))  # transaction, invoice, scheduled, category
    label: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict] = mapped_column(JSONB)
    # Archivo de una factura borrada: se conserva hasta vaciar la papelera.
    file_key: Mapped[str | None] = mapped_column(String(80))
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RevokedSession(Base):
    """Sesión cerrada antes de vencer: su token deja de valer aunque alguien lo haya copiado."""

    __tablename__ = "revoked_sessions"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Pasada esta fecha el token vence solo y la fila se puede borrar.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ServerKey(Base):
    """Valores internos del servidor (claves VAPID, posición de lectura de Telegram)."""

    __tablename__ = "server_keys"

    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
