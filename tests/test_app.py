"""Testes das rotas, rodando num banco SQLite em memória.

    python -m pytest tests
"""

import io
import os
import re

import pytest
from sqlalchemy import select

from app import servicos
from app.modelos import Anexo, Chamado, Comentario, Usuario
from tests.conftest import csrf, entrar


def chamado(s, titulo) -> Chamado:
    s.expire_all()
    return s.scalar(select(Chamado).where(Chamado.titulo == titulo))


def usuario(s, login) -> Usuario:
    s.expire_all()
    return s.scalar(select(Usuario).where(Usuario.login == login))


def abrir(client, s, titulo, setor="T.I", para="carlos", **extra):
    """Abre um chamado pelo formulário e devolve a resposta."""
    dados = {"csrf": csrf(client, "/chamados/novo"), "setor_destino": setor,
             "responsavel": usuario(s, para).id if para else "",
             "titulo": titulo, "descricao": "Detalhes", "prioridade": "Baixa"}
    dados.update(extra)
    return client.post("/chamados/novo", content_type="multipart/form-data", data=dados)


def sair(client):
    client.post("/logout", data={"csrf": csrf(client, "/conta/")})


def salvar_usuario(client, s, login, setor, atende, papel="usuario"):
    u = usuario(s, login)
    dados = {"csrf": csrf(client, "/usuarios"), "setor": setor, "papel": papel}
    if atende:
        dados["atende"] = "1"
    return client.post(f"/usuarios/{u.id}", data=dados)


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
    sair(client)
    cadastrar(client, login="joao", nome="João")
    joao = usuario(s, "joao")
    assert joao.papel == "usuario" and not joao.atende   # ninguém atende sem o admin marcar


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


def test_usuario_nao_muda_o_proprio_setor(client, s, contas):
    entrar(client, "ana", "ana12345")
    client.post("/conta/", data={"csrf": csrf(client, "/conta/"), "nome": "Ana S.", "email": "",
                                 "setor": "RH"})
    ana = usuario(s, "ana")
    assert ana.nome == "Ana S." and ana.setor == "Fiscal"


# ─── administração de contas ────────────────────────────────────────────────

def test_admin_define_setor_atende_e_perfil(client, s, contas):
    entrar(client, "admin", "admin123")
    salvar_usuario(client, s, "bruno", "Manutenção", True)
    bruno = usuario(s, "bruno")
    assert bruno.setor == "Manutenção" and bruno.atende and not bruno.is_admin
    salvar_usuario(client, s, "bruno", "Manutenção", True, papel="admin")
    assert usuario(s, "bruno").is_admin


def test_admin_redefine_senha_e_usuario_troca(client, s, contas):
    entrar(client, "admin", "admin123")
    bruno = usuario(s, "bruno")
    html = client.post(f"/usuarios/{bruno.id}/senha", data={"csrf": csrf(client, "/usuarios")}).get_data(as_text=True)
    temporaria = re.search(r'class="senha-temporaria">([^<]+)<', html).group(1)
    sair(client)

    r = entrar(client, "bruno", temporaria)
    assert r.location.endswith("/conta/senha")
    assert client.get("/chamados").location.endswith("/conta/senha")
    token = csrf(client, "/conta/senha")
    client.post("/conta/senha", data={"csrf": token, "nova": "novasenha1", "confirmar": "novasenha1"})
    assert client.get("/chamados").status_code == 200
    assert not usuario(s, "bruno").trocar_senha


def test_nao_remove_ultimo_admin(s, contas):
    with pytest.raises(servicos.ErroValidacao):
        servicos.atualizar_usuario(s, usuario(s, "admin"), "T.I", True, "usuario")
    with pytest.raises(servicos.ErroValidacao):
        servicos.definir_ativo(s, usuario(s, "admin"), False)


def test_tirar_atendimento_ou_desativar_libera_chamados(s, contas):
    servicos.atualizar_usuario(s, usuario(s, "carlos"), "T.I", False, "usuario")
    assert chamado(s, "Sem acesso à pasta da rede").responsavel_id is None
    assert chamado(s, "Trocar teclado").responsavel.login == "carlos"   # fechado: histórico fica
    servicos.definir_ativo(s, usuario(s, "marta"), False)
    assert chamado(s, "Tomada queimada na recepção").responsavel_id is None


def test_permissoes_das_areas(client, contas):
    entrar(client, "ana", "ana12345")                 # usuário comum
    for url in ("/painel", "/relatorio", "/usuarios"):
        assert client.get(url).status_code == 403, url
    sair(client)
    entrar(client, "marta", "marta123")               # atende a Manutenção
    assert client.get("/painel").status_code == 200
    assert client.get("/relatorio").status_code == 200
    assert client.get("/usuarios").status_code == 403


