"""Testes das rotas, rodando num banco SQLite em memória.

    python -m pytest tests
"""

import io
import os

from sqlalchemy import select

from app.modelos import Anexo, Chamado, Comentario, Usuario
from tests.conftest import csrf, entrar


def chamado(s, titulo) -> Chamado:
    s.expire_all()
    return s.scalar(select(Chamado).where(Chamado.titulo == titulo))


def usuario(s, login) -> Usuario:
    s.expire_all()
    return s.scalar(select(Usuario).where(Usuario.login == login))


# ─── cadastro e login ───────────────────────────────────────────────────────

def cadastrar(client, **campos):
    dados = {"nome": "Maria Teste", "login": "maria", "email": "", "setor": "RH",
             "senha": "senha123", "confirmar": "senha123"}
    dados.update(campos)
    return client.post("/cadastro", data=dict(dados, csrf=csrf(client, "/cadastro")))


def test_primeira_conta_vira_admin_e_as_outras_usuario(client, s):
    r = cadastrar(client)
    assert r.status_code == 302
    assert usuario(s, "maria").is_admin
    client.post("/logout", data={"csrf": csrf(client, "/chamados")})
    cadastrar(client, login="joao", nome="João")
    assert usuario(s, "joao").papel == "usuario"


def test_cadastro_valida(client, contas):
    assert "já está em uso" in cadastrar(client, login="ana").get_data(as_text=True)
    assert "não conferem" in cadastrar(client, confirmar="outra123").get_data(as_text=True)
    assert "8 caracteres" in cadastrar(client, senha="abc1", confirmar="abc1").get_data(as_text=True)
    assert "letras e números" in cadastrar(client, senha="somenteletras", confirmar="somenteletras").get_data(as_text=True)
    assert "Usuário: de 3 a 50" in cadastrar(client, login="a b").get_data(as_text=True)


def test_login_normaliza_maiusculas_e_senha_fica_em_hash(client, s, contas):
    assert usuario(s, "ana").senha_hash != "ana12345"
    r = entrar(client, "ANA", "ana12345")
    assert r.status_code == 302


def test_exige_login(client):
    r = client.get("/chamados")
    assert r.status_code == 302 and "/login" in r.location


def test_login_invalido_e_bloqueio(client, contas):
    assert "inválidos" in entrar(client, "ana", "errada").get_data(as_text=True)
    for _ in range(4):
        entrar(client, "ana", "errada")
    assert "Muitas tentativas" in entrar(client, "ana", "ana12345").get_data(as_text=True)


def test_sem_csrf_recusado(client, contas):
    assert client.post("/login", data={"login": "ana", "senha": "ana12345"}).status_code == 400


def test_redirect_externo_bloqueado(client, contas):
    r = client.post("/login", data={"login": "admin", "senha": "admin123", "csrf": csrf(client),
                                    "proximo": "//site-malicioso.com"})
    assert r.location.endswith("/chamados")


def test_conta_desativada_perde_acesso_na_hora(client, s, contas):
    entrar(client, "ana", "ana12345")
    assert client.get("/chamados").status_code == 200
    u = usuario(s, "ana")
    u.ativo = False
    s.commit()
    assert client.get("/chamados").status_code == 302


# ─── administração de contas ────────────────────────────────────────────────

def test_admin_promove_redefine_e_usuario_troca_senha(client, s, contas):
    entrar(client, "admin", "admin123")
    token = csrf(client, "/usuarios")
    bruno = usuario(s, "bruno")
    client.post(f"/usuarios/{bruno.id}/papel", data={"csrf": token, "papel": "tecnico"})
    assert usuario(s, "bruno").is_tecnico

    html = client.post(f"/usuarios/{bruno.id}/senha", data={"csrf": token}).get_data(as_text=True)
    import re
    temporaria = re.search(r'class="senha-temporaria">([^<]+)<', html).group(1)
    client.post("/logout", data={"csrf": token})

    # entra com a temporária e é obrigado a trocar
    r = entrar(client, "bruno", temporaria)
    assert r.location.endswith("/conta/senha")
    assert client.get("/chamados").location.endswith("/conta/senha")
    token = csrf(client, "/conta/senha")
    client.post("/conta/senha", data={"csrf": token, "nova": "novasenha1", "confirmar": "novasenha1"})
    assert client.get("/chamados").status_code == 200
    assert not usuario(s, "bruno").trocar_senha


def test_nao_remove_ultimo_admin(client, s, contas):
    entrar(client, "admin", "admin123")
    carlos = usuario(s, "carlos")
    token = csrf(client, "/usuarios")
    client.post(f"/usuarios/{carlos.id}/papel", data={"csrf": token, "papel": "admin"})
    client.post("/logout", data={"csrf": token})
    entrar(client, "carlos", "carlos123")
    token = csrf(client, "/usuarios")
    admin = usuario(s, "admin")
    client.post(f"/usuarios/{admin.id}/ativo", data={"csrf": token, "ativo": "0"})
    assert not usuario(s, "admin").ativo
    # carlos agora é o único admin ativo e não pode ser rebaixado
    from app import servicos
    import pytest
    with pytest.raises(servicos.ErroValidacao):
        servicos.definir_papel(s, usuario(s, "carlos"), "usuario")


