"""Avisos por e-mail sobre os chamados.

Regras: ninguém recebe aviso da própria ação, e só recebe quem tem e-mail e conta ativa.
- chamado novo          → funcionário escolhido
- encaminhado           → novo responsável
- comentário            → solicitante e responsável
- mudança de status     → solicitante (encerrado: com link para avaliar)
- pedido de nova senha  → CPD (config avisos_cpd; vazio = remetente)
- conta nova (login)    → CPD
- avaliação pendente    → quem abriu (até 2 lembretes: python manage.py avisos-diarios)
- tarefas da T.I        → responsável (ou toda a T.I): atrasadas, do dia e no prazo de aviso
- pesquisa de satisfação → quem não é da T.I: convite em junho e dezembro e um lembrete
                          (python manage.py avisos-diarios)
- SLA em risco (75%)    → responsável; SLA estourado → responsável e CPD
                          (python manage.py verificar-sla, a cada 15 min no expediente)
- resumo semanal        → CPD: preventivas pendentes, contratos vencendo/vencidos e tarefas atrasadas
                          (python manage.py avisar-semanal, agendado no cron)
"""

from flask import current_app, render_template, request, url_for

from . import correio, formatos
from .modelos import STATUS_FECHADO, Chamado, Comentario, Usuario


def _link(endpoint: str, **valores) -> str:
    base = current_app.extensions["email"].url_site
    if base:
        return base + url_for(endpoint, **valores)
    return url_for(endpoint, _external=True, **valores)


def _resumo(texto: str, limite: int = 1200) -> str:
    texto = (texto or "").strip()
    return texto if len(texto) <= limite else texto[:limite].rstrip() + "…"


def _avisar(destinos: list[Usuario | None], autor: Usuario, c: Chamado, assunto: str, frase: str,
            citacao: str = "", botao: str = "Abrir chamado", link: str | None = None) -> None:
    if not correio.ativo():
        return
    link = link or _link("chamados.detalhe", chamado_id=c.id)
    enviados = set()
    for u in destinos:
        if u is None or u.id == autor.id or not u.ativo or not u.email or u.id in enviados:
            continue
        enviados.add(u.id)
        dados = dict(destino=u, c=c, frase=frase, citacao=_resumo(citacao), botao=botao, link=link,
                     cid_marca=correio.CID_MARCA)
        correio.enviar(correio.Mensagem(
            para=u.email,
            assunto=f"[Chamado #{c.id}] {assunto}: {c.titulo}",
            texto=render_template("email/aviso.txt", **dados),
            html=render_template("email/aviso.html", **dados),
        ))


def chamado_aberto(c: Chamado) -> None:
    _avisar([c.responsavel], c.solicitante, c, "Novo chamado",
            f"{c.solicitante.nome} ({c.setor}) abriu um chamado para você.", c.descricao)


def chamado_encaminhado(c: Chamado, autor: Usuario) -> None:
    _avisar([c.responsavel], autor, c, "Encaminhado para você",
            f"{autor.nome} encaminhou este chamado para você ({c.setor_destino}).", c.descricao)


def comentario_novo(c: Chamado, autor: Usuario, m: Comentario) -> None:
    anexos = f" (com {len(m.anexos)} anexo{'s' if len(m.anexos) > 1 else ''})" if m.anexos else ""
    _avisar([c.solicitante, c.responsavel], autor, c, "Nova resposta",
            f"{autor.nome} comentou no chamado{anexos}:", m.texto)


def status_alterado(c: Chamado, autor: Usuario, anterior: str) -> None:
    if c.status == STATUS_FECHADO:
        link = _link("chamados.avaliacoes") if not c.avaliacao else None
        _avisar([c.solicitante], autor, c, "Chamado encerrado",
                f"{autor.nome} encerrou o seu chamado. Conte como foi o atendimento.",
                botao="Avaliar atendimento" if link else "Abrir chamado", link=link)
    else:
        _avisar([c.solicitante], autor, c, f"Status: {c.status}",
                f"{autor.nome} mudou o status do chamado de \"{anterior}\" para \"{c.status}\".")


