"""Minha conta: dados pessoais e troca de senha."""

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import servicos
from ..banco import db
from ..seguranca import login_obrigatorio

bp = Blueprint("conta", __name__, url_prefix="/conta")


@bp.route("/", methods=["GET", "POST"])
@login_obrigatorio
def perfil():
    if request.method == "POST":
        f = request.form
        try:
            servicos.atualizar_perfil(db(), g.usuario, f.get("nome", ""), f.get("email", ""),
                                      f.get("setor", ""))
        except servicos.ErroValidacao as e:
            flash(str(e), "erro")
        else:
            flash("Dados atualizados.", "ok")
        return redirect(url_for("conta.perfil"))
    return render_template("conta/perfil.html")


@bp.route("/senha", methods=["GET", "POST"])
@login_obrigatorio
def senha():
    obrigatoria = g.usuario.trocar_senha
    if request.method == "POST":
        f = request.form
        if f.get("nova", "") != f.get("confirmar", ""):
            flash("As senhas não conferem.", "erro")
        else:
            try:
                servicos.alterar_senha(db(), g.usuario, None if obrigatoria else f.get("atual", ""),
                                       f.get("nova", ""))
            except servicos.ErroValidacao as e:
                flash(str(e), "erro")
            else:
                flash("Senha alterada.", "ok")
                return redirect(url_for("chamados.lista"))
    return render_template("conta/senha.html", obrigatoria=obrigatoria)
