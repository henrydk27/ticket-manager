"""comentários editados pelo administrador

- comentarios.editado_em e comentarios.editado_por_id: quem corrigiu o texto e quando.

Revision ID: c91d3e5a7f20
Revises: 8e2f4c61a0b7
Create Date: 2026-10-15 09:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = "c91d3e5a7f20"
down_revision = "8e2f4c61a0b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("comentarios", schema=None) as batch_op:
        batch_op.add_column(sa.Column("editado_em", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("editado_por_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_comentarios_editado_por", "usuarios", ["editado_por_id"], ["id"],
                                    ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("comentarios", schema=None) as batch_op:
        batch_op.drop_constraint("fk_comentarios_editado_por", type_="foreignkey")
        batch_op.drop_column("editado_por_id")
        batch_op.drop_column("editado_em")
