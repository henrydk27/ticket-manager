"""Chamados: lista, abertura, detalhes, comentários, anexos, atendimento e avaliação."""

import json
import math

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from .. import anexos as arquivos_disco
from .. import notificacoes, servicos, sla
from ..anexos import TIPOS_EXIBIVEIS, AnexoInvalido, ler_anexos
from ..banco import db
from ..modelos import CATEGORIAS, MATRIZ_PRIORIDADE, Comentario, SETORES
from ..seguranca import admin_obrigatorio, login_obrigatorio

bp = Blueprint("chamados", __name__)

# Exemplos mostrados ao abrir o chamado, por categoria (o catálogo completo está em docs/SLA.md)
EXEMPLOS_PRIORIDADE = {
    "Incidente": [
        ("Alta", "Sem internet ou rede na empresa, sistema ou servidor fora do ar para um setor inteiro, "
                 "e-mail parado para todos, impressora do faturamento/expedição parada."),
        ("Média", "Meu computador não liga, sem acesso ao sistema só para mim, impressora do setor "
                  "com falha (dá para usar outra), lentidão que atrapalha o setor."),
        ("Baixa", "Mouse ou teclado com defeito, monitor com mancha, programa que trava às vezes, "
                  "lentidão leve só para mim."),
    ],
    "Solicitação": [
        ("Alta", "Acesso ou sistema que um setor inteiro precisa hoje para trabalhar, liberação urgente "
                 "com prazo (auditoria, fiscalização)."),
        ("Média", "Conta e acessos para funcionário que começa nos próximos dias, programa necessário "
                  "para o trabalho da semana, configurar impressora nova no setor."),
        ("Baixa", "Instalar um programa sem pressa, criar uma pasta, dúvida no Excel ou no e-mail, "
                  "assinatura de e-mail, troca de equipamento planejada."),
    ],
}


def _filtros_da_url() -> servicos.Filtros:
    a = request.args
    try:
        pagina = max(1, int(a.get("pagina", 1)))
    except ValueError:
        pagina = 1
    return servicos.Filtros(
        visao=a.get("visao", "") if a.get("visao") in servicos.VISOES else "",
        texto=a.get("q", "").strip()[:100],
        status=a.get("status", ""),
        setor=a.get("setor", "") if a.get("setor") in SETORES else "",
        categoria=a.get("categoria", "") if a.get("categoria") in CATEGORIAS else "",
        sla=a.get("sla", "") if a.get("sla") in servicos.FILTROS_SLA else "",
        ordenar=a.get("ordenar", "id"),
        direcao="asc" if a.get("direcao") == "asc" else "desc",
        pagina=pagina,
    )


def _chamado_visivel(chamado_id: int):
    c = servicos.obter_chamado(db(), chamado_id)
    if c is None:
        abort(404)
    if not g.usuario.pode_ver(c):
        abort(403)
    return c


def _chamado_atendido(chamado_id: int):
    """Chamado do setor que o usuário atende (ou admin)."""
    c = _chamado_visivel(chamado_id)
    if not g.usuario.trabalha_em(c):
        abort(403)
    return c


def _voltar(c, ancora: str = ""):
    return redirect(url_for("chamados.detalhe", chamado_id=c.id) + ancora)


def _voltar_para_lista(c):
    """Mudança feita na lista: volta para a mesma lista (filtros e página), na linha do chamado."""
    destino = request.form.get("voltar", "")
    if destino.startswith("/chamados") and not destino.startswith("//") and "\\" not in destino:
        return redirect(destino.split("#")[0] + f"#c{c.id}")
    return redirect(url_for("chamados.lista") + f"#c{c.id}")


@bp.route("/")
@login_obrigatorio
def inicio():
    return redirect(url_for("chamados.lista"))


@bp.route("/chamados")
@login_obrigatorio
def lista():
    f = _filtros_da_url()
    chamados, total = servicos.listar_chamados(db(), f, g.usuario)
    # Parâmetros atuais sem página/ordem, para montar links de ordenação e paginação
    base = {k: v for k, v in request.args.items() if k not in ("pagina", "ordenar", "direcao") and v}
    return render_template(
        "chamados/lista.html", chamados=chamados, total=total, f=f, base=base,
        paginas=max(1, math.ceil(total / f.por_pagina)), VISOES=servicos.VISOES,
        anexos=servicos.contar_anexos(db(), [c.id for c in chamados]),
        pendentes=len(servicos.avaliacoes_pendentes(db(), g.usuario)),
        relogio={c.id: sla.principal(c) for c in chamados}, FILTROS_SLA=servicos.FILTROS_SLA,
    )


