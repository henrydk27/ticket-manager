"""Testes do inventário de TI."""

import io

from openpyxl import load_workbook
from sqlalchemy import select

from app.modelos import Equipamento, Usuario
from tests.conftest import csrf, entrar


def eq(s, patrimonio) -> Equipamento:
    s.expire_all()
    return s.scalar(select(Equipamento).where(Equipamento.patrimonio == patrimonio))


def uid(s, login) -> int:
    return s.scalar(select(Usuario.id).where(Usuario.login == login))


def cadastrar(client, **campos):
    dados = {"csrf": csrf(client, "/inventario/novo"), "patrimonio": "000123", "tipo": "Desktop",
             "situacao": "Em estoque", "setor": "", "usuario_id": "", "marca": "Dell",
             "modelo": "OptiPlex 3080", "numero_serie": "ABC123", "processador": "i5-10500",
             "memoria": "16 GB", "armazenamento": "SSD 512 GB", "sistema_operacional": "Windows 11",
             "hostname": "FISCAL-01", "ip": "192.168.0.25", "mac": "aa-bb-cc-dd-ee-ff", "observacoes": ""}
    dados.update(campos)
    return client.post("/inventario/novo", data=dados, follow_redirects=True)


def editar(client, e, **campos):
    dados = {"csrf": csrf(client, f"/inventario/{e.id}")}
    for c in ("patrimonio", "tipo", "situacao", "setor", "marca", "modelo", "numero_serie", "processador",
              "memoria", "armazenamento", "sistema_operacional", "hostname", "ip", "mac", "observacoes"):
        dados[c] = getattr(e, c) or ""
    dados["usuario_id"] = e.usuario_id or ""
    dados.update(campos)
    return client.post(f"/inventario/{e.id}", data=dados, follow_redirects=True)


def test_acesso_so_admin(client, contas):
    # carlos atende a T.I, mas não é administrador: também fica sem acesso
    for login, senha, esperado in (("ana", "ana12345", 403), ("marta", "marta123", 403),
                                   ("carlos", "carlos123", 403), ("admin", "admin123", 200)):
        entrar(client, login, senha)
        assert client.get("/inventario/").status_code == esperado, login
        tem_menu = "/inventario/" in client.get("/chamados").get_data(as_text=True)
        assert tem_menu == (esperado == 200), login
        client.post("/logout", data={"csrf": csrf(client, "/conta/")})


def test_cadastrar_com_patrimonio_existente_e_normalizar(client, s, contas):
    entrar(client, "admin", "admin123")
    html = cadastrar(client).get_data(as_text=True)
    assert "Equipamento 000123 cadastrado." in html
    e = eq(s, "000123")
    assert e.mac == "AA:BB:CC:DD:EE:FF" and e.ip == "192.168.0.25" and e.situacao == "Em estoque"
    assert e.historico[0].descricao == "Cadastrado: Em estoque." and e.historico[0].autor.login == "admin"


def test_patrimonio_unico_e_validacoes(client, contas):
    entrar(client, "admin", "admin123")
    cadastrar(client)
    assert "Já existe um equipamento com o patrimônio" in cadastrar(client, patrimonio="000123").get_data(as_text=True)
    assert "Informe o nº de patrimônio" in cadastrar(client, patrimonio=" ").get_data(as_text=True)
    assert "IP inválido" in cadastrar(client, patrimonio="X1", ip="192.168.0.300").get_data(as_text=True)
    assert "MAC inválido" in cadastrar(client, patrimonio="X2", mac="12:34").get_data(as_text=True)
    assert "Escolha o tipo" in cadastrar(client, patrimonio="X3", tipo="Geladeira").get_data(as_text=True)


def test_atribuir_a_usuario_preenche_setor_e_vira_em_uso(client, s, contas):
    entrar(client, "admin", "admin123")
    cadastrar(client, usuario_id=uid(s, "ana"))
    e = eq(s, "000123")
    assert e.usuario.login == "ana" and e.setor == "Fiscal" and e.situacao == "Em uso"


