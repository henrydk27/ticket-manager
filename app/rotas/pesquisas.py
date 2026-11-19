"""Pesquisa de satisfação da T.I: responder (quem não é da T.I) e resultados (só o administrador)."""

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from .. import correio, exportacao, pesquisas
from ..banco import db
from ..seguranca import admin_obrigatorio, login_obrigatorio
from ..servicos import ErroValidacao

bp = Blueprint("pesquisas", __name__)


@bp.route("/pesquisa", methods=["GET", "POST"])
@login_obrigatorio
def responder():
    p = pesquisas.aberta(db())
    pode = p is not None and pesquisas.participa(g.usuario)
    respondida = pode and pesquisas.ja_respondeu(db(), p, g.usuario)
    if request.method == "POST" and pode and not respondida:
        try:
            pesquisas.responder(db(), p, g.usuario, request.form)
        except ErroValidacao as e:
            flash(str(e), "erro")
        else:
            flash("Resposta enviada. Obrigado por ajudar a melhorar o atendimento da T.I!", "ok")
            return redirect(url_for("chamados.lista"))
    return render_template("pesquisas/responder.html", p=p, pode=pode, respondida=respondida,
                           RESOLVIDOS=pesquisas.RESOLVIDOS, dados=request.form,
                           dias=pesquisas.dias_restantes(p) if p else 0)


@bp.route("/pesquisas")
@admin_obrigatorio
def lista():
    itens = [(p, pesquisas.resultado(p)) for p in pesquisas.listar(db())]
    return render_template("pesquisas/lista.html", itens=itens, aberta=pesquisas.aberta(db()),
                           participantes=len(pesquisas.participantes(db())), MESES=pesquisas.MESES,
                           PRAZO=pesquisas.PRAZO_DIAS)


@bp.route("/pesquisas/abrir", methods=["POST"])
@admin_obrigatorio
def abrir():
    try:
        p = pesquisas.abrir(db(), g.usuario)
    except ErroValidacao as e:
        flash(str(e), "erro")
        return redirect(url_for("pesquisas.lista"))
    msgs = pesquisas.convidar(p, pesquisas.participantes(db()))
    for m in msgs:
        correio.enviar(m)
    flash(f"Pesquisa aberta até {p.encerra_em:%d/%m/%Y}. Convite enviado por e-mail a {len(msgs)} pessoa(s); "
          "quem não tem e-mail vê o aviso no sistema.", "ok")
    return redirect(url_for("pesquisas.resultado", pesquisa_id=p.id))


def _pesquisa(pesquisa_id: int):
    p = pesquisas.obter(db(), pesquisa_id)
    if p is None:
        abort(404)
    return p


@bp.route("/pesquisas/<int:pesquisa_id>")
@admin_obrigatorio
def resultado(pesquisa_id: int):
    p = _pesquisa(pesquisa_id)
    anteriores = [x for x in pesquisas.listar(db()) if x.aberta_em < p.aberta_em]
    anterior = pesquisas.resultado(anteriores[0]) if anteriores else None
    return render_template("pesquisas/resultado.html", p=p, r=pesquisas.resultado(p), anterior=anterior,
                           dias=pesquisas.dias_restantes(p), RESOLVIDOS=pesquisas.RESOLVIDOS)


@bp.route("/pesquisas/<int:pesquisa_id>/encerrar", methods=["POST"])
@admin_obrigatorio
def encerrar(pesquisa_id: int):
    p = _pesquisa(pesquisa_id)
    pesquisas.encerrar(db(), p)
    flash("Pesquisa encerrada.", "ok")
    return redirect(url_for("pesquisas.resultado", pesquisa_id=p.id))


@bp.route("/pesquisas/<int:pesquisa_id>/excel")
@admin_obrigatorio
def excel(pesquisa_id: int):
    p = _pesquisa(pesquisa_id)
    return send_file(exportacao.gerar_excel_pesquisa(p, pesquisas.resultado(p)), as_attachment=True,
                     download_name=f"pesquisa-{p.aberta_em:%Y-%m}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@bp.route("/pesquisas/<int:pesquisa_id>/pdf")
@admin_obrigatorio
def pdf(pesquisa_id: int):
    p = _pesquisa(pesquisa_id)
    return send_file(exportacao.gerar_pdf_pesquisa(p, pesquisas.resultado(p)), as_attachment=True,
                     download_name=f"pesquisa-{p.aberta_em:%Y-%m}.pdf", mimetype="application/pdf")