# ─── abrir chamado: setor e funcionário ─────────────────────────────────────

def test_novo_chamado_lista_so_quem_atende(client, contas):
    entrar(client, "ana", "ana12345")
    html = client.get("/chamados/novo").get_data(as_text=True)
    assert "Carlos Técnico" in html and "Marta Manutenção" in html and "Rita Recursos Humanos" in html
    assert "Bruno Lima" not in html                   # não atende chamados
    assert '<option >Fiscal</option>' not in html      # setor sem ninguém atendendo não aparece


def test_funcionario_obrigatorio_e_do_setor_certo(client, s, contas):
    entrar(client, "ana", "ana12345")
    assert "Escolha um funcionário do setor T.I" in abrir(client, s, "Sem pessoa", para=None).get_data(as_text=True)
    r = abrir(client, s, "Pessoa errada", setor="T.I", para="marta")   # marta é da Manutenção
    assert "Escolha um funcionário do setor T.I" in r.get_data(as_text=True)
    r = abrir(client, s, "Não atende", setor="Vendas", para="bruno")   # bruno não atende
    assert "Escolha um funcionário do setor Vendas" in r.get_data(as_text=True)
    assert chamado(s, "Pessoa errada") is None


def test_abrir_chamado_para_outro_setor(client, s, contas):
    entrar(client, "ana", "ana12345")
    assert abrir(client, s, "Cadeira quebrada", setor="Manutenção", para="marta").status_code == 302
    c = chamado(s, "Cadeira quebrada")
    assert c.setor_destino == "Manutenção" and c.responsavel.login == "marta"
    assert c.setor == "Fiscal"                         # setor de quem pediu vem do cadastro


# ─── visibilidade ───────────────────────────────────────────────────────────

def test_usuario_ve_so_os_proprios(client, s, contas):
    entrar(client, "ana", "ana12345")
    html = client.get("/chamados").get_data(as_text=True)
    assert "Impressora do fiscal" in html and "Tomada queimada" in html   # dela, em setores diferentes
    assert "Trocar teclado" not in html
    assert client.get(f"/chamados/{chamado(s, 'Trocar teclado').id}").status_code == 403


def test_todos_que_atendem_o_setor_veem_o_chamado(client, s, contas):
    entrar(client, "admin", "admin123")               # admin também atende T.I
    salvar_usuario(client, s, "admin", "T.I", True, papel="admin")
    sair(client)
    entrar(client, "carlos", "carlos123")
    c = chamado(s, "Erro ao emitir nota fiscal")      # responsável é o admin
    assert client.get(f"/chamados/{c.id}").status_code == 200           # carlos, colega do setor, vê
    client.post(f"/chamados/{c.id}/assumir", data={"csrf": csrf(client, "/chamados")})
    assert chamado(s, "Erro ao emitir nota fiscal").responsavel.login == "carlos"


def test_quem_atende_ve_so_o_proprio_setor(client, s, contas):
    entrar(client, "marta", "marta123")               # Manutenção
    html = client.get("/chamados").get_data(as_text=True)
    assert "Ar-condicionado da sala" in html and "Tomada queimada" in html
    assert "Impressora do fiscal" not in html and "Dúvida sobre saldo" not in html
    c = chamado(s, "Impressora do fiscal não imprime")
    assert client.get(f"/chamados/{c.id}").status_code == 403
    r = client.post(f"/chamados/{c.id}/status", data={"csrf": csrf(client, "/chamados"), "status": "Fechado"})
    assert r.status_code == 403 and chamado(s, "Impressora do fiscal não imprime").status == "Aberto"


def test_admin_ve_todos(client, contas):
    entrar(client, "admin", "admin123")
    html = client.get("/chamados").get_data(as_text=True)
    assert "Impressora do fiscal" in html and "Tomada queimada" in html and "Dúvida sobre saldo" in html
    html = client.get("/chamados?setor=RH").get_data(as_text=True)
    assert "Dúvida sobre saldo" in html and "Impressora do fiscal" not in html


def test_quem_atende_e_pede_para_outro_setor_ve_como_solicitante(client, s, contas):
    entrar(client, "marta", "marta123")
    abrir(client, s, "Computador da manutenção travando", setor="T.I", para="carlos")
    c = chamado(s, "Computador da manutenção travando")
    assert client.get(f"/chamados/{c.id}").status_code == 200           # vê: é dela
    r = client.post(f"/chamados/{c.id}/assumir", data={"csrf": csrf(client, "/chamados")})
    assert r.status_code == 403                                         # mas não atende T.I