def test_historico_de_movimentacoes(client, s, contas):
    entrar(client, "admin", "admin123")
    cadastrar(client, usuario_id=uid(s, "ana"))
    editar(client, eq(s, "000123"), usuario_id=uid(s, "bruno"), setor="Vendas")
    editar(client, eq(s, "000123"), memoria="32 GB")
    editar(client, eq(s, "000123"), situacao="Descartado")
    e = eq(s, "000123")
    textos = [m.descricao for m in reversed(e.historico)]
    assert textos[0] == "Cadastrado: Em uso, setor Fiscal, com Ana Souza."
    assert textos[1] == "Setor: Fiscal → Vendas. Usuário: Ana Souza → Bruno Lima."
    assert textos[2] == "Dados alterados: Memória."
    assert textos[3] == "Setor: Vendas → nenhum. Usuário: Bruno Lima → ninguém. Situação: Em uso → Descartado."
    assert e.usuario_id is None and e.setor is None          # descartado não fica com ninguém


def test_salvar_sem_mudanca_nao_gera_historico(client, s, contas):
    entrar(client, "admin", "admin123")
    cadastrar(client)
    editar(client, eq(s, "000123"))
    assert len(eq(s, "000123").historico) == 1


def test_lista_filtros_e_busca(client, s, contas):
    entrar(client, "admin", "admin123")
    cadastrar(client, usuario_id=uid(s, "ana"))
    cadastrar(client, patrimonio="000200", tipo="Monitor", marca="LG", modelo="24MK430", numero_serie="",
              hostname="", ip="", mac="", setor="Vendas")
    cadastrar(client, patrimonio="000300", tipo="Notebook", situacao="Descartado", hostname="VELHO", ip="", mac="")
    html = client.get("/inventario/").get_data(as_text=True)
    assert "000123" in html and "000200" in html and "000300" not in html     # descartados ficam fora
    assert "000300" in client.get("/inventario/?situacao=todas").get_data(as_text=True)
    html = client.get("/inventario/?q=fiscal-01").get_data(as_text=True)
    assert "000123" in html and "000200" not in html
    html = client.get("/inventario/?q=ana").get_data(as_text=True)          # busca pelo nome do usuário
    assert "000123" in html and "000200" not in html
    html = client.get("/inventario/?tipo=Monitor").get_data(as_text=True)
    assert "000200" in html and "000123" not in html
    html = client.get("/inventario/?setor=Vendas").get_data(as_text=True)
    assert "000200" in html and "000123" not in html
    for coluna in ("patrimonio", "tipo", "modelo", "setor", "usuario", "situacao", "atualizado"):
        for direcao in ("asc", "desc"):
            assert client.get(f"/inventario/?ordenar={coluna}&direcao={direcao}").status_code == 200


def test_exportar_excel_com_filtros(client, s, contas):
    entrar(client, "admin", "admin123")
    cadastrar(client, usuario_id=uid(s, "ana"))
    cadastrar(client, patrimonio="000200", tipo="Monitor", hostname="", ip="", mac="")
    r = client.get("/inventario/exportar?tipo=Desktop")
    assert r.status_code == 200 and r.data[:2] == b"PK"
    ws = load_workbook(io.BytesIO(r.data)).active
    linhas = list(ws.iter_rows(values_only=True))
    assert linhas[0][:3] == ("Patrimônio", "Tipo", "Marca")
    assert [l[0] for l in linhas[1:]] == ["000123"]
    assert linhas[1][7] == "Ana Souza" and linhas[1][14] == "AA:BB:CC:DD:EE:FF"


def test_so_admin_apaga_equipamento(client, s, contas):
    entrar(client, "admin", "admin123")
    cadastrar(client)
    e = eq(s, "000123")
    client.post("/logout", data={"csrf": csrf(client, "/conta/")})
    entrar(client, "carlos", "carlos123")
    assert client.post(f"/inventario/{e.id}/apagar", data={"csrf": csrf(client, "/conta/")}).status_code == 403
    client.post("/logout", data={"csrf": csrf(client, "/conta/")})
    entrar(client, "admin", "admin123")
    client.post(f"/inventario/{e.id}/apagar", data={"csrf": csrf(client, "/inventario/")})
    assert eq(s, "000123") is None


def test_usuario_desativado_continua_no_equipamento(client, s, contas):
    entrar(client, "admin", "admin123")
    cadastrar(client, usuario_id=uid(s, "ana"))
    ana = s.get(Usuario, uid(s, "ana"))
    ana.ativo = False
    s.commit()
    html = client.get(f"/inventario/{eq(s, '000123').id}").get_data(as_text=True)
    assert "Ana Souza (conta desativada)" in html
    editar(client, eq(s, "000123"), memoria="8 GB")                 # salvar outra coisa não perde o vínculo
    assert eq(s, "000123").usuario_id == ana.id
