"""esquema inicial

Revision ID: 0001
Revises:
Create Date: 2026-10-21 12:20:50.479218
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("monthly_budget", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("daily_limit", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("session_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column(
            "kind", sa.Enum("expense", "income", name="categorykind", native_enum=False, length=10), nullable=False
        ),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", "kind", name="uq_category_user_name_kind"),
    )
    op.create_index(op.f("ix_categories_user_id"), "categories", ["user_id"], unique=False)
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("supplier", sa.String(length=120), nullable=False),
        sa.Column("ruc", sa.String(length=20), nullable=False),
        sa.Column("number", sa.String(length=40), nullable=False),
        sa.Column("stamp", sa.String(length=20), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column(
            "status", sa.Enum("pending", "paid", name="invoicestatus", native_enum=False, length=10), nullable=False
        ),
        sa.Column("file_key", sa.String(length=80), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invoices_user_due", "invoices", ["user_id", "due_date"], unique=False)
    op.create_index(op.f("ix_invoices_user_id"), "invoices", ["user_id"], unique=False)
    op.create_table(
        "scheduled_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("day_of_month", sa.SmallInteger(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("day_of_month BETWEEN 1 AND 31", name="ck_scheduled_day"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scheduled_payments_user_id"), "scheduled_payments", ["user_id"], unique=False)
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "kind", sa.Enum("expense", "income", name="transactionkind", native_enum=False, length=10), nullable=False
        ),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(length=160), nullable=False),
        sa.Column(
            "method",
            sa.Enum("cash", "debit", "credit", "transfer", "qr", name="paymentmethod", native_enum=False, length=10),
            nullable=False,
        ),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("invoice_id", sa.Integer(), nullable=True),
        sa.Column("scheduled_payment_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_transaction_amount_positive"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scheduled_payment_id"], ["scheduled_payments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_id"),
    )
    op.create_index(
        op.f("ix_transactions_scheduled_payment_id"), "transactions", ["scheduled_payment_id"], unique=False
    )
    op.create_index("ix_transactions_user_date", "transactions", ["user_id", "date"], unique=False)
    op.create_index(op.f("ix_transactions_user_id"), "transactions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_transactions_user_id"), table_name="transactions")
    op.drop_index("ix_transactions_user_date", table_name="transactions")
    op.drop_index(op.f("ix_transactions_scheduled_payment_id"), table_name="transactions")
    op.drop_table("transactions")
    op.drop_index(op.f("ix_scheduled_payments_user_id"), table_name="scheduled_payments")
    op.drop_table("scheduled_payments")
    op.drop_index(op.f("ix_invoices_user_id"), table_name="invoices")
    op.drop_index("ix_invoices_user_due", table_name="invoices")
    op.drop_table("invoices")
    op.drop_index(op.f("ix_categories_user_id"), table_name="categories")
    op.drop_table("categories")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
