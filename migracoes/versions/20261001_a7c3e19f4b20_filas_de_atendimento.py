"""filas de atendimento

Cria filas (setores que atendem pedidos), seus atendentes e tipos de pedido.

Dados existentes:
- cria a fila "T.I" com tipos de pedido padrão;
- todos os chamados já abertos passam a pertencer à fila T.I;
- técnicos e administradores viram atendentes da fila T.I;
- o papel "técnico" deixa de existir (vira "usuário"; quem atende é definido pelas filas).

Revision ID: a7c3e19f4b20
Revises: ef9138d44dc3
Create Date: 2026-10-01 09:00:00
"""
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "a7c3e19f4b20"
down_revision = "ef9138d44dc3"
branch_labels = None
depends_on = None

TIPOS_TI = ["Acesso e senha", "Computador", "E-mail", "Impressora", "Outros", "Rede e internet", "Sistemas"]


def upgrade() -> None:
    op.create_table(
        "filas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=60), nullable=False),
        sa.Column("descricao", sa.String(length=255), nullable=True),
        sa.Column("ativa", sa.Boolean(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nome"),
    )
    op.create_table(
        "categorias",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fila_id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=60), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["fila_id"], ["filas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fila_id", "nome", name="uq_categorias_fila_nome"),
    )
    op.create_table(
        "fila_atendentes",
        sa.Column("fila_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["fila_id"], ["filas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("fila_id", "usuario_id"),
    )

    with op.batch_alter_table("chamados", schema=None) as batch_op:
        batch_op.add_column(sa.Column("fila_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("categoria_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_chamados_fila", "filas", ["fila_id"], ["id"])
        batch_op.create_foreign_key("fk_chamados_categoria", "categorias", ["categoria_id"], ["id"],
                                    ondelete="SET NULL")
        batch_op.create_index("ix_chamados_fila", ["fila_id"], unique=False)

    # ── dados (só comandos SQL, sem ler resultados: funciona também com --sql) ──
    filas = sa.table("filas", sa.column("id", sa.Integer), sa.column("nome", sa.String),
                     sa.column("descricao", sa.String), sa.column("ativa", sa.Boolean),
                     sa.column("criado_em", sa.DateTime))
    categorias = sa.table("categorias", sa.column("fila_id", sa.Integer), sa.column("nome", sa.String),
                          sa.column("ativa", sa.Boolean))
    atendentes = sa.table("fila_atendentes", sa.column("fila_id", sa.Integer),
                          sa.column("usuario_id", sa.Integer))
    usuarios = sa.table("usuarios", sa.column("id", sa.Integer), sa.column("papel", sa.String))
    chamados = sa.table("chamados", sa.column("fila_id", sa.Integer))
    ti = sa.select(filas.c.id).where(filas.c.nome == "T.I").scalar_subquery()

    op.execute(filas.insert().values(
        nome="T.I", descricao="Computadores, impressoras, sistemas, acessos, rede e e-mail",
        ativa=True, criado_em=datetime.now().replace(microsecond=0)))
    for nome in TIPOS_TI:
        op.execute(categorias.insert().values(fila_id=ti, nome=nome, ativa=True))
    op.execute(chamados.update().values(fila_id=ti))
    op.execute(atendentes.insert().from_select(
        ["fila_id", "usuario_id"],
        sa.select(ti, usuarios.c.id).where(usuarios.c.papel.in_(("tecnico", "admin")))))
    op.execute(usuarios.update().where(usuarios.c.papel == "tecnico").values(papel="usuario"))

    with op.batch_alter_table("chamados", schema=None) as batch_op:
        batch_op.alter_column("fila_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    conn = op.get_bind()
    # Atendentes que não são admin voltam a ser "técnico"
    conn.execute(sa.text(
        "UPDATE usuarios SET papel = 'tecnico' WHERE papel = 'usuario' "
        "AND id IN (SELECT usuario_id FROM fila_atendentes)"))

    with op.batch_alter_table("chamados", schema=None) as batch_op:
        batch_op.drop_index("ix_chamados_fila")
        batch_op.drop_constraint("fk_chamados_categoria", type_="foreignkey")
        batch_op.drop_constraint("fk_chamados_fila", type_="foreignkey")
        batch_op.drop_column("categoria_id")
        batch_op.drop_column("fila_id")

    op.drop_table("fila_atendentes")
    op.drop_table("categorias")
    op.drop_table("filas")