@bp.route("/chamados/novo", methods=["GET", "POST"])
@login_obrigatorio
def novo():
    form = request.form
    if request.method == "POST":
        try:
            arquivos = ler_anexos(request.files.getlist("anexos"))
            c = servicos.criar_chamado(db(), g.usuario, form.get("setor_destino", ""),
                                       form.get("responsavel", ""), form.get("titulo", ""),
                                       form.get("descricao", ""), form.get("prioridade", ""), arquivos,
                                       form.get("categoria", ""),
                                       *((form.get("impacto", ""), form.get("urgencia", ""))
                                         if "prioridade" not in form else ()))
        except (servicos.ErroValidacao, AnexoInvalido) as e:
            flash(str(e), "erro")
        else:
            notificacoes.chamado_aberto(c)
            flash(f"Chamado #{c.id} enviado para {c.responsavel.nome} ({c.setor_destino}).", "ok")
            return _voltar(c)
    return render_template("chamados/novo.html", form=form,
                           por_setor=servicos.atendentes_por_setor(db()),
                           MATRIZ_JSON=json.dumps({f"{i}|{u}": p for (i, u), p in MATRIZ_PRIORIDADE.items()}),
                           EXEMPLOS_PRIORIDADE=EXEMPLOS_PRIORIDADE)


@bp.route("/chamados/<int:chamado_id>")
@login_obrigatorio
def detalhe(chamado_id: int):
    c = _chamado_visivel(chamado_id)
    trabalha = g.usuario.trabalha_em(c)
    return render_template(
        "chamados/detalhe.html", c=c, trabalha=trabalha,
        anexos_chamado=[a for a in c.anexos if a.comentario_id is None],
        relogios=sla.relogios(c),
        por_setor=servicos.atendentes_por_setor(db()) if trabalha else {},
    )


@bp.route("/chamados/<int:chamado_id>/comentarios/<int:comentario_id>/editar", methods=["POST"])
@admin_obrigatorio
def editar_comentario(chamado_id: int, comentario_id: int):
    c = _chamado_visivel(chamado_id)
    m = db().get(Comentario, comentario_id)
    if m is None or m.chamado_id != c.id:
        abort(404)
    try:
        if servicos.editar_comentario(db(), m, g.usuario, request.form.get("texto", "")):
            flash("Comentário editado.", "ok")
    except servicos.ErroValidacao as e:
        flash(str(e), "erro")
    return _voltar(c, f"#m{m.id}")


@bp.route("/chamados/<int:chamado_id>/comentar", methods=["POST"])
@login_obrigatorio
def comentar(chamado_id: int):
    c = _chamado_visivel(chamado_id)
    try:
        m = servicos.comentar(db(), c, g.usuario, request.form.get("texto", ""),
                              ler_anexos(request.files.getlist("anexos")))
    except (servicos.ErroValidacao, AnexoInvalido) as e:
        flash(str(e), "erro")
    else:
        notificacoes.comentario_novo(c, g.usuario, m)
    return _voltar(c, "#comentarios")


@bp.route("/chamados/<int:chamado_id>/status", methods=["POST"])
@login_obrigatorio
def alterar_status(chamado_id: int):
    c = _chamado_atendido(chamado_id)
    anterior = c.status
    try:
        if servicos.alterar_status(db(), c, request.form.get("status", ""), g.usuario):
            notificacoes.status_alterado(c, g.usuario, anterior)
            flash(f"Chamado #{c.id}: status alterado para {c.status}.", "ok")
    except servicos.ErroValidacao as e:
        flash(str(e), "erro")
    if request.form.get("voltar"):
        return _voltar_para_lista(c)
    return _voltar(c)


@bp.route("/chamados/<int:chamado_id>/categoria", methods=["POST"])
@login_obrigatorio
def classificar(chamado_id: int):
    c = _chamado_atendido(chamado_id)
    if not g.usuario.classifica_chamados:
        abort(403)
    try:
        if servicos.classificar(db(), c, request.form.get("categoria", ""), g.usuario):
            flash(f"Chamado #{c.id} classificado como {c.categoria}.", "ok")
    except servicos.ErroValidacao as e:
        flash(str(e), "erro")
    return _voltar(c)


