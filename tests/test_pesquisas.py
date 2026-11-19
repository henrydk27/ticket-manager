"""Pesquisa de satisfação da T.I: quem responde, abertura automática, lembrete e resultado."""

import io
from datetime import date, datetime, timedelta

from openpyxl import load_workbook

from app import notificacoes, pesquisas
from app.modelos import Pesquisa
from tests.conftest import csrf, entrar
from tests.test_app import sair, usuario


def responder(client, nota="9", resolvidos="todos", comentario=""):
    return client.post("/pesquisa", data={"nota": nota, "resolvidos": resolvidos, "comentario": comentario,
                                          "csrf": csrf(client, "/pesquisa")}, follow_redirects=True)


def test_quem_participa(s, contas):
    nomes = {u.login for u in pesquisas.participantes(s)}
    assert "ana" in nomes and "marta" in nomes                # fora da T.I
    assert "admin" not in nomes and "carlos" not in nomes      # administrador e a própria T.I


def test_abrir_responder_e_resultado(client, s, app, contas, emails):
    entrar(client, "admin", "admin123")
    r = client.post("/pesquisas/abrir", data={"csrf": csrf(client, "/pesquisas")}, follow_redirects=True)
    assert "Pesquisa aberta até" in r.get_data(as_text=True)
    p = pesquisas.aberta(s)
    assert p.encerra_em == date.today() + timedelta(days=6) and p.convidados == len(pesquisas.participantes(s))
    convites = [m for m in emails if "Pesquisa de satisfação" in m.assunto]
    assert {m.para for m in convites} == {u.email for u in pesquisas.participantes(s)}
    assert "/pesquisa" in convites[0].html
    # outra não abre enquanto esta estiver aberta
    assert "Já existe" in client.post("/pesquisas/abrir", data={"csrf": csrf(client, "/pesquisas")},
                                      follow_redirects=True).get_data(as_text=True)
    sair(client)

    entrar(client, "ana", "ana12345")
    assert "✎ Pesquisa" in client.get("/chamados").get_data(as_text=True)
    assert "Escolha uma nota" in responder(client, nota="11").get_data(as_text=True)
    assert "Obrigado" in responder(client, nota="4", resolvidos="poucos", comentario="Demora no retorno").get_data(as_text=True)
    assert "✎ Pesquisa" not in client.get("/chamados").get_data(as_text=True)
    assert "já respondeu" in client.get("/pesquisa").get_data(as_text=True)
    assert client.get(f"/pesquisas/{p.id}").status_code == 403          # resultado só para o administrador
    sair(client)

    entrar(client, "bruno", "bruno123")
    responder(client, nota="10")
    sair(client)
    entrar(client, "carlos", "carlos123")                                # T.I não responde
    assert "✎ Pesquisa" not in client.get("/chamados").get_data(as_text=True)
    assert "é para quem usa" in client.get("/pesquisa").get_data(as_text=True)
    sair(client)

    s.expire_all()
    res = pesquisas.resultado(s.get(Pesquisa, p.id))
    assert res.total == 2 and res.media == 7 and res.nps == 0 and res.promotores == 1 and res.detratores == 1
    entrar(client, "admin", "admin123")
    html = client.get(f"/pesquisas/{p.id}").get_data(as_text=True)
    assert "Demora no retorno" in html and "Ana" in html
    with client.get(f"/pesquisas/{p.id}/excel") as rx:
        linhas = list(load_workbook(io.BytesIO(rx.data))["Respostas"].iter_rows(values_only=True))
    assert linhas[0][1] == "Nome" and len(linhas) == 3
    with client.get(f"/pesquisas/{p.id}/pdf") as rp:
        assert rp.data.startswith(b"%PDF")
    client.post(f"/pesquisas/{p.id}/encerrar", data={"csrf": csrf(client, "/pesquisas")})
    s.expire_all()
    assert pesquisas.aberta(s) is None


def test_rotina_abre_em_junho_e_dezembro_e_lembra(s, app, contas):
    assert not pesquisas.deve_abrir(s, date(2026, 11, 30))
    assert pesquisas.deve_abrir(s, date(2026, 12, 1))
    assert not pesquisas.deve_abrir(s, date(2026, 12, 8))               # só na primeira semana
    assert pesquisas.deve_abrir(s, date(2027, 6, 1))

    p = pesquisas.abrir(s, hoje=date(2026, 12, 1))
    p.aberta_em = datetime(2026, 12, 1, 8)
    s.commit()
    assert not pesquisas.deve_abrir(s, date(2026, 12, 2))                # já abriu neste mês
    assert pesquisas.a_lembrar(s, date(2026, 12, 4))[0] is None          # cedo para o lembrete
    p2, faltam = pesquisas.a_lembrar(s, date(2026, 12, 5))
    assert p2.id == p.id and {u.login for u in faltam} == {u.login for u in pesquisas.participantes(s)}
    with app.test_request_context():
        msg = notificacoes.mensagem_pesquisa(faltam[0], p2, lembrete=True)
    assert "Lembrete" in msg.assunto and "07/12" in msg.assunto
    pesquisas.marcar_lembrete(s, p2)
    assert pesquisas.a_lembrar(s, date(2026, 12, 6))[0] is None          # um lembrete só
    assert pesquisas.aberta(s, date(2026, 12, 7)) and pesquisas.aberta(s, date(2026, 12, 8)) is None


def test_pesquisa_identificada_guarda_quem_respondeu(client, s, contas):
    p = pesquisas.abrir(s)
    ana = usuario(s, "ana")
    pesquisas.responder(s, p, ana, {"nota": "8", "resolvidos": "maioria"})
    s.expire_all()
    r = s.get(Pesquisa, p.id).respostas[0]
    assert r.usuario.login == "ana" and r.setor == ana.setor and r.nota == 8
