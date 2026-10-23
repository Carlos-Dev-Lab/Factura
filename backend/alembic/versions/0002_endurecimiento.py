"""intentos de login en base de datos y archivo único por factura

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_login_attempts_key_created", "login_attempts", ["key", "created_at"], unique=False)
    op.create_index(op.f("ix_login_attempts_created_at"), "login_attempts", ["created_at"], unique=False)

    # Si por algún motivo dos facturas comparten archivo, se conserva el vínculo en la más antigua.
    op.execute(
        """
        UPDATE invoices SET file_key = NULL
        WHERE file_key IS NOT NULL
          AND id NOT IN (SELECT MIN(id) FROM invoices WHERE file_key IS NOT NULL GROUP BY file_key)
        """
    )
    op.create_unique_constraint("uq_invoices_file_key", "invoices", ["file_key"])


def downgrade() -> None:
    op.drop_constraint("uq_invoices_file_key", "invoices", type_="unique")
    op.drop_index(op.f("ix_login_attempts_created_at"), table_name="login_attempts")
    op.drop_index("ix_login_attempts_key_created", table_name="login_attempts")
    op.drop_table("login_attempts")
