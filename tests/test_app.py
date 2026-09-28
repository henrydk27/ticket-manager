"""Testes das rotas, rodando num banco SQLite em memória.

    python -m pytest tests
"""

import io
import os
import re

import pytest
from sqlalchemy import select

from app import servicos
from app.modelos import Anexo, Categoria, Chamado, Comentario, Fila, Usuario
from tests.conftest import csrf, entrar


def chamado(s, titulo) -> Chamado:
    s.expire_all()
    return s.scalar(select(Chamado).where(Chamado.titulo == titulo))


def usuario(s, login) -> Usuario:
    s.expire_all()
    return s.scalar(select(Usuario).where(Usuario.login == login))


def fila(s, nome) -> Fila:
    s.expire_all()
    return s.scalar(select(Fila).where(Fila.nome == nome))


def tipo(s, fila_nome, nome) -> Categoria:
    return next(c for c in fila(s, fila_nome).categorias if c.nome == nome)


def abrir(client, s, titulo, fila_nome="T.I", tipo_nome="Computador", **extra):
    """Abre um chamado pelo formulário e devolve a resposta."""
    f = fila(s, fila_nome)
    dados = {"csrf": csrf(client, "/chamados/novo"), "fila": f.id,
             "categoria": tipo(s, fila_nome, tipo_nome).id if tipo_nome else "",
             "titulo": titulo, "descricao": "Detalhes", "prioridade": "Baixa", "setor": "RH"}
    dados.update(extra)
    return client.post("/chamados/novo", content_type="multipart/form-data", data=dados)


def sair(client):
    client.post("/logout", data={"csrf": csrf(client, "/conta/")})


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
    client.post(f"/usuarios/{bruno.id}/papel", data={"csrf": token, "papel": "admin"})
    assert usuario(s, "bruno").is_admin

    html = client.post(f"/usuarios/{bruno.id}/senha", data={"csrf": token}).get_data(as_text=True)
    temporaria = re.search(r'class="senha-temporaria">([^<]+)<', html).group(1)
    sair(client)

    # entra com a temporária e é obrigado a trocar
    r = entrar(client, "bruno", temporaria)
    assert r.location.endswith("/conta/senha")
    assert client.get("/chamados").location.endswith("/conta/senha")
    token = csrf(client, "/conta/senha")
    client.post("/conta/senha", data={"csrf": token, "nova": "novasenha1", "confirmar": "novasenha1"})
    assert client.get("/chamados").status_code == 200
    assert not usuario(s, "bruno").trocar_senha


def test_nao_remove_ultimo_admin(s, contas):
    with pytest.raises(servicos.ErroValidacao):
        servicos.definir_papel(s, usuario(s, "admin"), "usuario")
    with pytest.raises(servicos.ErroValidacao):
        servicos.definir_ativo(s, usuario(s, "admin"), False)


def test_desativar_conta_tira_responsabilidade(s, contas):
    servicos.definir_ativo(s, usuario(s, "carlos"), False)
    assert chamado(s, "Sem acesso à pasta da rede").responsavel_id is None


def test_permissoes_das_areas(client, contas):
    entrar(client, "ana", "ana12345")                 # usuário comum
    for url in ("/painel", "/relatorio", "/usuarios", "/filas"):
        assert client.get(url).status_code == 403, url
    sair(client)
    entrar(client, "marta", "marta123")               # atendente
    assert client.get("/painel").status_code == 200
    assert client.get("/relatorio").status_code == 200
    assert client.get("/usuarios").status_code == 403
    assert client.get("/filas").status_code == 403


# ─── filas: visibilidade ────────────────────────────────────────────────────

def test_usuario_ve_so_os_proprios(client, s, contas):
    entrar(client, "ana", "ana12345")
    html = client.get("/chamados").get_data(as_text=True)
    assert "Impressora do fiscal" in html and "Tomada queimada" in html   # dela, em filas diferentes
    assert "Trocar teclado" not in html
    assert client.get(f"/chamados/{chamado(s, 'Trocar teclado').id}").status_code == 403


def test_atendente_ve_so_as_proprias_filas(client, s, contas):
    entrar(client, "marta", "marta123")               # Manutenção
    html = client.get("/chamados").get_data(as_text=True)
    assert "Ar-condicionado da sala" in html and "Tomada queimada" in html
    assert "Impressora do fiscal" not in html and "Dúvida sobre saldo" not in html
    c = chamado(s, "Impressora do fiscal não imprime")
    assert client.get(f"/chamados/{c.id}").status_code == 403
    # não mexe em chamado de outra fila nem pelo endereço direto
    r = client.post(f"/chamados/{c.id}/status", data={"csrf": csrf(client, "/chamados"), "status": "Fechado"})
    assert r.status_code == 403 and chamado(s, "Impressora do fiscal não imprime").status == "Aberto"


def test_admin_ve_todas_as_filas(client, contas):
    entrar(client, "admin", "admin123")
    html = client.get("/chamados").get_data(as_text=True)
    assert "Impressora do fiscal" in html and "Tomada queimada" in html and "Dúvida sobre saldo" in html