def _avisar_cpd(assunto: str, titulo: str, u: Usuario, frase: str, linhas: list[tuple[str, str]],
                instrucao: str) -> None:
    if not correio.ativo():
        return
    cfg = current_app.extensions["email"]
    destino = cfg.avisos_cpd or cfg.remetente
    if not destino:
        return
    dados = dict(titulo=titulo, u=u, frase=frase, linhas=linhas, instrucao=instrucao, botao="Abrir cadastro",
                 link=_link("admin.usuario_editar", usuario_id=u.id), cid_marca=correio.CID_MARCA)
    correio.enviar(correio.Mensagem(
        para=destino,
        assunto=f"[Ticket Manager] {assunto}: {u.nome}",
        texto=render_template("email/cpd.txt", **dados),
        html=render_template("email/cpd.html", **dados),
    ))


def _dados_conta(u: Usuario, momento) -> list[tuple[str, str]]:
    ip = request.remote_addr
    return [("Usuário", u.login), ("Setor", u.setor), ("E-mail", u.email or "não cadastrado"),
            ("Em", formatos.data_hora(momento) + (f" (de {ip})" if ip else ""))]


def pedido_nova_senha(u: Usuario) -> None:
    """Avisa o CPD que a pessoa pediu uma nova senha na tela de login."""
    _avisar_cpd("Pedido de nova senha", "Pedido de nova senha", u,
                "Esta pessoa pediu uma nova senha na tela de login.", _dados_conta(u, u.senha_solicitada_em),
                "Confirme que o pedido é mesmo da pessoa. Depois, no cadastro dela, clique em "
                "\"Liberar nova senha\": no próximo acesso ela digita só o usuário e cria a senha nova.")


def conta_criada(u: Usuario) -> None:
    """Avisa o CPD que alguém criou a própria conta na tela de login."""
    _avisar_cpd("Nova conta", "Nova conta criada", u, "Esta pessoa criou uma conta pela tela de login.",
                _dados_conta(u, u.criado_em),
                "Confira se o nome e o setor estão certos e ajuste o perfil e \"Atende chamados\", se for o caso. "
                "Se a conta não for de alguém da empresa, desative-a.")


def mensagem_semanal(pendentes: list, contratos: list | None = None,
                     tarefas: list | None = None) -> "correio.Mensagem | None":
    """Resumo semanal ao CPD: preventivas atrasadas/vencendo, contratos vencendo/vencidos e tarefas atrasadas.

    None = nada a avisar ou sem destino configurado.
    """
    contratos, tarefas = contratos or [], tarefas or []
    cfg = current_app.extensions["email"]
    destino = cfg.avisos_cpd or cfg.remetente
    if not (pendentes or contratos or tarefas) or not destino:
        return None
    atrasadas = [x for x in pendentes if x.estado == "atrasada"]
    proximas = [x for x in pendentes if x.estado != "atrasada"]
    vencidos = [d for d in contratos if d.situacao_vencimento == "vencido"]
    vencendo = [d for d in contratos if d.situacao_vencimento != "vencido"]
    dados = dict(atrasadas=atrasadas, proximas=proximas, vencidos=vencidos, vencendo=vencendo, tarefas=tarefas,
                 link_preventivas=_link("preventivas.lista"), link_tarefas=_link("tarefas.lista", estado="atrasada"),
                 link_contratos=_link("documentos.lista", categoria="Contratos"), cid_marca=correio.CID_MARCA)

    def qtd(n, um, varios):
        return f"{n} {um if n == 1 else varios}"
    partes = []
    if pendentes:
        partes.append(qtd(len(pendentes), "preventiva pendente", "preventivas pendentes"))
    if vencendo:
        partes.append(qtd(len(vencendo), "contrato vencendo", "contratos vencendo"))
    if vencidos:
        partes.append(qtd(len(vencidos), "contrato vencido", "contratos vencidos"))
    if tarefas:
        partes.append(qtd(len(tarefas), "tarefa atrasada", "tarefas atrasadas"))
    return correio.Mensagem(
        para=destino, assunto="[Ticket Manager] Avisos da semana: " + ", ".join(partes),
        texto=render_template("email/semanal.txt", **dados),
        html=render_template("email/semanal.html", **dados))


def mensagem_lembrete_avaliacao(u: Usuario, chamados: list) -> "correio.Mensagem | None":
    """Lembra quem abriu de avaliar os chamados encerrados (uma mensagem com todos)."""
    if not chamados or not u.email or not u.ativo:
        return None
    n = len(chamados)
    dados = dict(destino=u, chamados=chamados, link=_link("chamados.avaliacoes"), cid_marca=correio.CID_MARCA)
    return correio.Mensagem(
        para=u.email,
        assunto=("[Ticket Manager] Como foi o atendimento? " +
                 (f"Chamado #{chamados[0].id}: {chamados[0].titulo}" if n == 1 else f"{n} chamados esperando avaliação")),
        texto=render_template("email/lembrete_avaliacao.txt", **dados),
        html=render_template("email/lembrete_avaliacao.html", **dados))


