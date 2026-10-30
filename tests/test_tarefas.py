"""Tarefas recorrentes da T.I: datas, quem acessa, conclusão com histórico e avisos por e-mail."""

from datetime import date, timedelta

from sqlalchemy import select

from app import tarefas
from app.modelos import Tarefa, TarefaExecucao
from tests.conftest import csrf, entrar
from tests.test_app import sair, usuario


def nova(client, **campos):
    dados = {"titulo": "Conferir backup", "repeticao": "mensal", "inicio": date.today().isoformat(),
             "dia_mes": str(date.today().day), "avisar_dias": "0", "csrf": csrf(client, "/tarefas/nova")}
    dados.update(campos)
    return client.post("/tarefas/nova", data=dados, follow_redirects=True)


def tarefa(s, titulo="Conferir backup") -> Tarefa:
    s.expire_all()
    return s.scalar(select(Tarefa).where(Tarefa.titulo == titulo))


def test_datas_das_repeticoes():
    t = Tarefa(repeticao="mensal", dia_mes=31)
    assert tarefas.primeira_ocorrencia(t, date(2027, 2, 10)) == date(2027, 2, 28)
    assert tarefas.seguinte(t, date(2027, 2, 28)) == date(2027, 3, 31)
    assert tarefas.primeira_ocorrencia(Tarefa(repeticao="mensal", dia_mes=5), date(2026, 10, 30)) == date(2026, 11, 5)
    semanal = Tarefa(repeticao="semanal", dia_semana=0)                     # segunda
    assert tarefas.primeira_ocorrencia(semanal, date(2026, 10, 30)) == date(2026, 11, 2)
    assert tarefas.seguinte(semanal, date(2026, 11, 2)) == date(2026, 11, 9)
    tri = Tarefa(repeticao="meses", intervalo_meses=3)
    assert tarefas.seguinte(tri, date(2026, 11, 30)) == date(2027, 2, 28)
    assert tarefas.seguinte(Tarefa(repeticao="unica"), date(2026, 11, 30)) is None
    assert tarefas.descricao_repeticao(tri) == "A cada 3 meses (trimestral)"


def test_quem_acessa_as_tarefas(client, s, contas):
    for login, senha, pode in (("ana", "ana12345", False), ("marta", "marta123", False),
                               ("carlos", "carlos123", True), ("admin", "admin123", True)):
        entrar(client, login, senha)
        assert client.get("/tarefas/").status_code == (200 if pode else 403), login
        if pode:
            assert "/tarefas/" in client.get("/preventivas/").get_data(as_text=True)
        sair(client)


def test_cadastrar_concluir_e_historico(client, s, contas):
    entrar(client, "carlos", "carlos123")
    hoje = date.today()
    r = nova(client, titulo="Trocar senha do Wi-Fi", repeticao="meses", intervalo_meses="3",
             inicio=(hoje - timedelta(days=5)).isoformat(), descricao="Rede de visitantes")
    assert "cadastrada" in r.get_data(as_text=True)
    t = tarefa(s, "Trocar senha do Wi-Fi")
    assert t.proxima == hoje - timedelta(days=5) and tarefas.situacao(t).estado == "atrasada"
    assert "Trocar senha do Wi-Fi" in client.get("/tarefas/?estado=atrasada").get_data(as_text=True)
    assert "Trocar senha do Wi-Fi" not in client.get("/tarefas/?estado=em_dia").get_data(as_text=True)

    r = client.post(f"/tarefas/{t.id}/concluir", data={"observacao": "Senha nova no cofre", "csrf": csrf(client, "/tarefas/")},
                    follow_redirects=True)
    assert "concluída" in r.get_data(as_text=True)
    t = tarefa(s, "Trocar senha do Wi-Fi")
    assert t.ativa and t.proxima > hoje
    e = s.scalar(select(TarefaExecucao).where(TarefaExecucao.tarefa_id == t.id))
    assert e.observacao == "Senha nova no cofre" and e.usuario.login == "carlos"
    assert "Senha nova no cofre" in client.get(f"/tarefas/{t.id}").get_data(as_text=True)

    # uma vez só: depois de concluída, sai da lista e não volta
    nova(client, titulo="Renovar domínio", repeticao="unica")
    unica = tarefa(s, "Renovar domínio")
    client.post(f"/tarefas/{unica.id}/concluir", data={"csrf": csrf(client, "/tarefas/")}, follow_redirects=True)
    unica = tarefa(s, "Renovar domínio")
    assert not unica.ativa and unica.proxima is None
    assert "Renovar domínio" not in client.get("/tarefas/").get_data(as_text=True)
    assert "Renovar domínio" in client.get("/tarefas/?estado=concluida").get_data(as_text=True)


def test_validacao_e_responsavel(client, s, contas):
    entrar(client, "admin", "admin123")
    assert "Informe o título" in nova(client, titulo="  ").get_data(as_text=True)
    ana = usuario(s, "ana")                                   # não atende a T.I
    assert "responsável precisa" in nova(client, responsavel_id=str(ana.id)).get_data(as_text=True)
    assert tarefa(s) is None
    carlos = usuario(s, "carlos")
    nova(client, responsavel_id=str(carlos.id))
    assert tarefa(s).responsavel_id == carlos.id


def test_so_admin_apaga(client, s, contas):
    entrar(client, "carlos", "carlos123")
    nova(client)
    t = tarefa(s)
    client.post(f"/tarefas/{t.id}/concluir", data={"csrf": csrf(client, "/tarefas/")})
    assert client.post(f"/tarefas/{t.id}/apagar", data={"csrf": csrf(client, "/tarefas/")}).status_code == 403
    sair(client)
    entrar(client, "admin", "admin123")
    client.post(f"/tarefas/{t.id}/apagar", data={"csrf": csrf(client, "/tarefas/")})
    assert tarefa(s) is None and s.scalar(select(TarefaExecucao)) is None


def test_avisos_do_dia_e_semanal(client, s, app, contas):
    from app import notificacoes
    entrar(client, "admin", "admin123")
    hoje = date.today()
    carlos = usuario(s, "carlos")
    nova(client, titulo="Atrasada da equipe", repeticao="unica", inicio=(hoje - timedelta(days=2)).isoformat())
    nova(client, titulo="Do Carlos daqui a 3 dias", repeticao="unica", inicio=(hoje + timedelta(days=3)).isoformat(),
         avisar_dias="3", responsavel_id=str(carlos.id))
    nova(client, titulo="Longe", repeticao="unica", inicio=(hoje + timedelta(days=20)).isoformat(), avisar_dias="3")

    s.expire_all()
    avisos = {u.login: sorted(x.tarefa.titulo for x in itens) for u, itens in tarefas.avisos_do_dia(s).items()}
    assert avisos["carlos"] == ["Atrasada da equipe", "Do Carlos daqui a 3 dias"]
    assert avisos["admin"] == ["Atrasada da equipe"]
    assert "ana" not in avisos

    u = usuario(s, "carlos")
    itens = next(v for k, v in tarefas.avisos_do_dia(s).items() if k.login == "carlos")
    with app.test_request_context():
        msg = notificacoes.mensagem_tarefas(u, itens)
        assert msg.para == u.email and "1 atrasada(s)" in msg.assunto
        assert "Do Carlos daqui a 3 dias" in msg.texto and "/tarefas/" in msg.html

        app.extensions["email"].avisos_cpd = "cpd@empresa.com.br"
        semanal = notificacoes.mensagem_semanal([], [], tarefas.atrasadas(s))
    assert "1 tarefa atrasada" in semanal.assunto and "Atrasada da equipe" in semanal.texto