def test_visoes_e_busca(client, contas):
    entrar(client, "carlos", "carlos123")
    html = client.get("/chamados?visao=atribuidos&status=abertos").get_data(as_text=True)
    assert "Sem acesso à pasta" in html and "Erro ao emitir nota" not in html
    html = client.get("/chamados?visao=setor").get_data(as_text=True)
    assert "Erro ao emitir nota" in html and "Tomada queimada" not in html
    html = client.get("/chamados?visao=meus").get_data(as_text=True)
    assert "Nenhum chamado com esses filtros" in html                  # carlos não abriu nenhum
    html = client.get("/chamados?q=NOTA").get_data(as_text=True)
    assert "Erro ao emitir nota" in html and "Impressora" not in html
    html = client.get("/chamados?q=%25").get_data(as_text=True)        # "%" não casa com tudo
    assert "Nenhum chamado com esses filtros" in html
    for coluna in ("titulo", "para", "status", "abertura", "responsavel", "prioridade"):
        for direcao in ("asc", "desc"):
            assert client.get(f"/chamados?ordenar={coluna}&direcao={direcao}").status_code == 200


# ─── atendimento ────────────────────────────────────────────────────────────

def test_fluxo_completo(client, s, app, contas):
    entrar(client, "ana", "ana12345")
    r = abrir(client, s, "Mouse quebrado", anexos=(io.BytesIO(b"\x89PNG foto"), "foto.png"))
    assert r.status_code == 302
    c = chamado(s, "Mouse quebrado")
    assert c.status == "Aberto" and c.solicitante.login == "ana" and c.responsavel.login == "carlos"
    anexo = c.anexos[0]
    assert os.path.exists(os.path.join(app.config["ANEXOS_PASTA"], anexo.arquivo))
    assert client.get(f"/anexos/{anexo.id}").data == b"\x89PNG foto"

    token = csrf(client, "/chamados")
    client.post(f"/chamados/{c.id}/comentar", content_type="multipart/form-data",
                data={"csrf": token, "texto": "Urgente!", "anexos": (io.BytesIO(b"log"), "erro.log")})
    c = chamado(s, "Mouse quebrado")
    assert c.comentarios[-1].texto == "Urgente!" and c.comentarios[-1].anexos[0].nome == "erro.log"
    assert client.post(f"/chamados/{c.id}/status", data={"csrf": token, "status": "Fechado"}).status_code == 403

    # carlos atende e fecha
    sair(client)
    entrar(client, "carlos", "carlos123")
    token = csrf(client, f"/chamados/{c.id}")
    client.post(f"/chamados/{c.id}/status", data={"csrf": token, "status": "Em andamento"})
    client.post(f"/chamados/{c.id}/status", data={"csrf": token, "status": "Fechado"})
    c = chamado(s, "Mouse quebrado")
    assert c.fechado_em is not None
    assert [m.texto for m in c.comentarios if m.evento] == [
        'Status alterado de "Aberto" para "Em andamento".',
        'Status alterado de "Em andamento" para "Fechado".',
    ]

    # outro usuário não baixa o anexo nem avalia
    sair(client)
    entrar(client, "bruno", "bruno123")
    assert client.get(f"/anexos/{anexo.id}").status_code == 403
    client.post(f"/chamados/{c.id}/avaliar", data={"csrf": csrf(client, "/chamados"), "avaliacao": "Bom"})
    assert chamado(s, "Mouse quebrado").avaliacao is None

    # a dona avalia
    sair(client)
    entrar(client, "ana", "ana12345")
    client.post(f"/chamados/{c.id}/avaliar", data={"csrf": csrf(client, "/avaliacoes"), "avaliacao": "Bom"})
    assert chamado(s, "Mouse quebrado").avaliacao == "Bom"


def test_encaminhar_para_outro_setor(client, s, contas):
    entrar(client, "carlos", "carlos123")
    c = chamado(s, "Sem acesso à pasta da rede")                  # T.I, com carlos
    r = client.post(f"/chamados/{c.id}/encaminhar",
                    data={"csrf": csrf(client, "/chamados"), "setor_destino": "Manutenção",
                          "responsavel": usuario(s, "marta").id})
    assert r.location.endswith("/chamados")                      # carlos não atende Manutenção: volta à lista
    c = chamado(s, "Sem acesso à pasta da rede")
    assert c.setor_destino == "Manutenção" and c.responsavel.login == "marta"
    assert "Encaminhado de T.I para Manutenção (Marta Manutenção)." in [m.texto for m in c.comentarios]
    assert client.get(f"/chamados/{c.id}").status_code == 403    # e deixa de ver
    sair(client)
    entrar(client, "marta", "marta123")
    assert client.get(f"/chamados/{c.id}").status_code == 200