def mensagem_tarefas(u: Usuario, itens: list) -> "correio.Mensagem | None":
    """Aviso diário das tarefas da T.I: atrasadas, de hoje e as que vencem no prazo de aviso."""
    if not itens or not u.email or not u.ativo:
        return None
    atrasadas = [x for x in itens if x.estado == "atrasada"]
    hoje = [x for x in itens if x.estado == "hoje"]
    proximas = [x for x in itens if x.estado not in ("atrasada", "hoje")]
    dados = dict(destino=u, atrasadas=atrasadas, hoje=hoje, proximas=proximas,
                 link=_link("tarefas.lista"), cid_marca=correio.CID_MARCA)
    if len(itens) == 1:
        x = itens[0]
        quando = {"atrasada": "atrasada", "hoje": "para hoje"}.get(
            x.estado, f"em {x.dias} dia{'s' if x.dias != 1 else ''}")
        assunto = f"[Ticket Manager] Tarefa {quando}: {x.tarefa.titulo}"
    else:
        partes = [f"{len(lista)} {rotulo}" for lista, rotulo in
                  ((atrasadas, "atrasada(s)"), (hoje, "para hoje"), (proximas, "chegando")) if lista]
        assunto = "[Ticket Manager] Tarefas da T.I: " + ", ".join(partes)
    return correio.Mensagem(para=u.email, assunto=assunto,
                            texto=render_template("email/tarefas.txt", **dados),
                            html=render_template("email/tarefas.html", **dados))


def mensagem_pesquisa(u: Usuario, p, lembrete: bool = False) -> "correio.Mensagem | None":
    """Convite (ou lembrete) para responder a pesquisa de satisfação da T.I."""
    if not u.email or not u.ativo:
        return None
    dados = dict(destino=u, p=p, lembrete=lembrete, link=_link("pesquisas.responder"), cid_marca=correio.CID_MARCA)
    assunto = ("[Ticket Manager] Lembrete: a pesquisa de satisfação da T.I fecha em " if lembrete
               else "[Ticket Manager] Pesquisa de satisfação da T.I: responda até ") + f"{p.encerra_em:%d/%m}"
    return correio.Mensagem(para=u.email, assunto=assunto,
                            texto=render_template("email/pesquisa.txt", **dados),
                            html=render_template("email/pesquisa.html", **dados))


def mensagens_sla(c: Chamado, r, nivel: int) -> list["correio.Mensagem"]:
    """Alerta de SLA: em risco (75% do prazo) → responsável; estourado → responsável e CPD."""
    from types import SimpleNamespace

    from . import sla
    estourado = nivel >= sla.NIVEL_ESTOURADO
    if estourado:
        assunto = f"[Chamado #{c.id}] SLA estourado ({r.nome.lower()}): {c.titulo}"
        frase = (f"O prazo de {r.nome.lower()} deste chamado ({sla.texto(r.meta)} de expediente) "
                 f"estourou há {sla.texto(-r.restante)}.")
    else:
        assunto = f"[Chamado #{c.id}] SLA em risco ({r.nome.lower()}): {c.titulo}"
        frase = (f"Já foram usados {round(r.pct)}% do prazo de {r.nome.lower()} deste chamado. "
                 f"Faltam {sla.texto(r.restante)} de expediente"
                 + (f" (até {formatos.data_hora(r.prazo)})." if r.prazo else "."))
    destinos = []
    if c.responsavel and c.responsavel.ativo and c.responsavel.email:
        destinos.append((c.responsavel.email, c.responsavel))
    if estourado:
        cfg = current_app.extensions["email"]
        cpd = cfg.avisos_cpd or cfg.remetente
        if cpd and cpd not in [e for e, _u in destinos]:
            destinos.append((cpd, SimpleNamespace(nome="equipe")))
    link = _link("chamados.detalhe", chamado_id=c.id)
    msgs = []
    for email, quem in destinos:
        dados = dict(destino=quem, c=c, frase=frase, citacao="", botao="Abrir chamado", link=link,
                     cid_marca=correio.CID_MARCA)
        msgs.append(correio.Mensagem(para=email, assunto=assunto,
                                     texto=render_template("email/aviso.txt", **dados),
                                     html=render_template("email/aviso.html", **dados)))
    return msgs
