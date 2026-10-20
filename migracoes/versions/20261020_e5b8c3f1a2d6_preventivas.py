"""revisão preventiva dos ativos

- planos_preventiva: periodicidade e checklist por tipo de equipamento;
- preventivas: cada revisão feita, com o checklist, peças, observações, anexo e chamado aberto;
- equipamentos.preventiva_meses: periodicidade própria do equipamento (vazio = plano do tipo).

Revision ID: e5b8c3f1a2d6
Revises: d4a7b2e9c315
Create Date: 2026-10-20 14:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = "e5b8c3f1a2d6"
down_revision = "d4a7b2e9c315"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "planos_preventiva",
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("meses", sa.Integer(), nullable=False),
        sa.Column("itens", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("tipo", name="pk_planos_preventiva"),
    )
    op.create_table(
        "preventivas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipamento_id", sa.Integer(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("tecnico_id", sa.Integer(), nullable=True),
        sa.Column("resultados", sa.Text(), nullable=False),
        sa.Column("pecas", sa.Text(), nullable=True),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column("chamado_id", sa.Integer(), nullable=True),
        sa.Column("anexo_nome", sa.String(length=255), nullable=True),
        sa.Column("anexo_arquivo", sa.String(length=100), nullable=True),
        sa.Column("anexo_tipo", sa.String(length=100), nullable=True),
        sa.Column("anexo_tamanho", sa.Integer(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["equipamento_id"], ["equipamentos.id"], name="fk_preventivas_equipamento",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tecnico_id"], ["usuarios.id"], name="fk_preventivas_tecnico", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["chamado_id"], ["chamados.id"], name="fk_preventivas_chamado", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_preventivas"),
        sa.UniqueConstraint("anexo_arquivo", name="uq_preventivas_anexo"),
    )
    op.create_index("ix_preventivas_equipamento", "preventivas", ["equipamento_id"], unique=False)
    op.create_index("ix_preventivas_data", "preventivas", ["data"], unique=False)
    with op.batch_alter_table("equipamentos", schema=None) as batch_op:
        batch_op.add_column(sa.Column("preventiva_meses", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("equipamentos", schema=None) as batch_op:
        batch_op.drop_column("preventiva_meses")
    op.drop_index("ix_preventivas_data", table_name="preventivas")
    op.drop_index("ix_preventivas_equipamento", table_name="preventivas")
    op.drop_table("preventivas")
    op.drop_table("planos_preventiva")
