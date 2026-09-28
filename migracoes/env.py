"""Ambiente do Alembic: usa a URL do config.ini (ou a passada por manage.py)."""

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import carregar_config
from app.modelos import Base

config = context.config
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", carregar_config().banco_url.replace("%", "%%"))

target_metadata = Base.metadata


def rodar_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata,
                      literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def rodar_online() -> None:
    engine = engine_from_config(config.get_section(config.config_ini_section, {}),
                                prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as conn:
        # render_as_batch: permite ALTER TABLE também no SQLite (demonstração/testes)
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    rodar_offline()
else:
    rodar_online()
