"""Orden personalizado de categorías."""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("categories", sa.Column("sort_order", sa.Integer(), nullable=True))

def downgrade():
    op.drop_column("categories", "sort_order")
