"""tarefas recorrentes da T.I e o histórico de execução

Revision ID: c4f6b8d0e2a3
Revises: b3e5a7c9d1f2
Create Date: 2026-10-30 10:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = "c4f6b8d0e2a3"
down_revision = "b3e5a7c9d1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tarefas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=150), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("repeticao", sa.String(length=10), nullable=False),
        sa.Column("inicio", sa.Date(), nullable=False),
        sa.Column("dia_mes", sa.Integer(), nullable=True),
        sa.Column("dia_semana", sa.Integer(), nullable=True),
        sa.Column("intervalo_meses", sa.Integer(), nullable=True),
        sa.Column("avisar_dias", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("responsavel_id", sa.Integer(), nullable=True),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("proxima", sa.Date(), nullable=True),
        sa.Column("criado_por_id", sa.Integer(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["responsavel_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["criado_por_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tarefas_proxima", "tarefas", ["proxima"])
    op.create_table(
        "tarefas_execucoes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tarefa_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("data_prevista", sa.Date(), nullable=False),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("feita_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tarefa_id"], ["tarefas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tarefas_execucoes_tarefa", "tarefas_execucoes", ["tarefa_id"])


def downgrade() -> None:
    op.drop_index("ix_tarefas_execucoes_tarefa", table_name="tarefas_execucoes")
    op.drop_table("tarefas_execucoes")
    op.drop_index("ix_tarefas_proxima", table_name="tarefas")
    op.drop_table("tarefas")
