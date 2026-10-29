"""diagramas da infraestrutura (imagem + arquivo editável do draw.io)

Revision ID: a2d4f6b8c0e1
Revises: f1c6a9d4b7e2
Create Date: 2026-10-29 10:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = "a2d4f6b8c0e1"
down_revision = "f1c6a9d4b7e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagramas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=150), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("tamanho", sa.Integer(), nullable=False),
        sa.Column("arquivo", sa.String(length=100), nullable=False),
        sa.Column("editavel_nome", sa.String(length=255), nullable=True),
        sa.Column("editavel_tamanho", sa.Integer(), nullable=True),
        sa.Column("editavel_arquivo", sa.String(length=100), nullable=True),
        sa.Column("autor_id", sa.Integer(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["autor_id"], ["usuarios.id"], name="fk_diagramas_autor", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_diagramas"),
        sa.UniqueConstraint("arquivo", name="uq_diagramas_arquivo"),
        sa.UniqueConstraint("editavel_arquivo", name="uq_diagramas_editavel"),
    )


def downgrade() -> None:
    op.drop_table("diagramas")
