"""sesiones revocadas al cerrar sesión

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-23 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "revoked_sessions",
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("jti"),
    )
    op.create_index(op.f("ix_revoked_sessions_expires_at"), "revoked_sessions", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_revoked_sessions_expires_at"), table_name="revoked_sessions")
    op.drop_table("revoked_sessions")
