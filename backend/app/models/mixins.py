from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OwnedMixin:
    """Toda entidad de negocio pertenece a un usuario."""

    @declared_attr
    def user_id(cls) -> Mapped[int]:  # noqa: N805
        return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
