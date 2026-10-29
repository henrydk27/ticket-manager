"""lembretes por e-mail de avaliação dos chamados encerrados

Revision ID: b3e5a7c9d1f2
Revises: a2d4f6b8c0e1
Create Date: 2026-10-29 14:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = "b3e5a7c9d1f2"
down_revision = "a2d4f6b8c0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("chamados", schema=None) as batch_op:
        batch_op.add_column(sa.Column("lembretes_avaliacao", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("ultimo_lembrete_em", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chamados", schema=None) as batch_op:
        batch_op.drop_column("ultimo_lembrete_em")
        batch_op.drop_column("lembretes_avaliacao")
