"""ingreso con Google y avisos por email

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-23 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Las cuentas creadas con Google pueden no tener contraseña.
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=True)
    op.add_column("users", sa.Column("google_sub", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("google_email", sa.String(length=254), nullable=True))
    op.create_index(op.f("ix_users_google_sub"), "users", ["google_sub"], unique=True)
    op.add_column(
        "users", sa.Column("email_notify_enabled", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column("users", sa.Column("notify_email", sa.String(length=254), nullable=True))
    op.add_column("users", sa.Column("email_pending", sa.String(length=254), nullable=True))
    op.add_column("users", sa.Column("email_code_hash", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("email_code_expires", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "email_code_expires")
    op.drop_column("users", "email_code_hash")
    op.drop_column("users", "email_pending")
    op.drop_column("users", "notify_email")
    op.drop_column("users", "email_notify_enabled")
    op.drop_index(op.f("ix_users_google_sub"), table_name="users")
    op.drop_column("users", "google_email")
    op.drop_column("users", "google_sub")
    # Una cuenta solo-Google no tiene contraseña: sin Google no podría entrar. Se le asigna un
    # hash imposible de acertar; puede recuperar el acceso cambiando la contraseña desde la base.
    op.execute("UPDATE users SET password_hash = '!sin-contrasena' WHERE password_hash IS NULL")
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=False)
