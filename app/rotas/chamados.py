"""Chamados: lista com filtros, abertura, detalhes, comentários, anexos e avaliação."""

import math
from datetime import date, datetime

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from .. import anexos as arquivos_disco
from .. import servicos
from ..anexos import TIPOS_EXIBIVEIS, AnexoInvalido, ler_anexos
from ..banco import db
from ..modelos import Usuario
from ..seguranca import login_obrigatorio, tecnico_obrigatorio

bp = Blueprint("chamados", __name__)


def _data(texto: str | None) -> date | None:
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date() if texto else None
    except ValueError:
        return None


def _filtros_da_url() -> servicos.Filtros:
    a = request.args
    try:
        pagina = max(1, int(a.get("pagina", 1)))
    except ValueError:
        pagina = 1
    return servicos.Filtros(
        texto=a.get("q", "").strip()[:100],
        status=a.get("status", ""),
        setor=a.get("setor", ""),
        prioridade=a.get("prioridade", ""),
        responsavel=a.get("responsavel", "") if g.usuario.is_tecnico else "",
        de=_data(a.get("de")),
        ate=_data(a.get("ate")),
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


def _voltar(c, ancora: str = ""):
    return redirect(url_for("chamados.detalhe", chamado_id=c.id) + ancora)


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
        paginas=max(1, math.ceil(total / f.por_pagina)),
        anexos=servicos.contar_anexos(db(), [c.id for c in chamados]),
        tecnicos=servicos.listar_tecnicos(db()) if g.usuario.is_tecnico else [],
        pendentes=len(servicos.avaliacoes_pendentes(db(), g.usuario)),
    )


@bp.route("/chamados/novo", methods=["GET", "POST"])
@login_obrigatorio
def novo():
    form = request.form
    if request.method == "POST":
        try:
            arquivos = ler_anexos(request.files.getlist("anexos"))
            c = servicos.criar_chamado(db(), g.usuario, form.get("titulo", ""),
                                       form.get("descricao", ""), form.get("prioridade", ""),
                                       form.get("setor", ""), arquivos)
        except (servicos.ErroValidacao, AnexoInvalido) as e:
            flash(str(e), "erro")
        else:
            flash(f"Chamado #{c.id} aberto.", "ok")
            return _voltar(c)
    return render_template("chamados/novo.html", form=form)


@bp.route("/chamados/<int:chamado_id>")
@login_obrigatorio
def detalhe(chamado_id: int):
    c = _chamado_visivel(chamado_id)
    return render_template(
        "chamados/detalhe.html", c=c,
        anexos_chamado=[a for a in c.anexos if a.comentario_id is None],
        tecnicos=servicos.listar_tecnicos(db()) if g.usuario.is_tecnico else [],
    )


@bp.route("/chamados/<int:chamado_id>/comentar", methods=["POST"])
@login_obrigatorio
def comentar(chamado_id: int):
    c = _chamado_visivel(chamado_id)
    try:
        servicos.comentar(db(), c, g.usuario, request.form.get("texto", ""),
                          ler_anexos(request.files.getlist("anexos")))
    except (servicos.ErroValidacao, AnexoInvalido) as e:
        flash(str(e), "erro")
    return _voltar(c, "#comentarios")


@bp.route("/chamados/<int:chamado_id>/status", methods=["POST"])
@tecnico_obrigatorio
def alterar_status(chamado_id: int):
    c = _chamado_visivel(chamado_id)
    try:
        if servicos.alterar_status(db(), c, request.form.get("status", ""), g.usuario):
            flash(f"Status alterado para {c.status}.", "ok")
    except servicos.ErroValidacao as e:
        flash(str(e), "erro")
    return _voltar(c)


@bp.route("/chamados/<int:chamado_id>/responsavel", methods=["POST"])
@tecnico_obrigatorio
def atribuir(chamado_id: int):
    c = _chamado_visivel(chamado_id)
    escolhido = request.form.get("responsavel", "")
    responsavel = db().get(Usuario, int(escolhido)) if escolhido.isdigit() else None
    if escolhido and responsavel is None:
        abort(400)
    try:
        if servicos.atribuir(db(), c, responsavel, g.usuario):
            flash(f"Chamado atribuído a {responsavel.nome}." if responsavel else "Responsável removido.", "ok")
    except servicos.ErroValidacao as e:
        flash(str(e), "erro")
    return _voltar(c)


@bp.route("/chamados/<int:chamado_id>/assumir", methods=["POST"])
@tecnico_obrigatorio
def assumir(chamado_id: int):
    c = _chamado_visivel(chamado_id)
    servicos.assumir(db(), c, g.usuario)
    flash("Você assumiu este chamado.", "ok")
    return _voltar(c)


@bp.route("/chamados/<int:chamado_id>/apagar", methods=["POST"])
@tecnico_obrigatorio
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