def test_atendente_que_abre_pedido_em_outra_fila_ve_como_solicitante(client, s, contas):
    entrar(client, "marta", "marta123")
    abrir(client, s, "Computador da manutenção travando")
    c = chamado(s, "Computador da manutenção travando")
    assert client.get(f"/chamados/{c.id}").status_code == 200           # vê: é dela
    r = client.post(f"/chamados/{c.id}/assumir", data={"csrf": csrf(client, "/chamados")})
    assert r.status_code == 403                                         # mas não atende T.I


def test_abas_e_filtros(client, contas):
    entrar(client, "carlos", "carlos123")
    html = client.get("/chamados?status=abertos&responsavel=eu").get_data(as_text=True)
    assert "Sem acesso à pasta" in html and "Erro ao emitir nota" not in html
    html = client.get("/chamados?visao=filas&status=abertos&responsavel=nenhum").get_data(as_text=True)
    assert "Impressora do fiscal" in html and "Sem acesso à pasta" not in html
    html = client.get("/chamados?q=NOTA").get_data(as_text=True)
    assert "Erro ao emitir nota" in html and "Impressora" not in html
    html = client.get("/chamados?visao=meus").get_data(as_text=True)
    assert "Nenhum chamado com esses filtros" in html                  # carlos não abriu nenhum
    for coluna in ("titulo", "fila", "prioridade", "responsavel", "solicitante", "fechamento"):
        for direcao in ("asc", "desc"):
            assert client.get(f"/chamados?ordenar={coluna}&direcao={direcao}").status_code == 200


def test_busca_escapa_curinga(client, contas):
    entrar(client, "carlos", "carlos123")
    html = client.get("/chamados?q=%25").get_data(as_text=True)  # "%" não pode casar com tudo
    assert "Nenhum chamado com esses filtros" in html


# ─── filas: abrir, atender, transferir ──────────────────────────────────────

def test_tipo_obrigatorio_e_da_fila_certa(client, s, contas):
    entrar(client, "ana", "ana12345")
    assert "Escolha o tipo de pedido" in abrir(client, s, "Sem tipo", tipo_nome=None).get_data(as_text=True)
    outra = tipo(s, "Manutenção", "Elétrica").id
    assert "inválido" in abrir(client, s, "Tipo errado", categoria=outra).get_data(as_text=True)
    # fila sem tipos cadastrados não exige tipo
    assert abrir(client, s, "Pedido ao RH", fila_nome="RH", tipo_nome=None).status_code == 302
    assert chamado(s, "Pedido ao RH").fila.nome == "RH"


def test_fila_desativada_nao_recebe_pedidos(client, s, contas):
    f = fila(s, "RH")
    f.ativa = False
    s.commit()
    entrar(client, "ana", "ana12345")
    html = client.get("/chamados/novo").get_data(as_text=True)
    assert 'opcao-fila-nome">RH<' not in html and 'opcao-fila-nome">T.I<' in html
    r = abrir(client, s, "X", fila_nome="RH", tipo_nome=None)
    assert "Escolha para qual setor" in r.get_data(as_text=True)


def test_fluxo_completo(client, s, app, contas):
    entrar(client, "ana", "ana12345")
    r = abrir(client, s, "Mouse quebrado", anexos=(io.BytesIO(b"\x89PNG foto"), "foto.png"))
    assert r.status_code == 302
    c = chamado(s, "Mouse quebrado")
    assert c.status == "Aberto" and c.solicitante.login == "ana" and c.categoria.nome == "Computador"
    anexo = c.anexos[0]
    assert os.path.exists(os.path.join(app.config["ANEXOS_PASTA"], anexo.arquivo))
    assert client.get(f"/anexos/{anexo.id}").data == b"\x89PNG foto"

    token = csrf(client, "/chamados")
    client.post(f"/chamados/{c.id}/comentar", content_type="multipart/form-data",
                data={"csrf": token, "texto": "Urgente!", "anexos": (io.BytesIO(b"log"), "erro.log")})
    c = chamado(s, "Mouse quebrado")
    assert c.comentarios[-1].texto == "Urgente!" and c.comentarios[-1].anexos[0].nome == "erro.log"
    assert client.post(f"/chamados/{c.id}/status", data={"csrf": token, "status": "Fechado"}).status_code == 403

    # atendente da T.I assume e fecha
    sair(client)
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


def test_transferir_entre_filas(client, s, contas):
    entrar(client, "carlos", "carlos123")
    c = chamado(s, "Sem acesso à pasta da rede")                  # T.I, responsável carlos
    manut = fila(s, "Manutenção")
    r = client.post(f"/chamados/{c.id}/transferir",
                    data={"csrf": csrf(client, "/chamados"), "fila": manut.id,
                          "categoria": tipo(s, "Manutenção", "Elétrica").id})
    assert r.location.endswith("/chamados")                      # carlos não atende Manutenção: volta à lista
    c = chamado(s, "Sem acesso à pasta da rede")
    assert c.fila.nome == "Manutenção" and c.categoria.nome == "Elétrica"
    assert c.responsavel_id is None                             # carlos não é da Manutenção
    assert "Transferido de T.I para Manutenção / Elétrica." in [m.texto for m in c.comentarios]
    assert client.get(f"/chamados/{c.id}").status_code == 403    # e deixa de ver

    sair(client)
    entrar(client, "marta", "marta123")
    assert client.get(f"/chamados/{c.id}").status_code == 200    # agora é da Manutenção


