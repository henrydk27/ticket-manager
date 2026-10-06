"""documentos internos e ordenação natural do patrimônio

- documentos: termos, regras e procedimentos da empresa (arquivo em disco, como os anexos);
- equipamentos.patrimonio_ordem: chave para ordenar o patrimônio pelo valor do número
  ("2" antes de "10"), preenchida aqui para os equipamentos que já existem.

Revision ID: 5b1d0e7a93c2
Revises: 246567826a93
Create Date: 2026-10-06 11:00:00
"""
import sqlalchemy as sa
from alembic import context, op

from app.modelos import ordem_natural

revision = "5b1d0e7a93c2"
down_revision = "246567826a93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documentos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=150), nullable=False),
        sa.Column("categoria", sa.String(length=40), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("tipo", sa.String(length=100), nullable=False),
        sa.Column("tamanho", sa.Integer(), nullable=False),
        sa.Column("arquivo", sa.String(length=100), nullable=False),
        sa.Column("autor_id", sa.Integer(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["autor_id"], ["usuarios.id"], name="fk_documentos_autor", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_documentos"),
        sa.UniqueConstraint("arquivo", name="uq_documentos_arquivo"),
    )
    op.create_index("ix_documentos_categoria", "documentos", ["categoria"], unique=False)

    with op.batch_alter_table("equipamentos", schema=None) as batch_op:
        batch_op.add_column(sa.Column("patrimonio_ordem", sa.String(length=500), nullable=False,
                                      server_default=""))

    # Preenche a chave dos equipamentos já cadastrados (precisa do banco: não vale para --sql)
    if not context.is_offline_mode():
        equipamentos = sa.table("equipamentos", sa.column("id", sa.Integer), sa.column("patrimonio", sa.String),
                                sa.column("patrimonio_ordem", sa.String))
        conn = op.get_bind()
        for id_, patrimonio in conn.execute(sa.select(equipamentos.c.id, equipamentos.c.patrimonio)).all():
            conn.execute(equipamentos.update().where(equipamentos.c.id == id_)
                         .values(patrimonio_ordem=ordem_natural(patrimonio)))


def downgrade() -> None:
    with op.batch_alter_table("equipamentos", schema=None) as batch_op:
        batch_op.drop_column("patrimonio_ordem")
    op.drop_index("ix_documentos_categoria", table_name="documentos")
    op.drop_table("documentos")
