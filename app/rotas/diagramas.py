"""Diagramas da infraestrutura: admin e quem atende a T.I veem; admin cadastra, troca e apaga."""

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from .. import anexos as arquivos_disco
from .. import diagramas
from ..anexos import AnexoInvalido, ler_anexos
from ..banco import db
from ..seguranca import admin_obrigatorio, preventiva_obrigatorio
from ..servicos import ErroValidacao

bp = Blueprint("diagramas", __name__, url_prefix="/diagramas")


def _obter(diagrama_id: int):
    d = diagramas.obter(db(), diagrama_id)
    if d is None:
        abort(404)
    return d


def _um_arquivo(campo: str):
    arquivos = ler_anexos(request.files.getlist(campo),
                          diagramas.EXTENSOES_IMAGEM | diagramas.EXTENSOES_EDITAVEL | {".pdf"})
    return arquivos[0] if arquivos else None


def _formulario(d):
    if request.method == "POST":
        try:
            salvo = diagramas.salvar(db(), d, request.form, _um_arquivo("imagem"), _um_arquivo("editavel"),
                                     g.usuario, remover_editavel=request.form.get("remover_editavel") == "1")
        except (ErroValidacao, AnexoInvalido) as e:
            db().rollback()
            flash(str(e), "erro")
        else:
            flash(f"Diagrama “{salvo.titulo}” {'salvo' if d else 'cadastrado'}.", "ok")
            return redirect(url_for("diagramas.ver", diagrama_id=salvo.id))
        dados = request.form
    elif d:
        dados = {"titulo": d.titulo, "descricao": d.descricao or "", "ordem": str(d.ordem or 0)}
    else:
        dados = {"ordem": "0"}
    return render_template("diagramas/diagrama.html", d=d, dados=dados,
                           ext_imagem=",".join(sorted(diagramas.EXTENSOES_IMAGEM)),
                           ext_editavel=",".join(sorted(diagramas.EXTENSOES_EDITAVEL)))


@bp.route("/")
@preventiva_obrigatorio
def lista():
    return render_template("diagramas/lista.html", itens=diagramas.listar(db()))


@bp.route("/<int:diagrama_id>")
@preventiva_obrigatorio
def ver(diagrama_id: int):
    d = _obter(diagrama_id)
    return render_template("diagramas/ver.html", d=d, embutido=diagramas.editavel_embutido(d.nome))


@bp.route("/novo", methods=["GET", "POST"])
@admin_obrigatorio
def novo():
    return _formulario(None)


@bp.route("/<int:diagrama_id>/editar", methods=["GET", "POST"])
@admin_obrigatorio
def editar(diagrama_id: int):
    return _formulario(_obter(diagrama_id))


@bp.route("/<int:diagrama_id>/apagar", methods=["POST"])
@admin_obrigatorio
def apagar(diagrama_id: int):
    d = _obter(diagrama_id)
    diagramas.apagar(db(), d)
    flash(f"Diagrama “{d.titulo}” apagado.", "ok")
    return redirect(url_for("diagramas.lista"))


@bp.route("/<int:diagrama_id>/imagem")
@preventiva_obrigatorio
def imagem(diagrama_id: int):
    d = _obter(diagrama_id)
    ext = arquivos_disco.extensao(d.nome)
    baixar = request.args.get("baixar") is not None
    try:
        resp = send_file(arquivos_disco.caminho(d.arquivo), mimetype=diagramas.TIPOS_IMAGEM.get(ext, "application/octet-stream"),
                         as_attachment=baixar, download_name=d.nome, max_age=0)
    except FileNotFoundError:
        abort(404)
    # SVG enviado por alguém pode ter script: aberto direto no navegador, roda isolado e sem script
    resp.headers["Content-Security-Policy"] = ("default-src 'none'; img-src data:; style-src 'unsafe-inline'; "
                                               "font-src data:; sandbox")
    return resp


@bp.route("/<int:diagrama_id>/editavel")
@preventiva_obrigatorio
def editavel(diagrama_id: int):
    d = _obter(diagrama_id)
    if not d.editavel_arquivo:
        abort(404)
    try:
        return send_file(arquivos_disco.caminho(d.editavel_arquivo), mimetype="application/octet-stream",
                         as_attachment=True, download_name=d.editavel_nome, max_age=0)
    except FileNotFoundError:
        abort(404)
