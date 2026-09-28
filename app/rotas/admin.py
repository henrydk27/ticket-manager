"""Painel e relatório (atendentes) e gestão de filas e usuários (administrador)."""

from datetime import date, datetime, timedelta

from flask import (Blueprint, abort, flash, g, make_response, redirect, render_template, request,
                   send_file, url_for)

from .. import exportacao, servicos
from ..banco import db
from ..modelos import Categoria, Usuario
from ..seguranca import admin_obrigatorio, atendente_obrigatorio

bp = Blueprint("admin", __name__)

PERIODOS = {30: "Últimos 30 dias", 90: "Últimos 90 dias", 365: "Últimos 12 meses"}


def _fila_do_filtro() -> tuple[list, int | None]:
    """Filas que o usuário pode consultar e a escolhida no filtro (?fila=ID), se permitida."""
    filas = servicos.filas_do_atendente(db(), g.usuario)
    escolhida = request.args.get("fila", "")
    if escolhida.isdigit() and int(escolhida) in {f.id for f in filas}:
        return filas, int(escolhida)
    return filas, None


@bp.route("/painel")
@atendente_obrigatorio
def painel():
    try:
        dias = int(request.args.get("dias", 30))
    except ValueError:
        dias = 30
    if dias not in PERIODOS:
        dias = 30
    filas, fila_id = _fila_do_filtro()
    return render_template("admin/painel.html", d=servicos.painel(db(), dias, g.usuario, fila_id),
                           dias=dias, PERIODOS=PERIODOS, filas=filas, fila_id=fila_id)


# ─── FILAS ──────────────────────────────────────────────────────────────────

@bp.route("/filas", methods=["GET", "POST"])
@admin_obrigatorio
def filas():
    if request.method == "POST":
        try:
            f = servicos.criar_fila(db(), request.form.get("nome", ""), request.form.get("descricao", ""))
        except servicos.ErroValidacao as e:
            flash(str(e), "erro")
        else:
            flash(f"Fila {f.nome} criada. Agora escolha os atendentes e os tipos de pedido.", "ok")
            return redirect(url_for("admin.fila", fila_id=f.id))
    return render_template("admin/filas.html", filas=servicos.listar_filas(db()),
                           abertos=servicos.contar_abertos_por_fila(db()))


def _fila(fila_id: int):
    f = servicos.obter_fila(db(), fila_id)
    if f is None:
        abort(404)
    return f


@bp.route("/filas/<int:fila_id>", methods=["GET", "POST"])
@admin_obrigatorio
def fila(fila_id: int):
    f = _fila(fila_id)
    if request.method == "POST":
        try:
            servicos.atualizar_fila(db(), f, request.form.get("nome", ""), request.form.get("descricao", ""),
                                    request.form.get("ativa") == "1")
        except servicos.ErroValidacao as e:
            flash(str(e), "erro")
        else:
            flash("Fila atualizada.", "ok")
        return redirect(url_for("admin.fila", fila_id=f.id))
    return render_template("admin/fila.html", f=f, usuarios=servicos.listar_usuarios_ativos(db()))


@bp.route("/filas/<int:fila_id>/atendentes", methods=["POST"])
@admin_obrigatorio
def fila_atendentes(fila_id: int):
    f = _fila(fila_id)
    ids = [int(i) for i in request.form.getlist("atendentes") if i.isdigit()]
    servicos.definir_atendentes(db(), f, ids)
    flash(f"Atendentes da fila {f.nome} atualizados.", "ok")
    return redirect(url_for("admin.fila", fila_id=f.id))


@bp.route("/filas/<int:fila_id>/categorias", methods=["POST"])
@admin_obrigatorio
def fila_categoria_nova(fila_id: int):
    f = _fila(fila_id)
    try:
        c = servicos.adicionar_categoria(db(), f, request.form.get("nome", ""))
        flash(f"Tipo de pedido {c.nome} adicionado.", "ok")
    except servicos.ErroValidacao as e:
        flash(str(e), "erro")
    return redirect(url_for("admin.fila", fila_id=f.id) + "#categorias")


@bp.route("/categorias/<int:categoria_id>/ativa", methods=["POST"])
@admin_obrigatorio
def categoria_ativa(categoria_id: int):
    c = db().get(Categoria, categoria_id)
    if c is None:
        abort(404)
    servicos.definir_categoria_ativa(db(), c, request.form.get("ativa") == "1")
    return redirect(url_for("admin.fila", fila_id=c.fila_id) + "#categorias")


