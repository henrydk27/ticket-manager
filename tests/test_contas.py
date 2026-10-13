"""Contas cadastradas pelo admin, primeiro acesso e pedido de nova senha ao CPD."""

from datetime import timedelta

from sqlalchemy import select

from app.modelos import Usuario, agora
from tests.conftest import csrf, entrar
from tests.test_app import sair, usuario


def cadastrar_pelo_admin(client, **campos):
    dados = {"csrf": csrf(client, "/usuarios/novo"), "nome": "João da Silva", "login": "joao.silva",
             "email": "", "setor": "Expedição", "papel": "usuario"}
    dados.update(campos)
    return client.post("/usuarios/novo", data=dados, follow_redirects=True)


def entrar_so_com_usuario(client, login):
    return client.post("/login", data={"login": login, "senha": "", "csrf": csrf(client)})


def criar_senha(client, nova="senha123", confirmar=None):
    return client.post("/criar-senha", data={"csrf": csrf(client, "/criar-senha"), "nova": nova,
                                             "confirmar": confirmar or nova})


def test_admin_cadastra_e_pessoa_cria_senha_no_primeiro_acesso(client, s, contas):
    entrar(client, "admin", "admin123")
    assert "+ Cadastrar usuário" in client.get("/usuarios").get_data(as_text=True)
    html = cadastrar_pelo_admin(client).get_data(as_text=True)
    assert "Conta de João da Silva criada" in html and "aguardando primeiro acesso" in html
    joao = usuario(s, "joao.silva")
    assert joao.setor == "Expedição" and joao.email is None and joao.pode_criar_senha
    # já aparece para atribuir equipamentos
    assert "João da Silva" in client.get("/inventario/novo").get_data(as_text=True)
    assert "já está em uso" in cadastrar_pelo_admin(client).get_data(as_text=True)
    sair(client)

    # Ninguém entra com senha nenhuma: digitando só o usuário vai criar a senha
    r = entrar_so_com_usuario(client, "joao.silva")
    assert r.location.endswith("/criar-senha")
    assert "joao.silva" in client.get("/criar-senha").get_data(as_text=True)
    assert "não conferem" in client.post("/criar-senha", data={
        "csrf": csrf(client, "/criar-senha"), "nova": "senha123", "confirmar": "outra123"},
        follow_redirects=True).get_data(as_text=True)
    r = criar_senha(client)
    assert r.status_code == 302
    # sem e-mail cadastrado: o sistema pede o e-mail antes de seguir
    assert client.get("/chamados").location.endswith("/conta/")
    joao = usuario(s, "joao.silva")
    assert joao.senha_liberada_em is None and not joao.pode_criar_senha
    sair(client)

    # Senha criada: agora entra normalmente e "só o usuário" não funciona mais
    assert entrar_so_com_usuario(client, "joao.silva").status_code == 200
    assert client.get("/criar-senha").location.endswith("/login")
    assert entrar(client, "joao.silva", "senha123").status_code == 302


def test_cadastro_pelo_admin_so_para_admin(client, contas):
    entrar(client, "marta", "marta123")
    assert client.get("/usuarios/novo").status_code == 403


def test_prazo_para_criar_senha(client, s, contas):
    entrar(client, "admin", "admin123")
    cadastrar_pelo_admin(client)
    sair(client)
    joao = usuario(s, "joao.silva")
    joao.senha_liberada_em = agora() - timedelta(days=8)
    s.commit()
    html = client.post("/login", data={"login": "joao.silva", "senha": "", "csrf": csrf(client)},
                       follow_redirects=True).get_data(as_text=True)
    assert "prazo para criar sua senha venceu" in html


def test_solicitar_nova_senha_avisa_o_cpd_e_admin_libera(client, s, app, contas, emails):
    app.extensions["email"].avisos_senha = "cpd@empresa.com.br"
    assert "Solicitar nova senha" in client.get("/login").get_data(as_text=True)

    r = client.post("/solicitar-senha", data={"csrf": csrf(client, "/solicitar-senha"),
                                              "identificacao": "Bruno"}, follow_redirects=True)
    assert "Pedido enviado ao CPD" in r.get_data(as_text=True)
    assert len(emails) == 1 and emails[0].para == "cpd@empresa.com.br"
    assert "bruno" in emails[0].texto and "Liberar nova senha" in emails[0].html
    assert usuario(s, "bruno").senha_solicitada_em is not None

    # Pedido repetido logo em seguida e usuário inexistente: mesma resposta, sem novo e-mail
    for ident in ("bruno@empresa.com.br", "ninguem"):
        r = client.post("/solicitar-senha", data={"csrf": csrf(client, "/solicitar-senha"),
                                                  "identificacao": ident}, follow_redirects=True)
        assert "Pedido enviado ao CPD" in r.get_data(as_text=True)
    assert len(emails) == 1

    # O pedido sozinho não muda nada: a senha antiga continua valendo
    assert entrar(client, "bruno", "bruno123").status_code == 302
    sair(client)

    entrar(client, "admin", "admin123")
    html = client.get("/usuarios").get_data(as_text=True)
    assert "pediu nova senha" in html and 'class="contador-menu"' in html
    bruno = usuario(s, "bruno")
    html = client.post(f"/usuarios/{bruno.id}/senha", data={"csrf": csrf(client, "/usuarios")},
                       follow_redirects=True).get_data(as_text=True)
    assert "Nova senha liberada para Bruno" in html and "contador-menu" not in html
    sair(client)

    # Senha antiga parou de valer; com só o usuário, cria a nova
    assert entrar(client, "bruno", "bruno123").location.endswith("/criar-senha")
    criar_senha(client, "nova1234")
    assert client.get("/chamados").status_code == 200
    sair(client)
    assert entrar(client, "bruno", "nova1234").status_code == 302


def test_conta_desativada_nao_cria_senha(client, s, contas):
    entrar(client, "admin", "admin123")
    cadastrar_pelo_admin(client)
    joao = usuario(s, "joao.silva")
    client.post(f"/usuarios/{joao.id}/ativo", data={"csrf": csrf(client, "/usuarios"), "ativo": "0"})
    sair(client)
    assert entrar_so_com_usuario(client, "joao.silva").status_code == 200
    assert s.scalar(select(Usuario.senha_liberada_em).where(Usuario.login == "joao.silva")) is not None
