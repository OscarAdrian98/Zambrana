"""añadir horas medico"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "a9464fce2497"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ausencias", sa.Column("hora_desde", sa.Time(), nullable=True))
    op.add_column("ausencias", sa.Column("hora_hasta", sa.Time(), nullable=True))


def downgrade():
    op.drop_column("ausencias", "hora_hasta")
    op.drop_column("ausencias", "hora_desde")