def test_usuario_nao_acessa_area_restrita(client, contas):
    entrar(client, "ana", "ana12345")
    for url in ("/painel", "/usuarios", "/relatorio"):
        assert client.get(url).status_code == 403


def test_tecnico_ve_painel_mas_nao_usuarios(client, contas):
    entrar(client, "carlos", "carlos123")
    assert client.get("/painel").status_code == 200
    assert client.get("/usuarios").status_code == 403


# ─── chamados ───────────────────────────────────────────────────────────────

def test_usuario_ve_so_os_proprios(client, s, contas):
    entrar(client, "ana", "ana12345")
    html = client.get("/chamados").get_data(as_text=True)
    assert "Impressora do fiscal" in html and "Trocar teclado" not in html
    assert client.get(f"/chamados/{chamado(s, 'Trocar teclado').id}").status_code == 403


def test_tecnico_ve_todos_filtra_e_ordena(client, contas):
    entrar(client, "carlos", "carlos123")
    html = client.get("/chamados").get_data(as_text=True)
    assert "Trocar teclado" in html and "Impressora do fiscal" in html
    html = client.get("/chamados?status=abertos&setor=Fiscal").get_data(as_text=True)
    assert "Impressora do fiscal" in html and "Trocar teclado" not in html
    html = client.get("/chamados?q=NOTA").get_data(as_text=True)
    assert "Erro ao emitir nota" in html and "Impressora" not in html
    html = client.get("/chamados?responsavel=eu").get_data(as_text=True)
    assert "Sem acesso à pasta" in html and "Erro ao emitir nota" not in html
    html = client.get("/chamados?responsavel=nenhum").get_data(as_text=True)
    assert "Impressora do fiscal" in html and "Sem acesso à pasta" not in html
    for coluna in ("titulo", "prioridade", "responsavel", "solicitante", "fechamento"):
        for direcao in ("asc", "desc"):
            assert client.get(f"/chamados?ordenar={coluna}&direcao={direcao}").status_code == 200


def test_busca_escapa_curinga(client, contas):
    entrar(client, "carlos", "carlos123")
    html = client.get("/chamados?q=%25").get_data(as_text=True)  # "%" não pode casar com tudo
    assert "Nenhum chamado com esses filtros" in html


def test_fluxo_completo(client, s, app, contas):
    entrar(client, "ana", "ana12345")
    token = csrf(client, "/chamados/novo")
    r = client.post("/chamados/novo", content_type="multipart/form-data", data={
        "csrf": token, "titulo": "Mouse quebrado", "descricao": "Não clica",
        "prioridade": "Baixa", "setor": "T.I",
        "anexos": (io.BytesIO(b"\x89PNG foto"), "foto.png"),
    })
    assert r.status_code == 302
    c = chamado(s, "Mouse quebrado")
    assert c.status == "Aberto" and c.solicitante.login == "ana"
    anexo = c.anexos[0]
    assert os.path.exists(os.path.join(app.config["ANEXOS_PASTA"], anexo.arquivo))
    assert client.get(f"/anexos/{anexo.id}").data == b"\x89PNG foto"

    client.post(f"/chamados/{c.id}/comentar", content_type="multipart/form-data",
                data={"csrf": token, "texto": "Urgente!", "anexos": (io.BytesIO(b"log"), "erro.log")})
    c = chamado(s, "Mouse quebrado")
    assert c.comentarios[-1].texto == "Urgente!" and c.comentarios[-1].anexos[0].nome == "erro.log"

    # usuário não muda status
    assert client.post(f"/chamados/{c.id}/status", data={"csrf": token, "status": "Fechado"}).status_code == 403

    # técnico assume e fecha
    client.post("/logout", data={"csrf": token})
    entrar(client, "carlos", "carlos123")
    token = csrf(client, f"/chamados/{c.id}")
    client.post(f"/chamados/{c.id}/assumir", data={"csrf": token})
    c = chamado(s, "Mouse quebrado")
    assert c.responsavel.login == "carlos" and c.status == "Em andamento"
    client.post(f"/chamados/{c.id}/status", data={"csrf": token, "status": "Fechado"})
    c = chamado(s, "Mouse quebrado")
    assert c.fechado_em is not None
    assert [m.texto for m in c.comentarios if m.evento] == [
        "Chamado atribuído a Carlos Técnico.",
        'Status alterado de "Aberto" para "Em andamento".',
        'Status alterado de "Em andamento" para "Fechado".',
    ]

    # outro usuário não baixa o anexo nem avalia
    client.post("/logout", data={"csrf": token})
    entrar(client, "bruno", "bruno123")
    assert client.get(f"/anexos/{anexo.id}").status_code == 403
    token = csrf(client, "/chamados")
    client.post(f"/chamados/{c.id}/avaliar", data={"csrf": token, "avaliacao": "Bom"})
    assert chamado(s, "Mouse quebrado").avaliacao is None

    # a dona é levada às avaliações ao entrar, e avalia
    client.post("/logout", data={"csrf": token})
    assert entrar(client, "ana", "ana12345").location.endswith("/avaliacoes")
    token = csrf(client, "/avaliacoes")
    client.post(f"/chamados/{c.id}/avaliar", data={"csrf": token, "avaliacao": "Bom"})
    assert chamado(s, "Mouse quebrado").avaliacao == "Bom"


