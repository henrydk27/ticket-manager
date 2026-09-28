"""Conexão com o banco: um engine por processo, uma sessão por requisição."""

from flask import Flask, current_app, g
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def criar_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        # SQLite (testes/demonstração): mesma conexão entre threads e chaves estrangeiras ativas
        kw = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kw["poolclass"] = StaticPool
        engine = create_engine(url, **kw)

        @event.listens_for(engine, "connect")
        def _fk(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
        return engine

    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)


def iniciar(app: Flask, url: str) -> None:
    engine = criar_engine(url)
    app.extensions["engine"] = engine
    app.extensions["sessoes"] = sessionmaker(engine, expire_on_commit=False)

    @app.teardown_appcontext
    def _fechar(_exc):
        sessao = g.pop("db", None)
        if sessao is not None:
            sessao.close()


def db() -> Session:
    """Sessão da requisição atual (criada na primeira chamada)."""
    if "db" not in g:
        g.db = current_app.extensions["sessoes"]()
    return g.db
