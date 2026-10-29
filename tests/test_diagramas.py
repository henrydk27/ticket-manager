"""Testes da tela de diagramas da infraestrutura."""

import io
import os

from sqlalchemy import select

from app.modelos import Diagrama
from tests.conftest import csrf, entrar
from tests.test_app import sair

SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
       b'<rect width="200" height="100" fill="#eee"/></svg>')


def diagrama(s, titulo):
    s.expire_all()
    return s.scalar(select(Diagrama).where(Diagrama.titulo == titulo))


def enviar(client, url="/diagramas/novo", imagem=("mapa.svg", SVG), editavel=("mapa.drawio", b"<mxfile/>"), **campos):
    dados = {"csrf": csrf(client, url), "titulo": "Mapa da rede", "descricao": "Topologia", "ordem": "1"}
    dados.update(campos)
    if imagem:
        dados["imagem"] = (io.BytesIO(imagem[1]), imagem[0])
    if editavel:
        dados["editavel"] = (io.BytesIO(editavel[1]), editavel[0])
    return client.post(url, data=dados, content_type="multipart/form-data", follow_redirects=True)


def test_quem_ve_e_quem_cadastra(client, s, contas):
    for login, senha, ver, cadastrar in (("ana", "ana12345", 403, 403), ("marta", "marta123", 403, 403),
                                         ("carlos", "carlos123", 200, 403), ("admin", "admin123", 200, 200)):
        entrar(client, login, senha)
        assert client.get("/diagramas/").status_code == ver, login
        assert client.get("/diagramas/novo").status_code == cadastrar, login
        assert (">Diagramas<" in client.get("/chamados").get_data(as_text=True)) == (ver == 200), login
        sair(client)


def test_cadastrar_ver_trocar_e_apagar(client, s, app, contas):
    entrar(client, "admin", "admin123")
    html = enviar(client).get_data(as_text=True)
    assert "cadastrado" in html and "data-visualizador" in html and "Baixar editável (.drawio)" in html
    d = diagrama(s, "Mapa da rede")
    pasta = app.config["ANEXOS_PASTA"]
    assert os.path.exists(os.path.join(pasta, d.arquivo)) and os.path.exists(os.path.join(pasta, d.editavel_arquivo))

    with client.get(f"/diagramas/{d.id}/imagem") as r:
        assert r.mimetype == "image/svg+xml" and r.data == SVG
        assert "sandbox" in r.headers["Content-Security-Policy"]  # SVG enviado não roda script
    with client.get(f"/diagramas/{d.id}/editavel") as r:
        assert r.data == b"<mxfile/>"
    sair(client)

    entrar(client, "carlos", "carlos123")                       # atende a T.I: vê
    assert "Mapa da rede" in client.get("/diagramas/").get_data(as_text=True)
    assert client.get(f"/diagramas/{d.id}").status_code == 200
    assert "Editar</a>" not in client.get(f"/diagramas/{d.id}").get_data(as_text=True)
    sair(client)

    entrar(client, "admin", "admin123")
    antiga = d.arquivo
    enviar(client, f"/diagramas/{d.id}/editar", imagem=("novo.png", b"\x89PNG"), editavel=None,
           titulo="Mapa da rede 2026", remover_editavel="1")
    d = diagrama(s, "Mapa da rede 2026")
    assert d.nome == "novo.png" and d.editavel_arquivo is None and not os.path.exists(os.path.join(pasta, antiga))

    assert "precisa ser SVG" in enviar(client, imagem=("mapa.pdf", b"%PDF")).get_data(as_text=True)
    assert "Escolha a imagem" in enviar(client, imagem=None).get_data(as_text=True)

    client.post(f"/diagramas/{d.id}/apagar", data={"csrf": csrf(client, "/diagramas/")})
    assert s.scalar(select(Diagrama.id)) is None and os.listdir(pasta) == []


def test_drawio_svg_e_editavel_embutido(client, s, contas):
    entrar(client, "admin", "admin123")
    enviar(client, imagem=("Mapa da rede.drawio.svg", SVG), editavel=None)
    d = diagrama(s, "Mapa da rede")
    html = client.get(f"/diagramas/{d.id}").get_data(as_text=True)
    assert "Baixar editável" in html and "este arquivo abre e edita direto no draw.io".lower() in html.lower()
