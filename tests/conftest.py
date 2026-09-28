import re

import pytest

from app import create_app
from app.config import Config
from app.modelos import Base
from tests.dados_exemplo import popular


@pytest.fixture
def app(tmp_path):
    cfg = Config(banco_url="sqlite://", secret_key="x" * 40, sessao_horas=1,
                 anexos_pasta=str(tmp_path / "anexos"), anexo_max_mb=1)
    a = create_app(cfg)
    a.config["TESTING"] = True
    a.config["EMAIL_CAPTURA"] = []   # e-mails ficam numa lista em vez de serem enviados
    Base.metadata.create_all(a.extensions["engine"])
    yield a
    a.extensions["engine"].dispose()


@pytest.fixture
def s(app):
    """Sessão própria do teste (separada das requisições) para preparar e conferir dados.

    Depois de uma requisição, use s.expire_all() para reler do banco.
    """
    sessao = app.extensions["sessoes"]()
    yield sessao
    sessao.close()


@pytest.fixture
def contas(s):
    return popular(s)


@pytest.fixture
def emails(app):
    """Lista dos e-mails que o sistema tentou enviar."""
    return app.config["EMAIL_CAPTURA"]


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client, url="/login"):
    html = client.get(url).get_data(as_text=True)
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def entrar(client, login, senha):
    return client.post("/login", data={"login": login, "senha": senha, "csrf": csrf(client)})
