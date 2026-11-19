"""SLA: prioridade por impacto x urgência, relógios no expediente, pausa, metas, alertas e telas."""

import io
from datetime import datetime, timedelta

from openpyxl import load_workbook

from app import notificacoes, servicos, sla
from app.expediente import segundos_expediente, somar_expediente
from app.modelos import STATUS_AGUARDANDO, STATUS_ANDAMENTO, STATUS_FECHADO, Chamado
from tests.conftest import csrf, entrar
from tests.test_app import abrir, chamado, sair, usuario

SEG = datetime(2026, 11, 16, 8, 0)        # segunda-feira, 8h


def novo(s, autor="ana", prioridade="Média", categoria="Incidente", setor="T.I", para="carlos",
         inicio=SEG) -> Chamado:
    c = servicos.criar_chamado(s, usuario(s, autor), setor, usuario(s, para).id, "Teste SLA", "x",
                               prioridade, [], categoria)
    if c.sla_inicio:
        c.aberto_em = c.sla_inicio = inicio
        s.commit()
    return c


def test_somar_expediente_e_inverso():
    sexta = datetime(2026, 11, 20, 17, 0)
    assert somar_expediente(sexta, 2 * 3600) == datetime(2026, 11, 23, 8, 0)      # pula o fim de semana
    assert somar_expediente(datetime(2026, 11, 16, 5, 0), 30 * 60) == datetime(2026, 11, 16, 7, 30)
    for ini, seg in ((SEG, 3600), (sexta, 15 * 3600), (datetime(2026, 11, 21, 10), 11 * 3600)):
        assert segundos_expediente(ini, somar_expediente(ini, seg)) == seg


def test_formulario_calcula_prioridade_pela_matriz(client, s, contas):
    entrar(client, "ana", "ana12345")
    html = client.get("/chamados/novo").get_data(as_text=True)
    assert "Quem está sendo afetado?" in html and "Mouse ou teclado" in html
    dados = {"impacto": "empresa", "urgencia": "parou"}
    r = client.post("/chamados/novo", content_type="multipart/form-data", data={
        "csrf": csrf(client, "/chamados/novo"), "setor_destino": "T.I", "responsavel": usuario(s, "carlos").id,
        "titulo": "Sem internet", "descricao": "Caiu tudo", "categoria": "Incidente", **dados})
    assert r.status_code == 302
    c = chamado(s, "Sem internet")
    assert (c.prioridade, c.impacto, c.urgencia) == ("Alta", "empresa", "parou")
    assert (c.sla_atendimento_min, c.sla_solucao_min) == (30, 240) and c.sla_inicio is not None
    client.post("/chamados/novo", content_type="multipart/form-data", data={
        "csrf": csrf(client, "/chamados/novo"), "setor_destino": "T.I", "responsavel": usuario(s, "carlos").id,
        "titulo": "Mouse com defeito", "descricao": "Clique falha", "categoria": "Incidente",
        "impacto": "pessoa", "urgencia": "atrapalha"})
    assert chamado(s, "Mouse com defeito").prioridade == "Baixa"
    r = client.post("/chamados/novo", content_type="multipart/form-data", data={
        "csrf": csrf(client, "/chamados/novo"), "setor_destino": "T.I", "responsavel": usuario(s, "carlos").id,
        "titulo": "Sem resposta", "descricao": "x", "categoria": "Incidente", "impacto": "pessoa"})
    assert "quanto isso atrapalha" in r.get_data(as_text=True)


def test_so_a_ti_tem_sla(s, contas):
    assert novo(s, setor="Manutenção", para="marta").sla_inicio is None
    c = novo(s)
    assert c.sla_inicio is not None
    servicos.encaminhar(s, c, "Manutenção", usuario(s, "marta").id, usuario(s, "carlos"))
    assert c.sla_inicio is None and c.sla_solucao_min is None
    servicos.encaminhar(s, c, "T.I", usuario(s, "carlos").id, usuario(s, "marta"))
    assert c.sla_inicio is not None and c.sla_solucao_min == 11 * 60
    assert novo(s, categoria="Problema", autor="carlos", para="admin").sla_solucao_min is None


def test_relogios_pausa_e_reabertura(s, contas):
    c = novo(s, prioridade="Média")                  # incidente médio: 2 h / 1 dia útil
    at = sla.relogio_atendimento(c, SEG + timedelta(hours=1, minutes=40))
    assert at.estado == "risco" and at.prazo == SEG + timedelta(hours=2)
    assert sla.relogio_atendimento(c, SEG + timedelta(hours=3)).estado == "estourado"

    # comentário de quem abriu não conta como atendimento; da T.I conta
    sla.atendeu(c, usuario(s, "ana"), SEG + timedelta(hours=1))
    assert c.primeiro_atendimento_em is None
    sla.atendeu(c, usuario(s, "carlos"), SEG + timedelta(hours=1))
    assert sla.relogio_atendimento(c).estado == "cumprido"

    # 3 h correndo, 2 dias em "Aguardando usuário", volta e corre mais 2 h
    sla.mudou_status(c, STATUS_ANDAMENTO, STATUS_AGUARDANDO, SEG + timedelta(hours=3))
    c.status, c.pausado_em = STATUS_AGUARDANDO, SEG + timedelta(hours=3)
    r = sla.relogio_solucao(c, SEG + timedelta(days=2))
    assert r.estado == "pausado" and r.usado == 3 * 3600
    sla.mudou_status(c, STATUS_AGUARDANDO, STATUS_ANDAMENTO, SEG + timedelta(days=2, hours=3))
    c.status = STATUS_ANDAMENTO
    assert c.pausa_segundos == 22 * 3600
    r = sla.relogio_solucao(c, SEG + timedelta(days=2, hours=5))
    assert r.usado == 5 * 3600 and r.estado == "ok" and sla.texto(r.restante) == "6 h"
    assert r.prazo == datetime(2026, 11, 19, 8, 0)           # quarta 13h + 6 h = 5 h hoje + 1 h na quinta

    # fecha dentro do prazo; reabrir retoma de onde parou
    sla.mudou_status(c, STATUS_ANDAMENTO, STATUS_FECHADO, SEG + timedelta(days=2, hours=6))
    c.status, c.fechado_em = STATUS_FECHADO, SEG + timedelta(days=2, hours=6)
    assert sla.relogio_solucao(c).estado == "cumprido"
    sla.mudou_status(c, STATUS_FECHADO, STATUS_ANDAMENTO, SEG + timedelta(days=3, hours=6))
    c.status, c.fechado_em = STATUS_ANDAMENTO, None
    assert sla.relogio_solucao(c, SEG + timedelta(days=3, hours=6)).usado == 6 * 3600


