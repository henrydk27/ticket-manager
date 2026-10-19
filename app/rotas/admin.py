"""Painel e relatório (quem atende) e gestão de usuários (administrador)."""

from datetime import date, datetime, timedelta

from flask import (Blueprint, abort, flash, g, redirect, render_template, request,
                   send_file, url_for)

from .. import exportacao, servicos
from ..banco import db
from ..modelos import PAPEIS, SETORES, Usuario
from ..seguranca import admin_obrigatorio, login_obrigatorio, supervisor_obrigatorio

bp = Blueprint("admin", __name__)

PERIODOS = {30: "Últimos 30 dias", 90: "Últimos 90 dias", 365: "Últimos 12 meses"}


def _setor_do_filtro() -> str | None:
    """Só o admin escolhe o setor (?setor=); quem atende vê sempre o próprio setor."""
    setor = request.args.get("setor", "")
    return setor if g.usuario.is_admin and setor in SETORES else None


@bp.route("/painel")
@login_obrigatorio
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

@bp.route("/usuarios")
@admin_obrigatorio
def usuarios():
    a = request.args
    f = servicos.FiltrosUsuarios(
        texto=a.get("q", "").strip()[:100],
        setor=a.get("setor", "") if a.get("setor") in SETORES else "",
        papel=a.get("papel", "") if a.get("papel") in PAPEIS else "",
        situacao=a.get("situacao", "") if a.get("situacao") in servicos.SITUACOES_CONTA else "",
    )
    filtrado = any((f.texto, f.setor, f.papel, f.situacao))
    return render_template("admin/usuarios.html", usuarios=servicos.listar_usuarios(db(), f), f=f,
                           filtrado=filtrado, contagem=servicos.contagem_de_contas(db()),
                           SITUACOES_CONTA=servicos.SITUACOES_CONTA,
                           pedidos=servicos.listar_usuarios(db(), servicos.FiltrosUsuarios(situacao="senha")))


def _alvo(usuario_id: int) -> Usuario:
    u = db().get(Usuario, usuario_id)
    if u is None:
        abort(404)
    return u


@bp.route("/usuarios/novo", methods=["GET", "POST"])
@admin_obrigatorio
def usuario_novo():
    """Cadastro pelo admin (ex.: para atribuir equipamentos a quem ainda não tem conta)."""
    f = request.form
    if request.method == "POST":
        try:
            u = servicos.cadastrar_pelo_admin(db(), f.get("nome", ""), f.get("login", ""), f.get("email", ""),
                                              f.get("setor", ""), f.get("atende") == "1", f.get("papel", ""))
        except servicos.ErroValidacao as e:
            flash(str(e), "erro")
        else:
            flash(f"Conta de {u.nome} criada. No primeiro acesso, a pessoa digita só o usuário "
                  f"\u201c{u.login}\u201d e clica em Entrar para criar a própria senha (prazo de 7 dias).", "ok")
            return redirect(url_for("admin.usuarios", _anchor=f"u{u.id}"))
    return render_template("admin/usuario.html", conta=None, form=f)


@bp.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@admin_obrigatorio
def usuario_editar(usuario_id: int):
    """Corrige nome, usuário, e-mail, setor, perfil e "atende chamados" de uma conta."""
    u = _alvo(usuario_id)
    if request.method == "POST":
        f = request.form
        try:
            servicos.editar_usuario(db(), u, g.usuario, f.get("nome", ""), f.get("login", ""),
                                    f.get("email", ""), f.get("setor", ""), f.get("atende") == "1",
                                    f.get("papel", ""))
        except servicos.ErroValidacao as e:
            db().rollback()
            flash(str(e), "erro")
            return render_template("admin/usuario.html", conta=u, form=f)
        flash(f"Dados de {u.nome} salvos.", "ok")
        return redirect(url_for("admin.usuarios", _anchor=f"u{u.id}"))
    form = {"nome": u.nome, "login": u.login, "email": u.email or "", "setor": u.setor,
            "papel": u.papel, "atende": "1" if u.atende else ""}
    return render_template("admin/usuario.html", conta=u, form=form)


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
    return redirect(url_for("admin.usuario_editar", usuario_id=u.id))


@bp.route("/usuarios/<int:usuario_id>/apagar", methods=["POST"])
@admin_obrigatorio
def usuario_apagar(usuario_id: int):
    u = _alvo(usuario_id)
    nome = u.nome
    try:
        servicos.apagar_usuario(db(), u, g.usuario)
    except servicos.ErroValidacao as e:
        flash(str(e), "erro")
        return redirect(url_for("admin.usuario_editar", usuario_id=u.id))
    flash(f"Conta de {nome} apagada.", "ok")
    return redirect(url_for("admin.usuarios"))


@bp.route("/usuarios/<int:usuario_id>/senha", methods=["POST"])
@admin_obrigatorio
def usuario_senha(usuario_id: int):
    """Libera uma nova senha: a atual deixa de valer e a pessoa cria outra no próximo acesso."""
    u = _alvo(usuario_id)
    if u.id == g.usuario.id:
        flash("Para trocar a sua senha, use Minha conta.", "erro")
        return redirect(url_for("admin.usuario_editar", usuario_id=u.id))
    servicos.liberar_nova_senha(db(), u)
    flash(f"Nova senha liberada para {u.nome}. No próximo acesso, a pessoa digita só o usuário "
          f"\u201c{u.login}\u201d e clica em Entrar para criar a senha (prazo de 7 dias).", "ok")
    return redirect(url_for("admin.usuario_editar", usuario_id=u.id))


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
@supervisor_obrigatorio
def relatorio():
    hoje = date.today()
    return render_template("admin/relatorio.html", setor=_setor_do_filtro(),
                           setores=list(servicos.atendentes_por_setor(db())),
                           de=(hoje - timedelta(days=30)).isoformat(), ate=hoje.isoformat())


@bp.route("/relatorio/<formato>")
@supervisor_obrigatorio
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
