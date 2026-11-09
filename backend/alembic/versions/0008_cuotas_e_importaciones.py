"""Separa el mes de la cuota y registra las confirmaciones de importación."""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("scheduled_month", sa.Date(), nullable=True))
    op.execute("""
        UPDATE transactions
        SET scheduled_month = date_trunc('month', date)::date
        WHERE scheduled_payment_id IS NOT NULL
    """)
    op.create_table(
        "import_batches",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("fingerprint", sa.String(64), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("import_batches")
    op.drop_column("transactions", "scheduled_month")
