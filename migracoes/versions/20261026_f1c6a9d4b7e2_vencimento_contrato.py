"""documentos: data de vencimento dos contratos

Revision ID: f1c6a9d4b7e2
Revises: e5b8c3f1a2d6
Create Date: 2026-10-26 09:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = "f1c6a9d4b7e2"
down_revision = "e5b8c3f1a2d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documentos", schema=None) as batch_op:
        batch_op.add_column(sa.Column("vencimento", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("documentos", schema=None) as batch_op:
        batch_op.drop_column("vencimento")
