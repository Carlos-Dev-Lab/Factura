"""código de vinculación de Telegram más largo (no se puede adivinar probando)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-21 23:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "telegram_link_code", type_=sa.String(length=32), existing_type=sa.String(length=16))


def downgrade() -> None:
    # Los códigos son temporales (15 minutos): se descartan los pendientes que no entran.
    op.execute("UPDATE users SET telegram_link_code = NULL WHERE length(telegram_link_code) > 16")
    op.alter_column("users", "telegram_link_code", type_=sa.String(length=16), existing_type=sa.String(length=32))
