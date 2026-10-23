from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LoginAttempt(Base):
    """Intento de inicio de sesión fallido, para limitar la fuerza bruta."""

    __tablename__ = "login_attempts"
    __table_args__ = (Index("ix_login_attempts_key_created", "key", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
