"""Avisos por e-mail sobre os chamados.

Regras: ninguém recebe aviso da própria ação, e só recebe quem tem e-mail e conta ativa.
- chamado novo          → funcionário escolhido
- encaminhado           → novo responsável
- comentário            → solicitante e responsável
- mudança de status     → solicitante (encerrado: com link para avaliar)
"""

from flask import current_app, render_template, url_for

from . import correio
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
        dados = dict(destino=u, c=c, frase=frase, citacao=_resumo(citacao), botao=botao, link=link)
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
