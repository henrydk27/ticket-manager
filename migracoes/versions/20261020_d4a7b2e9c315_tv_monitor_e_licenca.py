"""inventário: tipo "TV/Monitor" e licença do Windows

- equipamentos.licenca_windows: chave de produto (XXXXX-XXXXX-XXXXX-XXXXX-XXXXX);
- o tipo "Monitor" passa a se chamar "TV/Monitor" nos equipamentos já cadastrados.

Revision ID: d4a7b2e9c315
Revises: c91d3e5a7f20
Create Date: 2026-10-20 09:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = "d4a7b2e9c315"
down_revision = "c91d3e5a7f20"
branch_labels = None
depends_on = None

equipamentos = sa.table("equipamentos", sa.column("tipo", sa.String))


def upgrade() -> None:
    with op.batch_alter_table("equipamentos", schema=None) as batch_op:
        batch_op.add_column(sa.Column("licenca_windows", sa.String(length=29), nullable=True))
    op.execute(equipamentos.update().where(equipamentos.c.tipo == "Monitor").values(tipo="TV/Monitor"))


def downgrade() -> None:
    op.execute(equipamentos.update().where(equipamentos.c.tipo == "TV/Monitor").values(tipo="Monitor"))
    with op.batch_alter_table("equipamentos", schema=None) as batch_op:
        batch_op.drop_column("licenca_windows")