def test_ti_ajusta_prioridade_e_recalcula(client, s, contas):
    c = novo(s, prioridade="Baixa")
    assert c.sla_solucao_min == 3 * 11 * 60
    entrar(client, "ana", "ana12345")
    assert client.post(f"/chamados/{c.id}/prioridade", data={"prioridade": "Alta",
                                                             "csrf": csrf(client, "/chamados")}).status_code == 403
    sair(client)
    entrar(client, "carlos", "carlos123")
    html = client.post(f"/chamados/{c.id}/prioridade", data={"prioridade": "Alta", "csrf": csrf(client, "/chamados")},
                       follow_redirects=True).get_data(as_text=True)
    assert "prazos do SLA recalculados" in html and "Prioridade alterada de" in html
    s.expire_all()
    c = s.get(Chamado, c.id)
    assert (c.prioridade, c.sla_atendimento_min, c.sla_solucao_min) == ("Alta", 30, 240)


def test_metas_editaveis_pelo_admin(client, s, contas):
    entrar(client, "admin", "admin123")
    html = client.get("/sla").get_data(as_text=True)
    assert "Metas de SLA da T.I" in html
    dados = {"csrf": csrf(client, "/sla")}
    for i, (at, sol) in enumerate(sla.metas(s).values()):
        dados[f"at{i}"] = f"{at / 60:g}".replace(".", ",") if at else ""
        dados[f"sol{i}"] = f"{sol / 60:g}" if sol else ""
    dados["at0"], dados["sol0"] = "0,25", "2"                       # Incidente – Alta: 15 min / 2 h
    assert "Metas de SLA salvas" in client.post("/sla", data=dados, follow_redirects=True).get_data(as_text=True)
    s.expire_all()
    assert sla.metas(s)[("Incidente", "Alta")] == (15, 120)
    dados["at0"] = "5"                                               # atendimento maior que a solução
    assert "não pode ter prazo maior" in client.post("/sla", data=dados, follow_redirects=True).get_data(as_text=True)
    sair(client)
    entrar(client, "carlos", "carlos123")
    assert client.get("/sla").status_code == 403


def test_alertas_risco_e_estourado(app, s, contas, emails):
    c = novo(s, prioridade="Alta", inicio=datetime.now() - timedelta(days=7))
    with app.test_request_context():
        itens = sla.alertas(s)
        assert {(r.tipo, nivel) for _c, r, nivel in itens} == {("atendimento", 2), ("solucao", 2)}
        msgs = notificacoes.mensagens_sla(c, itens[0][1], itens[0][2])
    assert "SLA estourado" in msgs[0].assunto and msgs[0].para == usuario(s, "carlos").email
    for x, r, nivel in itens:
        sla.marcar_aviso(x, r, nivel)
    s.commit()
    assert sla.alertas(s) == []                                       # não repete


def test_lista_painel_e_relatorio(client, s, contas):
    atrasado = novo(s, prioridade="Alta", inicio=datetime.now() - timedelta(days=7))
    novo(s, prioridade="Baixa", inicio=datetime.now())
    entrar(client, "carlos", "carlos123")
    html = client.get("/chamados").get_data(as_text=True)
    assert "SLA estourado há" in html
    html = client.get("/chamados?sla=estourado").get_data(as_text=True)
    assert f"#{atrasado.id}" in html and "1 encontrado" in html
    html = client.get(f"/chamados/{atrasado.id}").get_data(as_text=True)
    assert "Primeiro atendimento" in html and "Estourado há" in html
    assert "SLA da T.I" in client.get("/painel").get_data(as_text=True)
    servicos.alterar_status(s, atrasado, STATUS_FECHADO, usuario(s, "carlos"))
    sair(client)
    entrar(client, "admin", "admin123")
    hoje = datetime.now().date()
    with client.get(f"/relatorio/excel?de={hoje - timedelta(days=8):%Y-%m-%d}&ate={hoje:%Y-%m-%d}") as r:
        linhas = list(load_workbook(io.BytesIO(r.data)).active.iter_rows(values_only=True))
    cab = list(linhas[0])
    assert "SLA solução" in cab
    valores = {linha[0]: linha[cab.index("SLA solução")] for linha in linhas[1:]}
    assert valores[atrasado.id] == "Fora do prazo"
    with client.get(f"/relatorio/pdf?de={hoje - timedelta(days=8):%Y-%m-%d}&ate={hoje:%Y-%m-%d}") as r:
        assert r.data.startswith(b"%PDF")
