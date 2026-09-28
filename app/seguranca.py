"""Sessão do usuário, controle de acesso e proteção CSRF."""

import secrets
from functools import wraps

from flask import abort, flash, g, redirect, request, session, url_for

from .banco import db
from .modelos import Usuario

# Rotas liberadas enquanto o usuário precisa trocar a senha temporária
_LIBERADAS_TROCA_SENHA = {"conta.senha", "auth.logout", "static"}


def iniciar_sessao(u: Usuario) -> None:
    session.clear()
    session.permanent = True
    session["uid"] = u.id


def carregar_usuario() -> None:
    """Lê o usuário do banco a cada requisição: desativar ou mudar o papel vale na hora."""
    g.usuario = None
    uid = session.get("uid")
    if uid is None:
        return
    u = db().get(Usuario, uid)
    if u is None or not u.ativo:
        session.clear()
        return
    g.usuario = u


def exigir_troca_de_senha():
    if g.usuario is not None and g.usuario.trocar_senha and request.endpoint not in _LIBERADAS_TROCA_SENHA:
        return redirect(url_for("conta.senha"))
    return None


_LIBERADAS_SEM_EMAIL = {"conta.perfil", "conta.senha", "auth.logout", "static"}


def exigir_email():
    """Contas antigas sem e-mail precisam cadastrar um (os avisos chegam por e-mail)."""
    if g.usuario is not None and not g.usuario.email and request.endpoint not in _LIBERADAS_SEM_EMAIL:
        flash("Informe seu e-mail para continuar: é por ele que chegam os avisos dos chamados.", "info")
        return redirect(url_for("conta.perfil"))
    return None


def login_obrigatorio(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.usuario is None:
            return redirect(url_for("auth.login", proximo=request.full_path))
        return view(*args, **kwargs)
    return wrapper


def atendente_obrigatorio(view):
    """Quem atende chamados do seu setor e administradores."""
    @wraps(view)
    @login_obrigatorio
    def wrapper(*args, **kwargs):
        if not g.usuario.is_atendente:
            abort(403)
        return view(*args, **kwargs)
    return wrapper


def admin_obrigatorio(view):
    @wraps(view)
    @login_obrigatorio
    def wrapper(*args, **kwargs):
        if not g.usuario.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapper


# ─── CSRF ───────────────────────────────────────────────────────────────────

def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def verificar_csrf() -> None:
    if request.method != "POST":
        return
    enviado = request.form.get("csrf") or request.headers.get("X-CSRF-Token", "")
    if not enviado or not secrets.compare_digest(enviado, session.get("csrf", "")):
        flash("Sua sessão expirou. Tente novamente.", "erro")
        abort(400)


def chave_tentativa(login: str) -> str:
    return f"{request.remote_addr}|{(login or '').strip().lower()}"
