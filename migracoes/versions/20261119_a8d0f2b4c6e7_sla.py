"""SLA: impacto x urgência, metas por categoria e prioridade e relógios do chamado

Revision ID: a8d0f2b4c6e7
Revises: f7c9e1a3b5d6
Create Date: 2026-11-19 18:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = "a8d0f2b4c6e7"
down_revision = "f7c9e1a3b5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metas_sla",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("categoria", sa.String(length=15), nullable=False),
        sa.Column("prioridade", sa.String(length=10), nullable=False),
        sa.Column("atendimento_min", sa.Integer(), nullable=True),
        sa.Column("solucao_min", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ux_metas_sla", "metas_sla", ["categoria", "prioridade"], unique=True)
    with op.batch_alter_table("chamados") as t:
        t.add_column(sa.Column("impacto", sa.String(length=10), nullable=True))
        t.add_column(sa.Column("urgencia", sa.String(length=10), nullable=True))
        t.add_column(sa.Column("sla_inicio", sa.DateTime(), nullable=True))
        t.add_column(sa.Column("sla_atendimento_min", sa.Integer(), nullable=True))
        t.add_column(sa.Column("sla_solucao_min", sa.Integer(), nullable=True))
        t.add_column(sa.Column("primeiro_atendimento_em", sa.DateTime(), nullable=True))
        t.add_column(sa.Column("pausado_em", sa.DateTime(), nullable=True))
        t.add_column(sa.Column("pausa_segundos", sa.Integer(), nullable=False, server_default="0"))
        t.add_column(sa.Column("sla_aviso_atendimento", sa.Integer(), nullable=False, server_default="0"))
        t.add_column(sa.Column("sla_aviso_solucao", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("chamados") as t:
        for coluna in ("sla_aviso_solucao", "sla_aviso_atendimento", "pausa_segundos", "pausado_em",
                       "primeiro_atendimento_em", "sla_solucao_min", "sla_atendimento_min", "sla_inicio",
                       "urgencia", "impacto"):
            t.drop_column(coluna)
    op.drop_index("ux_metas_sla", table_name="metas_sla")
    op.drop_table("metas_sla")
