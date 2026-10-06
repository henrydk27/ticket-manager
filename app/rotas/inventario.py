"""Telas do inventário de TI (só administradores)."""

import math
from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from .. import exportacao, inventario
from ..banco import db
from ..modelos import SETORES, SITUACOES, TIPOS_COMPUTADOR, TIPOS_EQUIPAMENTO
from ..seguranca import admin_obrigatorio, inventario_obrigatorio
from ..servicos import ErroValidacao

bp = Blueprint("inventario", __name__, url_prefix="/inventario")

CAMPOS_FORM = ["patrimonio", "tipo", "situacao", "setor", "usuario_id", "marca", "modelo", "numero_serie",
               "processador", "memoria", "armazenamento", "sistema_operacional", "hostname", "ip", "mac",
               "observacoes"]


def _filtros() -> inventario.Filtros:
    a = request.args
    try:
        pagina = max(1, int(a.get("pagina", 1)))
    except ValueError:
        pagina = 1
    situacao = a.get("situacao", "")
    setor = a.get("setor", "")
    return inventario.Filtros(
        texto=a.get("q", "").strip()[:100],
        tipo=a.get("tipo", "") if a.get("tipo") in TIPOS_EQUIPAMENTO else "",
        situacao=situacao if situacao in SITUACOES or situacao == "todas" else "",
        setor=setor if setor in SETORES or setor == "sem" else "",
        ordenar=a.get("ordenar", "patrimonio"),
        direcao="desc" if a.get("direcao") == "desc" else "asc",
        pagina=pagina,
    )


def _contexto_form(**extra):
    return dict(TIPOS=TIPOS_EQUIPAMENTO, TIPOS_COMPUTADOR=sorted(TIPOS_COMPUTADOR), SITUACOES=SITUACOES,
                usuarios=inventario.usuarios_para_atribuir(db()), **extra)


@bp.route("/")
@inventario_obrigatorio
def lista():
    f = _filtros()
    itens, total = inventario.listar(db(), f)
    base = {k: v for k, v in request.args.items() if k not in ("pagina", "ordenar", "direcao") and v}
    return render_template("inventario/lista.html", itens=itens, total=total, f=f, base=base,
                           paginas=max(1, math.ceil(total / f.por_pagina)),
                           contagem=inventario.contagem_por_situacao(db()),
                           TIPOS=TIPOS_EQUIPAMENTO, SITUACOES=SITUACOES)


@bp.route("/exportar")
@inventario_obrigatorio
def exportar():
    itens = inventario.todos(db(), _filtros())
    return send_file(exportacao.gerar_excel_inventario(itens), as_attachment=True,
                     download_name=f"Inventario_{date.today():%Y%m%d}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@bp.route("/novo", methods=["GET", "POST"])
@inventario_obrigatorio
def novo():
    if request.method == "POST":
        try:
            eq = inventario.salvar(db(), None, {c: request.form.get(c, "") for c in CAMPOS_FORM}, g.usuario)
        except ErroValidacao as e:
            flash(str(e), "erro")
        else:
            flash(f"Equipamento {eq.patrimonio} cadastrado.", "ok")
            return redirect(url_for("inventario.lista"))
    dados = request.form if request.method == "POST" else {"situacao": "Em estoque", "tipo": request.args.get("tipo", "")}
    return render_template("inventario/equipamento.html", eq=None, dados=dados, **_contexto_form())


@bp.route("/<int:equipamento_id>", methods=["GET", "POST"])
@inventario_obrigatorio
def equipamento(equipamento_id: int):
    eq = inventario.obter(db(), equipamento_id)
    if eq is None:
        abort(404)
    dados = None
    if request.method == "POST":
        try:
            inventario.salvar(db(), eq, {c: request.form.get(c, "") for c in CAMPOS_FORM}, g.usuario)
        except ErroValidacao as e:
            db().rollback()
            flash(str(e), "erro")
            dados = request.form
        else:
            flash(f"Equipamento {eq.patrimonio} salvo.", "ok")
            return redirect(url_for("inventario.lista"))
    if dados is None:
        dados = {c: getattr(eq, c) for c in CAMPOS_FORM if c != "usuario_id"} | {"usuario_id": eq.usuario_id}
        dados = {k: ("" if v is None else str(v)) for k, v in dados.items()}
    return render_template("inventario/equipamento.html", eq=eq, dados=dados, **_contexto_form())


@bp.route("/<int:equipamento_id>/apagar", methods=["POST"])
@admin_obrigatorio
def apagar(equipamento_id: int):
    eq = inventario.obter(db(), equipamento_id)
    if eq is None:
        abort(404)
    patrimonio = eq.patrimonio
    inventario.apagar(db(), eq)
    flash(f"Equipamento {patrimonio} apagado do inventário.", "ok")
    return redirect(url_for("inventario.lista"))
