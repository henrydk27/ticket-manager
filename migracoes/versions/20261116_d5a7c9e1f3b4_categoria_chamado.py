"""categoria do chamado: problema, solicitação ou dúvida

Revision ID: d5a7c9e1f3b4
Revises: c4f6b8d0e2a3
Create Date: 2026-11-16 09:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = "d5a7c9e1f3b4"
down_revision = "c4f6b8d0e2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("chamados", schema=None) as batch_op:
        batch_op.add_column(sa.Column("categoria", sa.String(length=15), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chamados", schema=None) as batch_op:
        batch_op.drop_column("categoria")