def test_reabrir_limpa_fechamento_e_avaliacao(client, s, contas):
    entrar(client, "carlos", "carlos123")
    c = chamado(s, "E-mail não sincroniza no celular")
    assert c.avaliacao == "Bom"
    client.post(f"/chamados/{c.id}/status", data={"csrf": csrf(client, "/chamados"), "status": "Em andamento"})
    c = chamado(s, "E-mail não sincroniza no celular")
    assert c.fechado_em is None and c.avaliacao is None


def test_atribuir_so_para_tecnico(client, s, contas):
    entrar(client, "carlos", "carlos123")
    c = chamado(s, "Impressora do fiscal não imprime")
    bruno = usuario(s, "bruno")
    html = client.post(f"/chamados/{c.id}/responsavel", follow_redirects=True,
                       data={"csrf": csrf(client, "/chamados"), "responsavel": bruno.id}).get_data(as_text=True)
    assert "Escolha um técnico ativo" in html
    assert chamado(s, "Impressora do fiscal não imprime").responsavel_id is None


def test_apagar_remove_comentarios_anexos_e_arquivos(client, s, app, contas):
    entrar(client, "ana", "ana12345")
    token = csrf(client, "/chamados/novo")
    client.post("/chamados/novo", content_type="multipart/form-data", data={
        "csrf": token, "titulo": "Apagar-me", "descricao": "x", "prioridade": "Baixa", "setor": "RH",
        "anexos": (io.BytesIO(b"abc"), "a.txt")})
    c = chamado(s, "Apagar-me")
    arquivo = os.path.join(app.config["ANEXOS_PASTA"], c.anexos[0].arquivo)
    cid = c.id
    client.post("/logout", data={"csrf": token})
    entrar(client, "admin", "admin123")
    client.post(f"/chamados/{cid}/apagar", data={"csrf": csrf(client, "/chamados")})
    s.expire_all()
    assert s.get(Chamado, cid) is None
    assert not s.scalars(select(Comentario).where(Comentario.chamado_id == cid)).all()
    assert not s.scalars(select(Anexo).where(Anexo.chamado_id == cid)).all()
    assert not os.path.exists(arquivo)


def test_anexo_proibido_ou_grande(client, contas):
    entrar(client, "ana", "ana12345")
    base = {"csrf": csrf(client, "/chamados/novo"), "titulo": "X", "descricao": "Y",
            "prioridade": "Baixa", "setor": "RH"}
    r = client.post("/chamados/novo", content_type="multipart/form-data",
                    data=dict(base, anexos=(io.BytesIO(b"MZ"), "virus.exe")))
    assert "não permitido" in r.get_data(as_text=True)
    r = client.post("/chamados/novo", content_type="multipart/form-data",
                    data=dict(base, anexos=(io.BytesIO(b"0" * (1024 * 1024 + 1)), "grande.txt")))
    assert "limite" in r.get_data(as_text=True)


def test_anexo_nao_exibivel_sempre_baixado(client, s, contas):
    entrar(client, "ana", "ana12345")
    token = csrf(client, "/chamados/novo")
    client.post("/chamados/novo", content_type="multipart/form-data", data={
        "csrf": token, "titulo": "Com xml", "descricao": "x", "prioridade": "Baixa", "setor": "RH",
        "anexos": (io.BytesIO(b"<script>alert(1)</script>"), "dados.xml", "text/html")})
    a = chamado(s, "Com xml").anexos[0]
    r = client.get(f"/anexos/{a.id}")
    assert r.headers["Content-Disposition"].startswith("attachment")
    assert r.mimetype == "application/octet-stream"


def test_painel_relatorio_e_conta(client, contas):
    entrar(client, "admin", "admin123")
    for url in ("/painel", "/painel?dias=365", "/usuarios", "/relatorio", "/conta/"):
        assert client.get(url).status_code == 200, url
    r = client.get("/relatorio/excel?de=2000-01-01&ate=2100-01-01")
    assert r.status_code == 200 and r.data[:2] == b"PK"
    r = client.get("/relatorio/pdf?de=2000-01-01&ate=2100-01-01")
    assert r.status_code == 200 and r.data[:4] == b"%PDF"
    assert client.get("/relatorio/pdf?de=2100-01-01&ate=2000-01-01").status_code == 302


def test_cabecalhos_seguranca(client):
    r = client.get("/login")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"
