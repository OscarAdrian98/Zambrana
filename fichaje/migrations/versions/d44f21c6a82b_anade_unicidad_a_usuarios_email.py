"""Añade unicidad física a usuarios.email.

Precondición de despliegue: no deben existir duplicados por
LOWER(TRIM(email)). Esta revisión no modifica ni sanea datos.
"""

from alembic import op


revision = "d44f21c6a82b"
down_revision = "a9464fce2497"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_usuarios_email",
        "usuarios",
        ["email"],
    )


def downgrade():
    op.drop_constraint(
        "uq_usuarios_email",
        "usuarios",
        type_="unique",
    )
