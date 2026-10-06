"""Testes da tela de documentos internos e da ordenação do patrimônio."""

import io
import os

from sqlalchemy import select

from app.modelos import Documento
from tests.conftest import csrf, entrar
from tests.test_inventario import cadastrar


def doc(s, titulo) -> Documento:
    s.expire_all()
    return s.scalar(select(Documento).where(Documento.titulo == titulo))


def enviar(client, url="/documentos/novo", arquivo=("termo.pdf", b"%PDF-1.4 teste"), **campos):
    dados = {"csrf": csrf(client, url), "titulo": "Termo de uso de equipamentos", "categoria": "Termos",
             "descricao": "Vale para todos."}
    dados.update(campos)
    if arquivo:
        dados["arquivo"] = (io.BytesIO(arquivo[1]), arquivo[0])
    return client.post(url, data=dados, content_type="multipart/form-data", follow_redirects=True)


def test_so_admin_cadastra_e_todos_consultam(client, s, app, contas):
    entrar(client, "ana", "ana12345")
    html = client.get("/documentos/").get_data(as_text=True)
    assert "Nenhum documento cadastrado" in html and "/documentos/novo" not in html
    assert client.get("/documentos/novo").status_code == 403

    client.post("/logout", data={"csrf": csrf(client, "/conta/")})
    entrar(client, "admin", "admin123")
    r = enviar(client)
    assert r.request.path == "/documentos/" and "cadastrado" in r.get_data(as_text=True)
    d = doc(s, "Termo de uso de equipamentos")
    assert d.nome == "termo.pdf" and d.categoria == "Termos" and d.autor.login == "admin"
    assert os.path.exists(os.path.join(app.config["ANEXOS_PASTA"], d.arquivo))

    client.post("/logout", data={"csrf": csrf(client, "/conta/")})
    entrar(client, "ana", "ana12345")
    html = client.get("/documentos/").get_data(as_text=True)
    assert "Termo de uso de equipamentos" in html and "Editar" not in html
    r = client.get(f"/documentos/{d.id}/arquivo")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data.startswith(b"%PDF")
    assert "attachment" in client.get(f"/documentos/{d.id}/arquivo?baixar=1").headers["Content-Disposition"]
    assert client.post(f"/documentos/{d.id}/apagar", data={"csrf": csrf(client, "/conta/")}).status_code == 403


def test_validacoes_trocar_arquivo_e_apagar(client, s, app, contas):
    entrar(client, "admin", "admin123")
    assert "Escolha o arquivo" in enviar(client, arquivo=None).get_data(as_text=True)
    assert "não aceito" in enviar(client, arquivo=("script.zip", b"PK")).get_data(as_text=True)
    assert "Escolha a categoria" in enviar(client, categoria="").get_data(as_text=True)
    assert s.scalar(select(Documento.id)) is None

    enviar(client)
    d = doc(s, "Termo de uso de equipamentos")
    antigo = d.arquivo
    url = f"/documentos/{d.id}/editar"
    r = enviar(client, url, arquivo=None, titulo="Termo de uso (2026)")       # sem arquivo: mantém o atual
    assert "salvo" in r.get_data(as_text=True)
    d = doc(s, "Termo de uso (2026)")
    assert d.arquivo == antigo
    enviar(client, url, arquivo=("regras.docx", b"novo"), titulo="Termo de uso (2026)")
    d = doc(s, "Termo de uso (2026)")
    pasta = app.config["ANEXOS_PASTA"]
    assert d.nome == "regras.docx" and not os.path.exists(os.path.join(pasta, antigo))

    html = client.get("/documentos/?categoria=Termos&q=2026").get_data(as_text=True)
    assert "Termo de uso (2026)" in html
    assert "Nenhum documento encontrado" in client.get("/documentos/?categoria=Formulários").get_data(as_text=True)

    client.post(f"/documentos/{d.id}/apagar", data={"csrf": csrf(client, "/documentos/")})
    assert s.scalar(select(Documento.id)) is None and os.listdir(pasta) == []


def test_ordenar_patrimonio_pelo_numero(client, s, contas):
    entrar(client, "admin", "admin123")
    for i, p in enumerate(["100", "99", "000123", "2", "1000"]):
        cadastrar(client, patrimonio=p, numero_serie=f"S{i}", hostname="", ip="", mac="")
    html = client.get("/inventario/?ordenar=patrimonio").get_data(as_text=True)
    ordem = [p for p in ("<strong>2<", "<strong>99<", "<strong>100<", "<strong>000123<", "<strong>1000<")]
    posicoes = [html.index(p) for p in ordem]
    assert posicoes == sorted(posicoes)
    html = client.get("/inventario/?ordenar=patrimonio&direcao=desc").get_data(as_text=True)
    assert html.index("<strong>1000<") < html.index("<strong>2<")