# ─── USUÁRIOS ───────────────────────────────────────────────────────────────

@bp.route("/usuarios")
@admin_obrigatorio
def usuarios():
    return render_template("admin/usuarios.html", usuarios=servicos.listar_usuarios(db()),
                           senha_temporaria=None)


def _alvo(usuario_id: int) -> Usuario:
    u = db().get(Usuario, usuario_id)
    if u is None:
        abort(404)
    return u


@bp.route("/usuarios/<int:usuario_id>/papel", methods=["POST"])
@admin_obrigatorio
def usuario_papel(usuario_id: int):
    u = _alvo(usuario_id)
    try:
        servicos.definir_papel(db(), u, request.form.get("papel", ""))
        flash(f"{u.nome} agora é {u.papel_nome}.", "ok")
    except servicos.ErroValidacao as e:
        flash(str(e), "erro")
    return redirect(url_for("admin.usuarios"))


@bp.route("/usuarios/<int:usuario_id>/ativo", methods=["POST"])
@admin_obrigatorio
def usuario_ativo(usuario_id: int):
    u = _alvo(usuario_id)
    ativar = request.form.get("ativo") == "1"
    try:
        servicos.definir_ativo(db(), u, ativar)
        flash(f"Conta de {u.nome} {'reativada' if ativar else 'desativada'}.", "ok")
    except servicos.ErroValidacao as e:
        flash(str(e), "erro")
    return redirect(url_for("admin.usuarios"))


@bp.route("/usuarios/<int:usuario_id>/senha", methods=["POST"])
@admin_obrigatorio
def usuario_senha(usuario_id: int):
    u = _alvo(usuario_id)
    if u.id == g.usuario.id:
        flash("Para trocar a sua senha, use Minha conta.", "erro")
        return redirect(url_for("admin.usuarios"))
    temporaria = servicos.redefinir_senha(db(), u)
    # A senha temporária é mostrada uma única vez, nesta resposta (não vai para URL nem para log)
    resp = make_response(render_template("admin/usuarios.html", usuarios=servicos.listar_usuarios(db()),
                                         senha_temporaria=(u, temporaria)))
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ─── RELATÓRIO ──────────────────────────────────────────────────────────────

def _periodo() -> tuple[date, date] | None:
    try:
        ini = datetime.strptime(request.args.get("de", ""), "%Y-%m-%d").date()
        fim = datetime.strptime(request.args.get("ate", ""), "%Y-%m-%d").date()
    except ValueError:
        flash("Informe as datas inicial e final.", "erro")
        return None
    if fim < ini:
        flash("A data final não pode ser anterior à data inicial.", "erro")
        return None
    return ini, fim


@bp.route("/relatorio")
@atendente_obrigatorio
def relatorio():
    hoje = date.today()
    filas, fila_id = _fila_do_filtro()
    return render_template("admin/relatorio.html", filas=filas, fila_id=fila_id,
                           de=(hoje - timedelta(days=30)).isoformat(), ate=hoje.isoformat())


@bp.route("/relatorio/<formato>")
@atendente_obrigatorio
def relatorio_arquivo(formato: str):
    if formato not in ("excel", "pdf"):
        abort(404)
    periodo = _periodo()
    _filas, fila_id = _fila_do_filtro()
    if periodo is None:
        return redirect(url_for("admin.relatorio", fila=fila_id or ""))

    ini, fim = periodo
    chamados = servicos.chamados_por_periodo(db(), ini, fim, g.usuario, fila_id)
    if not chamados:
        flash("Nenhum chamado encontrado para o período informado.", "erro")
        return redirect(url_for("admin.relatorio", de=ini.isoformat(), ate=fim.isoformat(),
                                fila=fila_id or ""))

    nome = f"Chamados_{ini:%Y%m%d}_{fim:%Y%m%d}"
    if formato == "excel":
        return send_file(exportacao.gerar_excel(chamados), as_attachment=True,
                         download_name=nome + ".xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return send_file(exportacao.gerar_pdf(chamados, ini, fim), as_attachment=True,
                     download_name=nome + ".pdf", mimetype="application/pdf")
