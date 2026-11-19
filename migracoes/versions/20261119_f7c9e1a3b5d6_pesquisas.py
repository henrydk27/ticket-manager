"""pesquisa de satisfação semestral com a T.I

Revision ID: f7c9e1a3b5d6
Revises: e6b8d0f2a4c5
Create Date: 2026-11-19 14:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = "f7c9e1a3b5d6"
down_revision = "e6b8d0f2a4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pesquisas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=150), nullable=False),
        sa.Column("aberta_em", sa.DateTime(), nullable=False),
        sa.Column("encerra_em", sa.Date(), nullable=False),
        sa.Column("encerrada_em", sa.DateTime(), nullable=True),
        sa.Column("convidados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lembrete_em", sa.DateTime(), nullable=True),
        sa.Column("criado_por_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["criado_por_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "pesquisas_respostas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pesquisa_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("setor", sa.String(length=50), nullable=False),
        sa.Column("resolvidos", sa.String(length=10), nullable=False),
        sa.Column("nota", sa.Integer(), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("respondida_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["pesquisa_id"], ["pesquisas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ux_pesquisa_usuario", "pesquisas_respostas", ["pesquisa_id", "usuario_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_pesquisa_usuario", table_name="pesquisas_respostas")
    op.drop_table("pesquisas_respostas")
    op.drop_table("pesquisas")
