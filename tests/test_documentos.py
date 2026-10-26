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


def test_so_admin_cadastra_e_supervisor_consulta(client, s, app, contas):
    from app import servicos
    from tests.test_app import usuario
    servicos.atualizar_usuario(s, usuario(s, "ana"), "Fiscal", False, "supervisor")
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


def test_categoria_contratos(client, s, contas):
    entrar(client, "admin", "admin123")
    assert ">Contratos</option>" in client.get("/documentos/novo").get_data(as_text=True)
    enviar(client, titulo="Contrato de manutenção do ar-condicionado", categoria="Contratos",
           arquivo=("contrato.pdf", b"%PDF-1.4 contrato"))
    assert doc(s, "Contrato de manutenção do ar-condicionado").categoria == "Contratos"
    html = client.get("/documentos/?categoria=Contratos").get_data(as_text=True)
    assert "Contrato de manutenção do ar-condicionado" in html



def test_vencimento_dos_contratos(client, s, contas):
    from datetime import date, timedelta
    entrar(client, "admin", "admin123")
    html = client.get("/documentos/novo").get_data(as_text=True)
    assert 'name="vencimento"' in html and "data-so-contratos" in html
    hoje = date.today()
    enviar(client, titulo="Contrato do link de internet", categoria="Contratos",
           vencimento=(hoje + timedelta(days=10)).isoformat())
    enviar(client, titulo="Contrato antigo", categoria="Contratos", vencimento=(hoje - timedelta(days=1)).isoformat())
    enviar(client, titulo="Contrato longo", categoria="Contratos", vencimento=(hoje + timedelta(days=400)).isoformat())
    enviar(client, titulo="Termo com data", categoria="Termos", vencimento=hoje.isoformat())   # ignorada fora de contratos
    assert doc(s, "Contrato do link de internet").situacao_vencimento == "vence"
    assert doc(s, "Contrato antigo").situacao_vencimento == "vencido"
    assert doc(s, "Contrato longo").situacao_vencimento == "vigente"
    assert doc(s, "Termo com data").vencimento is None
    html = client.get("/documentos/?categoria=Contratos").get_data(as_text=True)
    assert "(10 dias)" in html and "Vencido em" in html
    d = doc(s, "Contrato do link de internet")
    assert f'value="{(hoje + timedelta(days=10)).isoformat()}"' in client.get(f"/documentos/{d.id}/editar").get_data(as_text=True)
    assert "Data de vencimento inválida" in enviar(client, titulo="X", categoria="Contratos",
                                                   vencimento="31/02/2026").get_data(as_text=True)



def test_aviso_semanal_de_contratos(client, s, app, contas):
    from datetime import date, timedelta
    from app import documentos, notificacoes
    entrar(client, "admin", "admin123")
    hoje = date.today()
    for titulo, dias in (("Contrato vencendo", 10), ("Contrato vencido", -5), ("Contrato longo", 200),
                         ("Contrato vencido há muito", -90)):
        enviar(client, titulo=titulo, categoria="Contratos", vencimento=(hoje + timedelta(days=dias)).isoformat())
    lista = documentos.contratos_a_vencer(s)
    assert [d.titulo for d in lista] == ["Contrato vencido", "Contrato vencendo"]
    app.extensions["email"].avisos_cpd = "cpd@empresa.com.br"
    with app.test_request_context():
        msg = notificacoes.mensagem_semanal([], lista)
        assert notificacoes.mensagem_semanal([], []) is None
    assert msg.para == "cpd@empresa.com.br"
    assert "1 contrato vencendo" in msg.assunto and "1 contrato vencido" in msg.assunto
    assert "Contrato vencendo" in msg.texto and "Contrato longo" not in msg.texto
    assert "categoria=Contratos" in msg.texto and "Preventivas" not in msg.texto
