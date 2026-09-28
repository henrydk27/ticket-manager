"""Painel e relatório (quem atende) e gestão de usuários (administrador)."""

from datetime import date, datetime, timedelta

from flask import (Blueprint, abort, flash, g, make_response, redirect, render_template, request,
                   send_file, url_for)

from .. import exportacao, servicos
from ..banco import db
from ..modelos import SETORES, Usuario
from ..seguranca import admin_obrigatorio, atendente_obrigatorio

bp = Blueprint("admin", __name__)

PERIODOS = {30: "Últimos 30 dias", 90: "Últimos 90 dias", 365: "Últimos 12 meses"}


def _setor_do_filtro() -> str | None:
    """Só o admin escolhe o setor (?setor=); quem atende vê sempre o próprio setor."""
    setor = request.args.get("setor", "")
    return setor if g.usuario.is_admin and setor in SETORES else None


@bp.route("/painel")
@atendente_obrigatorio
def painel():
    try:
        dias = int(request.args.get("dias", 30))
    except ValueError:
        dias = 30
    if dias not in PERIODOS:
        dias = 30
    setor = _setor_do_filtro()
    return render_template("admin/painel.html", d=servicos.painel(db(), dias, g.usuario, setor),
                           dias=dias, PERIODOS=PERIODOS, setor=setor,
                           setores=list(servicos.atendentes_por_setor(db())))


# ─── USUÁRIOS ───────────────────────────────────────────────────────────────

def _pagina_usuarios(senha_temporaria=None):
    return render_template("admin/usuarios.html", usuarios=servicos.listar_usuarios(db()),
                           senha_temporaria=senha_temporaria)


@bp.route("/usuarios")
@admin_obrigatorio
def usuarios():
    return _pagina_usuarios()


def _alvo(usuario_id: int) -> Usuario:
    u = db().get(Usuario, usuario_id)
    if u is None:
        abort(404)
    return u


@bp.route("/usuarios/<int:usuario_id>", methods=["POST"])
@admin_obrigatorio
def usuario_salvar(usuario_id: int):
    u = _alvo(usuario_id)
    f = request.form
    papel = f.get("papel", u.papel) if u.id != g.usuario.id else u.papel  # ninguém rebaixa a si mesmo
    try:
        servicos.atualizar_usuario(db(), u, f.get("setor", ""), f.get("atende") == "1", papel)
        flash(f"Dados de {u.nome} salvos.", "ok")
    except servicos.ErroValidacao as e:
        flash(str(e), "erro")
    return redirect(url_for("admin.usuarios") + f"#u{u.id}")


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
    resp = make_response(_pagina_usuarios((u, temporaria)))
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
    return render_template("admin/relatorio.html", setor=_setor_do_filtro(),
                           setores=list(servicos.atendentes_por_setor(db())),
                           de=(hoje - timedelta(days=30)).isoformat(), ate=hoje.isoformat())


@bp.route("/relatorio/<formato>")
@atendente_obrigatorio
def relatorio_arquivo(formato: str):
    if formato not in ("excel", "pdf"):
        abort(404)
    periodo = _periodo()
    setor = _setor_do_filtro()
    if periodo is None:
        return redirect(url_for("admin.relatorio", setor=setor or ""))

    ini, fim = periodo
    chamados = servicos.chamados_por_periodo(db(), ini, fim, g.usuario, setor)
    if not chamados:
        flash("Nenhum chamado encontrado para o período informado.", "erro")
        return redirect(url_for("admin.relatorio", de=ini.isoformat(), ate=fim.isoformat(),
                                setor=setor or ""))

    nome = f"Chamados_{ini:%Y%m%d}_{fim:%Y%m%d}"
    if formato == "excel":
        return send_file(exportacao.gerar_excel(chamados), as_attachment=True,
                         download_name=nome + ".xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return send_file(exportacao.gerar_pdf(chamados, ini, fim), as_attachment=True,
                     download_name=nome + ".pdf", mimetype="application/pdf")
