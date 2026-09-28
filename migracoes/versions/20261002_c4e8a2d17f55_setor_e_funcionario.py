"""setor de destino e funcionário no lugar das filas

Simplifica o atendimento: o chamado vai para um setor (setor_destino) e um funcionário.
Quem atende é marcado no cadastro do usuário (usuarios.atende) e atende o próprio setor.

Dados existentes:
- chamados.setor_destino recebe o nome da fila em que o chamado estava (ex.: "T.I");
- administradores e quem era atendente de alguma fila ficam com atende = verdadeiro;
- as tabelas filas, categorias e fila_atendentes são removidas.

Revision ID: c4e8a2d17f55
Revises: a7c3e19f4b20
Create Date: 2026-10-02 09:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = "c4e8a2d17f55"
down_revision = "a7c3e19f4b20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.add_column(sa.Column("atende", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("chamados", schema=None) as batch_op:
        batch_op.add_column(sa.Column("setor_destino", sa.String(length=50), nullable=True))

    # ── dados (só comandos SQL: funciona também com --sql) ──
    filas = sa.table("filas", sa.column("id", sa.Integer), sa.column("nome", sa.String))
    atendentes = sa.table("fila_atendentes", sa.column("usuario_id", sa.Integer))
    usuarios = sa.table("usuarios", sa.column("id", sa.Integer), sa.column("papel", sa.String),
                        sa.column("atende", sa.Boolean))
    chamados = sa.table("chamados", sa.column("fila_id", sa.Integer), sa.column("setor_destino", sa.String))

    nome_da_fila = sa.select(filas.c.nome).where(filas.c.id == chamados.c.fila_id).scalar_subquery()
    op.execute(chamados.update().values(setor_destino=nome_da_fila))
    op.execute(chamados.update().where(chamados.c.setor_destino.is_(None)).values(setor_destino="T.I"))
    op.execute(usuarios.update().where(sa.or_(
        usuarios.c.papel == "admin",
        usuarios.c.id.in_(sa.select(atendentes.c.usuario_id)),
    )).values(atende=True))

    with op.batch_alter_table("chamados", schema=None) as batch_op:
        batch_op.alter_column("setor_destino", existing_type=sa.String(length=50), nullable=False)
        batch_op.create_index("ix_chamados_setor_destino", ["setor_destino"], unique=False)
        batch_op.drop_index("ix_chamados_fila")
        batch_op.drop_constraint("fk_chamados_categoria", type_="foreignkey")
        batch_op.drop_constraint("fk_chamados_fila", type_="foreignkey")
        batch_op.drop_column("categoria_id")
        batch_op.drop_column("fila_id")

    op.drop_table("fila_atendentes")
    op.drop_table("categorias")
    op.drop_table("filas")


def downgrade() -> None:
    op.create_table(
        "filas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=60), nullable=False),
        sa.Column("descricao", sa.String(length=255), nullable=True),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
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

    # Uma fila por setor de destino; atendentes = quem atende aquele setor
    op.execute(sa.text("INSERT INTO filas (nome) SELECT DISTINCT setor_destino FROM chamados"))
    op.execute(sa.text("INSERT INTO filas (nome) SELECT DISTINCT setor FROM usuarios WHERE atende "
                       "AND setor NOT IN (SELECT nome FROM filas)"))
    op.execute(sa.text("UPDATE chamados SET fila_id = (SELECT id FROM filas WHERE filas.nome = chamados.setor_destino)"))
    op.execute(sa.text("INSERT INTO fila_atendentes (fila_id, usuario_id) SELECT f.id, u.id FROM usuarios u "
                       "JOIN filas f ON f.nome = u.setor WHERE u.atende"))

    with op.batch_alter_table("chamados", schema=None) as batch_op:
        batch_op.alter_column("fila_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_index("ix_chamados_setor_destino")
        batch_op.drop_column("setor_destino")
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.drop_column("atende")
