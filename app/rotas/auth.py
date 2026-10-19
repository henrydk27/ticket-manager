"""Login, criação de conta e logout."""

from urllib.parse import urlparse

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template, request,
                   session, url_for)
from sqlalchemy import select

from .. import notificacoes, servicos
from ..banco import db
from ..modelos import Usuario
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
        conta = db().scalar(select(Usuario).where(Usuario.login == servicos.normalizar_login(login_digitado)))

        if conta is not None and conta.pode_criar_senha:
            # Cadastrada pelo admin ou senha liberada: vai criar a senha (não há senha para conferir)
            session.clear()
            session["criar_senha"] = conta.id
            return redirect(url_for("auth.criar_senha", proximo=request.form.get("proximo") or None))
        if conta is not None and conta.ativo and conta.prazo_senha_vencido:
            flash("O prazo para criar sua senha venceu. Clique em \u201cSolicitar nova senha\u201d.", "erro")
        elif not login_digitado or not senha:
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


@bp.route("/criar-senha", methods=["GET", "POST"])
def criar_senha():
    """Primeiro acesso (conta cadastrada pelo admin) ou nova senha liberada pelo CPD."""
    uid = session.get("criar_senha")
    u = db().get(Usuario, uid) if uid else None
    if u is None or not u.pode_criar_senha:
        session.pop("criar_senha", None)
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        f = request.form
        if f.get("nova", "") != f.get("confirmar", ""):
            flash("As senhas não conferem.", "erro")
        else:
            try:
                servicos.criar_senha(db(), u, f.get("nova", ""))
            except servicos.ErroValidacao as e:
                flash(str(e), "erro")
            else:
                flash("Senha criada. Bem-vindo!", "ok")
                destino = _entrar(u)
                return redirect(destino or _destino_seguro(f.get("proximo")))
    return render_template("criar_senha.html", conta=u, proximo=request.values.get("proximo", ""))


@bp.route("/solicitar-senha", methods=["GET", "POST"])
def solicitar_senha():
    if g.usuario is not None:
        return redirect(url_for("conta.senha"))
    if request.method == "POST":
        u = servicos.solicitar_nova_senha(db(), request.form.get("identificacao", ""))
        if u is not None:
            notificacoes.pedido_nova_senha(u)
        # Mesma resposta para qualquer caso (não revela quais usuários existem)
        flash("Pedido enviado ao CPD. Quando a nova senha for liberada, entre digitando só o seu "
              "usuário e clique em Entrar para criar a senha.", "ok")
        return redirect(url_for("auth.login"))
    return render_template("solicitar_senha.html")


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
                    notificacoes.conta_criada(u)
                _entrar(u)
                return redirect(url_for("chamados.lista"))

    return render_template("cadastro.html", form=form)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