@bp.route("/chamados/<int:chamado_id>/prioridade", methods=["POST"])
@login_obrigatorio
def repriorizar(chamado_id: int):
    c = _chamado_atendido(chamado_id)
    if not g.usuario.classifica_chamados:
        abort(403)
    try:
        if servicos.repriorizar(db(), c, request.form.get("prioridade", ""), g.usuario):
            flash(f"Chamado #{c.id}: prioridade {c.prioridade}" + (" (prazos do SLA recalculados)." if c.sla_inicio else "."),
                  "ok")
    except servicos.ErroValidacao as e:
        flash(str(e), "erro")
    return _voltar(c)


@bp.route("/chamados/<int:chamado_id>/assumir", methods=["POST"])
@login_obrigatorio
def assumir(chamado_id: int):
    c = _chamado_atendido(chamado_id)
    anterior = c.status
    try:
        servicos.assumir(db(), c, g.usuario)
        if c.status != anterior:
            notificacoes.status_alterado(c, g.usuario, anterior)
        flash("Você assumiu este chamado.", "ok")
    except servicos.ErroValidacao as e:
        flash(str(e), "erro")
    return _voltar(c)


@bp.route("/chamados/<int:chamado_id>/encaminhar", methods=["POST"])
@login_obrigatorio
def encaminhar(chamado_id: int):
    c = _chamado_atendido(chamado_id)
    try:
        mudou = servicos.encaminhar(db(), c, request.form.get("setor_destino", ""),
                                    request.form.get("responsavel", ""), g.usuario)
    except servicos.ErroValidacao as e:
        flash(str(e), "erro")
        return _voltar(c)
    if mudou:
        notificacoes.chamado_encaminhado(c, g.usuario)
        flash(f"Chamado #{c.id} agora está com {c.responsavel.nome} ({c.setor_destino}).", "ok")
    # Quem encaminhou para outro setor pode deixar de ver o chamado: aí volta para a lista
    return _voltar(c) if g.usuario.pode_ver(c) else redirect(url_for("chamados.lista"))


@bp.route("/chamados/<int:chamado_id>/apagar", methods=["POST"])
@admin_obrigatorio
def apagar(chamado_id: int):
    c = _chamado_visivel(chamado_id)
    servicos.apagar_chamado(db(), c)
    flash(f"Chamado #{chamado_id} apagado.", "ok")
    return redirect(url_for("chamados.lista"))


@bp.route("/anexos/<int:anexo_id>")
@login_obrigatorio
def baixar_anexo(anexo_id: int):
    a = servicos.obter_anexo(db(), anexo_id)
    if a is None:
        abort(404)
    _chamado_visivel(a.chamado_id)

    ext = arquivos_disco.extensao(a.nome)
    exibir = ext in TIPOS_EXIBIVEIS and request.args.get("baixar") is None
    try:
        return send_file(arquivos_disco.caminho(a.arquivo),
                         mimetype=TIPOS_EXIBIVEIS.get(ext, "application/octet-stream"),
                         as_attachment=not exibir, download_name=a.nome, max_age=0)
    except FileNotFoundError:
        abort(404)


@bp.route("/avaliacoes")
@login_obrigatorio
def avaliacoes():
    return render_template("chamados/avaliacoes.html",
                           pendentes=servicos.avaliacoes_pendentes(db(), g.usuario))


@bp.route("/chamados/<int:chamado_id>/avaliar", methods=["POST"])
@login_obrigatorio
def avaliar(chamado_id: int):
    c = servicos.obter_chamado(db(), chamado_id)
    if c is None:
        abort(404)
    try:
        if servicos.avaliar(db(), c, g.usuario, request.form.get("avaliacao", "")):
            flash(f"Chamado #{c.id} avaliado como {c.avaliacao}. Obrigado!", "ok")
        else:
            flash("Este chamado não pode ser avaliado.", "erro")
    except servicos.ErroValidacao:
        abort(400)
    if request.form.get("voltar") == "detalhe":
        return _voltar(c)
    if servicos.avaliacoes_pendentes(db(), g.usuario):
        return redirect(url_for("chamados.avaliacoes"))
    return redirect(url_for("chamados.lista"))
