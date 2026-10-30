"""Tarefas recorrentes da T.I: lista, cadastro, conclusão e histórico."""

from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import tarefas
from ..banco import db
from ..seguranca import admin_obrigatorio, preventiva_obrigatorio
from ..servicos import ErroValidacao

bp = Blueprint("tarefas", __name__, url_prefix="/tarefas")


def _obter(tarefa_id: int):
    t = tarefas.obter(db(), tarefa_id)
    if t is None:
        abort(404)
    return t


def _contexto(**extra):
    return dict(REPETICOES=tarefas.REPETICOES, DIAS_SEMANA=tarefas.DIAS_SEMANA, equipe=tarefas.equipe_ti(db()),
                descricao_repeticao=tarefas.descricao_repeticao, **extra)


@bp.route("/")
@preventiva_obrigatorio
def lista():
    estado = request.args.get("estado", "")
    estado = estado if estado in tarefas.ESTADOS else ""
    itens, contagem = tarefas.listar(db(), estado)
    return render_template("tarefas/lista.html", itens=itens, contagem=contagem, estado=estado,
                           ESTADOS=tarefas.ESTADOS, **_contexto())


def _formulario(t):
    if request.method == "POST":
        try:
            salvo = tarefas.salvar(db(), t, request.form, g.usuario)
        except ErroValidacao as e:
            db().rollback()
            flash(str(e), "erro")
        else:
            flash(f"Tarefa “{salvo.titulo}” {'salva' if t else 'cadastrada'}. "
                  f"Próxima: {salvo.proxima:%d/%m/%Y}." if salvo.proxima else "Tarefa salva.", "ok")
            return redirect(url_for("tarefas.lista"))
        dados = request.form
    elif t:
        dados = {"titulo": t.titulo, "descricao": t.descricao or "", "repeticao": t.repeticao,
                 "dia_mes": str(t.dia_mes or ""), "dia_semana": "" if t.dia_semana is None else str(t.dia_semana),
                 "intervalo_meses": str(t.intervalo_meses or ""), "inicio": t.inicio.isoformat(),
                 "avisar_dias": str(t.avisar_dias or 0), "responsavel_id": str(t.responsavel_id or "")}
    else:
        hoje = date.today()
        dados = {"repeticao": "mensal", "inicio": hoje.isoformat(), "dia_mes": str(hoje.day),
                 "avisar_dias": "0", "intervalo_meses": "3"}
    return render_template("tarefas/tarefa.html", t=t, dados=dados, **_contexto())


@bp.route("/nova", methods=["GET", "POST"])
@preventiva_obrigatorio
def nova():
    return _formulario(None)


@bp.route("/<int:tarefa_id>", methods=["GET", "POST"])
@preventiva_obrigatorio
def editar(tarefa_id: int):
    return _formulario(_obter(tarefa_id))


@bp.route("/<int:tarefa_id>/concluir", methods=["POST"])
@preventiva_obrigatorio
def concluir(tarefa_id: int):
    t = _obter(tarefa_id)
    try:
        tarefas.concluir(db(), t, g.usuario, request.form.get("observacao", ""))
    except ErroValidacao as e:
        flash(str(e), "erro")
    else:
        flash(f"Tarefa “{t.titulo}” concluída."
              + (f" Próxima: {t.proxima:%d/%m/%Y}." if t.proxima else ""), "ok")
    destino = request.form.get("voltar", "")
    return redirect(destino if destino.startswith("/tarefas") and not destino.startswith("//")
                    else url_for("tarefas.lista"))


@bp.route("/<int:tarefa_id>/apagar", methods=["POST"])
@admin_obrigatorio
def apagar(tarefa_id: int):
    t = _obter(tarefa_id)
    tarefas.apagar(db(), t)
    flash(f"Tarefa “{t.titulo}” apagada.", "ok")
    return redirect(url_for("tarefas.lista"))