def test_transferir_exige_tipo_da_fila_destino(client, s, contas):
    entrar(client, "carlos", "carlos123")
    c = chamado(s, "Impressora do fiscal não imprime")
    html = client.post(f"/chamados/{c.id}/transferir", follow_redirects=True,
                       data={"csrf": csrf(client, "/chamados"), "fila": fila(s, "Manutenção").id,
                             "categoria": ""}).get_data(as_text=True)
    assert "Escolha o tipo de pedido" in html
    assert chamado(s, "Impressora do fiscal não imprime").fila.nome == "T.I"


def test_atribuir_so_para_atendente_da_fila(client, s, contas):
    entrar(client, "carlos", "carlos123")
    c = chamado(s, "Impressora do fiscal não imprime")
    for intruso in ("bruno", "marta"):                          # usuário comum e atendente de outra fila
        html = client.post(f"/chamados/{c.id}/responsavel", follow_redirects=True,
                           data={"csrf": csrf(client, "/chamados"), "responsavel": usuario(s, intruso).id}
                           ).get_data(as_text=True)
        assert "Escolha um atendente ativo da fila T.I" in html
    assert chamado(s, "Impressora do fiscal não imprime").responsavel_id is None


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

    entrar(client, "carlos", "carlos123")                      # atendente da fila: não apaga
    assert client.post(f"/chamados/{cid}/apagar", data={"csrf": csrf(client, "/chamados")}).status_code == 403
    sair(client)

    entrar(client, "admin", "admin123")
    client.post(f"/chamados/{cid}/apagar", data={"csrf": csrf(client, "/chamados")})
    s.expire_all()
    assert s.get(Chamado, cid) is None
    assert not s.scalars(select(Comentario).where(Comentario.chamado_id == cid)).all()
    assert not s.scalars(select(Anexo).where(Anexo.chamado_id == cid)).all()
    assert not os.path.exists(arquivo)


# ─── filas: administração ───────────────────────────────────────────────────

def test_admin_cria_fila_atendentes_e_tipos(client, s, contas):
    entrar(client, "admin", "admin123")
    token = csrf(client, "/filas")
    r = client.post("/filas", data={"csrf": token, "nome": "Compras", "descricao": "Pedidos de compra"})
    f = fila(s, "Compras")
    assert r.location.endswith(f"/filas/{f.id}")
    assert "Já existe" in client.post("/filas", data={"csrf": token, "nome": "compras"}).get_data(as_text=True)

    bruno = usuario(s, "bruno")
    client.post(f"/filas/{f.id}/atendentes", data={"csrf": token, "atendentes": [bruno.id]})
    client.post(f"/filas/{f.id}/categorias", data={"csrf": token, "nome": "Material de escritório"})
    f = fila(s, "Compras")
    assert [u.login for u in f.atendentes] == ["bruno"]
    assert [c.nome for c in f.categorias] == ["Material de escritório"]

    # desativar o tipo: some da abertura de chamado
    client.post(f"/categorias/{f.categorias[0].id}/ativa", data={"csrf": token, "ativa": "0"})
    assert not fila(s, "Compras").categorias_ativas

    # bruno passa a atender Compras
    sair(client)
    entrar(client, "bruno", "bruno123")
    assert client.get("/painel").status_code == 200


def test_tirar_atendente_da_fila_remove_responsabilidade(s, contas):
    servicos.definir_atendentes(s, fila(s, "T.I"), [usuario(s, "admin").id])   # carlos sai
    assert chamado(s, "Sem acesso à pasta da rede").responsavel_id is None
    assert chamado(s, "Trocar teclado").responsavel.login == "carlos"          # fechado: histórico fica


def test_painel_relatorio_por_fila(client, s, contas):
    entrar(client, "marta", "marta123")
    html = client.get("/painel").get_data(as_text=True)
    assert "Ar-condicionado" in html and "Impressora" not in html   # só tipos da Manutenção
    r = client.get("/relatorio/excel?de=2000-01-01&ate=2100-01-01")
    assert r.status_code == 200 and r.data[:2] == b"PK"
    from openpyxl import load_workbook
    ws = load_workbook(io.BytesIO(r.data)).active
    assert {row[2] for row in ws.iter_rows(min_row=2, values_only=True)} == {"Manutenção"}

    sair(client)
    entrar(client, "admin", "admin123")
    ti = fila(s, "T.I")
    for url in ("/painel", "/painel?dias=365", f"/painel?fila={ti.id}", "/usuarios", "/filas",
                f"/filas/{ti.id}", "/relatorio", "/conta/"):
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
