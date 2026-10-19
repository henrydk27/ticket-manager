"""Contas cadastradas pelo admin, primeiro acesso e pedido de nova senha ao CPD."""

from datetime import timedelta

from sqlalchemy import select

from app import servicos
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
    app.extensions["email"].avisos_cpd = "cpd@empresa.com.br"
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


# ─── edição de usuário pelo admin ───────────────────────────────────────────

def editar(client, u, **campos):
    dados = {"csrf": csrf(client, f"/usuarios/{u.id}/editar"), "nome": u.nome, "login": u.login,
             "email": u.email or "", "setor": u.setor, "papel": u.papel, "atende": "1" if u.atende else ""}
    dados.update(campos)
    return client.post(f"/usuarios/{u.id}/editar", data=dados, follow_redirects=True)


def test_admin_edita_dados_de_quem_se_cadastrou_errado(client, s, contas):
    entrar(client, "admin", "admin123")
    bruno = usuario(s, "bruno")
    assert f"/usuarios/{bruno.id}/editar" in client.get("/usuarios").get_data(as_text=True)
    html = client.get(f"/usuarios/{bruno.id}/editar").get_data(as_text=True)
    assert 'value="Bruno Lima"' in html and "Salvar alterações" in html

    html = editar(client, bruno, nome="  Bruno  Lima Souza ", login="Bruno.Souza", email="BRUNO.SOUZA@empresa.com.br",
                  setor="Compras", papel="supervisor", atende="1").get_data(as_text=True)
    assert "Dados de Bruno Lima Souza salvos." in html
    b = usuario(s, "bruno.souza")
    assert (b.nome, b.email, b.setor, b.papel, b.atende) == (
        "Bruno Lima Souza", "bruno.souza@empresa.com.br", "Compras", "supervisor", True)
    sair(client)
    assert entrar(client, "bruno.souza", "bruno123").status_code == 302      # a senha continua a mesma
    assert client.get("/usuarios/1/editar").status_code == 403               # só admin edita
    sair(client)

    entrar(client, "admin", "admin123")
    b = usuario(s, "bruno.souza")
    assert "já está em uso" in editar(client, b, login="ana").get_data(as_text=True)
    assert "E-mail inválido" in editar(client, b, email="sem-arroba").get_data(as_text=True)
    assert usuario(s, "bruno.souza").email == "bruno.souza@empresa.com.br"   # nada foi gravado


def test_admin_nao_muda_o_proprio_perfil_pela_edicao(client, s, contas):
    entrar(client, "admin", "admin123")
    admin = usuario(s, "admin")
    editar(client, admin, nome="Administrador TI", papel="usuario")
    admin = usuario(s, "admin")
    assert admin.nome == "Administrador TI" and admin.is_admin


# ─── aviso ao CPD de conta nova e busca na tela de usuários ─────────────────

def test_conta_criada_pelo_login_avisa_o_cpd(client, s, app, contas, emails):
    from tests.test_app import cadastrar
    app.extensions["email"].avisos_cpd = "cpd@empresa.com.br"
    cadastrar(client)
    assert len(emails) == 1 and emails[0].para == "cpd@empresa.com.br"
    assert "Nova conta: Maria Teste" in emails[0].assunto
    maria = usuario(s, "maria")
    assert "RH" in emails[0].texto and f"/usuarios/{maria.id}/editar" in emails[0].texto
    sair(client)

    # cadastro feito pelo admin não gera aviso
    entrar(client, "admin", "admin123")
    cadastrar_pelo_admin(client)
    assert len(emails) == 1


def test_config_avisos_cpd_aceita_nome_antigo(tmp_path, monkeypatch):
    from app.config import carregar_config
    base = "[banco]\nurl = sqlite://\n[servidor]\nsecret_key = " + "x" * 40 + "\n[email]\nhost = mail\nremetente = a@b.com\n"
    ini = tmp_path / "config.ini"
    monkeypatch.setenv("TICKET_MANAGER_CONFIG", str(ini))
    ini.write_text(base + "avisos_senha = cpd@b.com\n", encoding="utf-8")
    assert carregar_config().email.avisos_cpd == "cpd@b.com"
    ini.write_text(base + "avisos_cpd = ti@b.com\n", encoding="utf-8")
    assert carregar_config().email.avisos_cpd == "ti@b.com"


def test_busca_e_filtros_na_tela_de_usuarios(client, s, contas):
    entrar(client, "admin", "admin123")
    cadastrar_pelo_admin(client)                                # joao.silva, aguardando primeiro acesso
    bruno = usuario(s, "bruno")
    bruno.senha_solicitada_em = bruno.criado_em
    s.commit()

    def nomes(url):
        html = client.get(url).get_data(as_text=True)
        return {n for n in ("Ana Souza", "Bruno Lima", "Carlos Técnico", "Marta Manutenção", "João da Silva")
                if f"<strong>{n}</strong>" in html}

    assert nomes("/usuarios") == {"Ana Souza", "Bruno Lima", "Carlos Técnico", "Marta Manutenção", "João da Silva"}
    assert nomes("/usuarios?q=souza") == {"Ana Souza"}
    assert nomes("/usuarios?q=empresa.com.br&setor=T.I") == {"Carlos Técnico"}
    assert nomes("/usuarios?situacao=senha") == {"Bruno Lima"}
    assert nomes("/usuarios?situacao=primeiro") == {"João da Silva"}
    servicos.atualizar_usuario(s, usuario(s, "marta"), "Manutenção", True, "supervisor")
    assert nomes("/usuarios?papel=supervisor") == {"Marta Manutenção"}
    client.post(f"/usuarios/{usuario(s, 'ana').id}/ativo", data={"csrf": csrf(client, "/usuarios"), "ativo": "0"})
    assert nomes("/usuarios?situacao=desativadas") == {"Ana Souza"}
    assert "Nenhuma conta com esses filtros" in client.get("/usuarios?q=ninguem").get_data(as_text=True)
    html = client.get("/usuarios?setor=Inexistente").get_data(as_text=True)   # filtro inválido é ignorado
    assert "<strong>Bruno Lima</strong>" in html
