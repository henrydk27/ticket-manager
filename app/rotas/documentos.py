"""Documentos internos: todos consultam; administradores cadastram, trocam e apagam."""

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from .. import anexos as arquivos_disco
from .. import documentos
from ..anexos import TIPOS_EXIBIVEIS, AnexoInvalido, ler_anexos
from ..banco import db
from ..modelos import CATEGORIAS_DOCUMENTO
from ..seguranca import admin_obrigatorio, login_obrigatorio
from ..servicos import ErroValidacao

bp = Blueprint("documentos", __name__, url_prefix="/documentos")


def _obter(documento_id: int):
    doc = documentos.obter(db(), documento_id)
    if doc is None:
        abort(404)
    return doc


def _formulario(doc):
    """Cadastro (doc=None) e edição usam o mesmo formulário."""
    if request.method == "POST":
        try:
            arquivos = ler_anexos(request.files.getlist("arquivo"))[:1]
            salvo = documentos.salvar(db(), doc, request.form, arquivos[0] if arquivos else None, g.usuario)
        except (ErroValidacao, AnexoInvalido) as e:
            flash(str(e), "erro")
        else:
            flash(f"Documento “{salvo.titulo}” {'salvo' if doc else 'cadastrado'}.", "ok")
            return redirect(url_for("documentos.lista"))
        dados = request.form
    elif doc:
        dados = {"titulo": doc.titulo, "categoria": doc.categoria, "descricao": doc.descricao or ""}
    else:
        dados = {"categoria": request.args.get("categoria", "")}
    return render_template("documentos/documento.html", doc=doc, dados=dados, CATEGORIAS=CATEGORIAS_DOCUMENTO,
                           extensoes=",".join(sorted(documentos.EXTENSOES_DOCUMENTO)))


@bp.route("/")
@login_obrigatorio
def lista():
    texto = request.args.get("q", "").strip()[:100]
    categoria = request.args.get("categoria", "")
    categoria = categoria if categoria in CATEGORIAS_DOCUMENTO else ""
    return render_template("documentos/lista.html", itens=documentos.listar(db(), texto, categoria),
                           texto=texto, categoria=categoria, CATEGORIAS=CATEGORIAS_DOCUMENTO,
                           contagem=documentos.contagem_por_categoria(db()))


@bp.route("/novo", methods=["GET", "POST"])
@admin_obrigatorio
def novo():
    return _formulario(None)


@bp.route("/<int:documento_id>/editar", methods=["GET", "POST"])
@admin_obrigatorio
def editar(documento_id: int):
    return _formulario(_obter(documento_id))


@bp.route("/<int:documento_id>/apagar", methods=["POST"])
@admin_obrigatorio
def apagar(documento_id: int):
    doc = _obter(documento_id)
    documentos.apagar(db(), doc)
    flash(f"Documento “{doc.titulo}” apagado.", "ok")
    return redirect(url_for("documentos.lista"))


@bp.route("/<int:documento_id>/arquivo")
@login_obrigatorio
def arquivo(documento_id: int):
    doc = _obter(documento_id)
    ext = arquivos_disco.extensao(doc.nome)
    exibir = ext in TIPOS_EXIBIVEIS and request.args.get("baixar") is None
    try:
        return send_file(arquivos_disco.caminho(doc.arquivo),
                         mimetype=TIPOS_EXIBIVEIS.get(ext, "application/octet-stream"),
                         as_attachment=not exibir, download_name=doc.nome, max_age=0)
    except FileNotFoundError:
        abort(404)