def test_encaminhar_exige_funcionario_do_setor(client, s, contas):
    entrar(client, "carlos", "carlos123")
    c = chamado(s, "Impressora do fiscal não imprime")
    for setor, pessoa in (("Manutenção", "carlos"), ("T.I", "bruno"), ("T.I", "marta")):
        html = client.post(f"/chamados/{c.id}/encaminhar", follow_redirects=True,
                           data={"csrf": csrf(client, "/chamados"), "setor_destino": setor,
                                 "responsavel": usuario(s, pessoa).id}).get_data(as_text=True)
        assert f"Escolha um funcionário do setor {setor}" in html
    c = chamado(s, "Impressora do fiscal não imprime")
    assert c.setor_destino == "T.I" and c.responsavel.login == "carlos"


def test_reabrir_limpa_fechamento_e_avaliacao(client, s, contas):
    entrar(client, "carlos", "carlos123")
    c = chamado(s, "E-mail não sincroniza no celular")
    assert c.avaliacao == "Bom"
    client.post(f"/chamados/{c.id}/status", data={"csrf": csrf(client, "/chamados"), "status": "Em andamento"})
    c = chamado(s, "E-mail não sincroniza no celular")
    assert c.fechado_em is None and c.avaliacao is None


def test_so_admin_apaga(client, s, app, contas):
    entrar(client, "ana", "ana12345")
    abrir(client, s, "Apagar-me", anexos=(io.BytesIO(b"abc"), "a.txt"))
    c = chamado(s, "Apagar-me")
    arquivo = os.path.join(app.config["ANEXOS_PASTA"], c.anexos[0].arquivo)
    cid = c.id
    sair(client)

    entrar(client, "carlos", "carlos123")                      # atende o setor: não apaga
    assert client.post(f"/chamados/{cid}/apagar", data={"csrf": csrf(client, "/chamados")}).status_code == 403
    sair(client)

    entrar(client, "admin", "admin123")
    client.post(f"/chamados/{cid}/apagar", data={"csrf": csrf(client, "/chamados")})
    s.expire_all()
    assert s.get(Chamado, cid) is None
    assert not s.scalars(select(Comentario).where(Comentario.chamado_id == cid)).all()
    assert not s.scalars(select(Anexo).where(Anexo.chamado_id == cid)).all()
    assert not os.path.exists(arquivo)


# ─── painel e relatório ─────────────────────────────────────────────────────

def test_painel_relatorio_por_setor(client, s, contas):
    entrar(client, "marta", "marta123")
    assert client.get("/painel").status_code == 200
    r = client.get("/relatorio/excel?de=2000-01-01&ate=2100-01-01&setor=T.I")   # setor ignorado: não é admin
    assert r.status_code == 200 and r.data[:2] == b"PK"
    from openpyxl import load_workbook
    ws = load_workbook(io.BytesIO(r.data)).active
    assert {row[2] for row in ws.iter_rows(min_row=2, values_only=True)} == {"Manutenção"}

    sair(client)
    entrar(client, "admin", "admin123")
    for url in ("/painel", "/painel?dias=365", "/painel?setor=T.I", "/usuarios", "/relatorio", "/conta/"):
        assert client.get(url).status_code == 200, url
    r = client.get("/relatorio/pdf?de=2000-01-01&ate=2100-01-01")
    assert r.status_code == 200 and r.data[:4] == b"%PDF"
    assert client.get("/relatorio/pdf?de=2100-01-01&ate=2000-01-01").status_code == 302


# ─── anexos e segurança ─────────────────────────────────────────────────────

def test_anexo_proibido_ou_grande(client, s, contas):
    entrar(client, "ana", "ana12345")
    r = abrir(client, s, "X", anexos=(io.BytesIO(b"MZ"), "virus.exe"))
    assert "não permitido" in r.get_data(as_text=True)
    r = abrir(client, s, "X", anexos=(io.BytesIO(b"0" * (1024 * 1024 + 1)), "grande.txt"))
    assert "limite" in r.get_data(as_text=True)


def test_anexo_nao_exibivel_sempre_baixado(client, s, contas):
    entrar(client, "ana", "ana12345")
    abrir(client, s, "Com xml", anexos=(io.BytesIO(b"<script>alert(1)</script>"), "dados.xml", "text/html"))
    a = chamado(s, "Com xml").anexos[0]
    r = client.get(f"/anexos/{a.id}")
    assert r.headers["Content-Disposition"].startswith("attachment")
    assert r.mimetype == "application/octet-stream"


def test_cabecalhos_seguranca(client):
    r = client.get("/login")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"
