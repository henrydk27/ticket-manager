"""categorias no padrão ITIL: Incidente, Solicitação e Problema (este, só a T.I)

Quem abriu como "Problema" relatava uma falha (Incidente); "Dúvida" vira Solicitação.

Revision ID: e6b8d0f2a4c5
Revises: d5a7c9e1f3b4
Create Date: 2026-11-19 09:00:00
"""
from alembic import op

revision = "e6b8d0f2a4c5"
down_revision = "d5a7c9e1f3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE chamados SET categoria = 'Incidente' WHERE categoria = 'Problema'")
    op.execute("UPDATE chamados SET categoria = 'Solicitação' WHERE categoria = 'Dúvida'")


def downgrade() -> None:
    op.execute("UPDATE chamados SET categoria = 'Problema' WHERE categoria = 'Incidente'")
