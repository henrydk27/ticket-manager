"""contas cadastradas pelo admin e pedido de nova senha

- usuarios.senha_liberada_em: a pessoa cria a própria senha ao entrar (conta cadastrada pelo
  admin ou nova senha liberada pelo CPD), dentro de 7 dias;
- usuarios.senha_solicitada_em: pedido de nova senha feito na tela de login.

Revision ID: 8e2f4c61a0b7
Revises: 5b1d0e7a93c2
Create Date: 2026-10-13 09:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = "8e2f4c61a0b7"
down_revision = "5b1d0e7a93c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.add_column(sa.Column("senha_liberada_em", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("senha_solicitada_em", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.drop_column("senha_solicitada_em")
        batch_op.drop_column("senha_liberada_em")
