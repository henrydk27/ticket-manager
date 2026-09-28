"""Login, criação de conta e logout."""

from urllib.parse import urlparse

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template, request,
                   session, url_for)

from .. import servicos
from ..banco import db
from ..seguranca import chave_tentativa, iniciar_sessao

bp = Blueprint("auth", __name__)


def _destino_seguro(proximo: str | None) -> str:
    # Só aceita caminhos internos (evita redirecionar para outro site)
    if proximo and proximo.startswith("/") and not proximo.startswith("//") and not urlparse(proximo).netloc:
        return proximo
    return url_for("chamados.lista")


def _entrar(u) -> str:
    iniciar_sessao(u)
    servicos.registrar_acesso(db(), u)
    if u.trocar_senha:
        return url_for("conta.senha")
    if servicos.avaliacoes_pendentes(db(), u):
        return url_for("chamados.avaliacoes")
    return ""


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.usuario is not None:
        return redirect(url_for("chamados.lista"))

    login_digitado = ""
    if request.method == "POST":
        login_digitado = request.form.get("login", "").strip()
        senha = request.form.get("senha", "")
        chave = chave_tentativa(login_digitado)

        if not login_digitado or not senha:
            flash("Preencha usuário e senha.", "erro")
        elif (espera := servicos.segundos_bloqueado(db(), chave)):
            flash(f"Muitas tentativas. Tente de novo em {espera // 60 + 1} minuto(s).", "erro")
        else:
            u = servicos.autenticar(db(), login_digitado, senha)
            if u is None:
                servicos.registrar_falha(db(), chave)
                flash("Usuário ou senha inválidos.", "erro")
            elif not u.ativo:
                flash("Sua conta está desativada. Fale com o administrador.", "erro")
            else:
                servicos.limpar_falhas(db(), chave)
                destino = _entrar(u)
                return redirect(destino or _destino_seguro(request.form.get("proximo")))

    return render_template("login.html", login=login_digitado,
                           proximo=request.values.get("proximo", ""),
                           cadastro_aberto=current_app.config["CADASTRO_ABERTO"])


@bp.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if not current_app.config["CADASTRO_ABERTO"]:
        abort(404)
    if g.usuario is not None:
        return redirect(url_for("chamados.lista"))

    form = request.form
    if request.method == "POST":
        if form.get("senha", "") != form.get("confirmar", ""):
            flash("As senhas não conferem.", "erro")
        else:
            try:
                u = servicos.criar_conta(db(), form.get("nome", ""), form.get("login", ""),
                                         form.get("email", ""), form.get("setor", ""),
                                         form.get("senha", ""))
            except servicos.ErroValidacao as e:
                flash(str(e), "erro")
            else:
                if u.is_admin:
                    flash("Conta criada. Por ser a primeira, ela é a de administrador.", "ok")
                else:
                    flash("Conta criada. Bem-vindo!", "ok")
                _entrar(u)
                return redirect(url_for("chamados.lista"))

    return render_template("cadastro.html", form=form)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
