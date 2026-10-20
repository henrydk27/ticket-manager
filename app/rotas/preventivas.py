"""Revisão preventiva: lista de vencimentos, registro com checklist, planos por tipo e relatório."""

from datetime import date, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from .. import anexos as arquivos_disco
from .. import exportacao, inventario, notificacoes, preventivas
from ..anexos import TIPOS_EXIBIVEIS, AnexoInvalido, ler_anexos
from ..banco import db
from ..modelos import RESULTADOS_ITEM, SETORES, TIPOS_EQUIPAMENTO
from ..seguranca import admin_obrigatorio, preventiva_obrigatorio
from ..servicos import ErroValidacao

bp = Blueprint("preventivas", __name__, url_prefix="/preventivas")


@bp.route("/")
@preventiva_obrigatorio
def lista():
    a = request.args
    f = preventivas.Filtros(
        texto=a.get("q", "").strip()[:100],
        setor=a.get("setor", "") if a.get("setor") in SETORES else "",
        tipo=a.get("tipo", "") if a.get("tipo") in TIPOS_EQUIPAMENTO else "",
        estado=a.get("estado", "") if a.get("estado") in preventivas.ESTADOS else "",
    )
    itens, contagem = preventivas.listar(db(), f)
    hoje = date.today()
    return render_template("preventivas/lista.html", itens=itens, contagem=contagem, f=f,
                           filtrado=any((f.texto, f.setor, f.tipo, f.estado)), ESTADOS=preventivas.ESTADOS,
                           TIPOS=TIPOS_EQUIPAMENTO, de=hoje.replace(day=1).isoformat(), ate=hoje.isoformat())


def _voltar_seguro(destino: str) -> str:
    """Só volta para telas internas de preventivas ou do inventário."""
    if destino.startswith(("/preventivas", "/inventario")) and not destino.startswith("//") and "\\" not in destino:
        return destino
    return ""


def _equipamento(equipamento_id: int):
    eq = inventario.obter(db(), equipamento_id)
    if eq is None:
        abort(404)
    return eq


@bp.route("/equipamento/<int:equipamento_id>", methods=["GET", "POST"])
@preventiva_obrigatorio
def registrar(equipamento_id: int):
    eq = _equipamento(equipamento_id)
    plano = preventivas.planos(db()).get(eq.tipo)
    form = request.form
    if request.method == "POST":
        itens = plano.itens if plano else []
        resultados = {item: form.get(f"r{i}", "") for i, item in enumerate(itens)}
        notas = {item: form.get(f"n{i}", "") for i, item in enumerate(itens)}
        try:
            arquivos = ler_anexos(request.files.getlist("anexo"))[:1]
            reg = preventivas.registrar(db(), eq, g.usuario, form.get("data", ""), resultados, notas,
                                        form.get("pecas", ""), form.get("observacoes", ""),
                                        arquivos[0] if arquivos else None)
        except (ErroValidacao, AnexoInvalido) as e:
            db().rollback()
            flash(str(e), "erro")
        else:
            flash(f"Preventiva do patrimônio {eq.patrimonio} registrada.", "ok")
            if reg.chamado is not None:
                notificacoes.chamado_aberto(reg.chamado)
                flash(f"Itens com problema: chamado #{reg.chamado.id} aberto para a T.I.", "info")
            elif reg.sem_atendente:
                flash("Itens com problema, mas ninguém atende a T.I para receber o chamado. "
                      "Abra o chamado manualmente.", "erro")
            destino = _voltar_seguro(request.form.get("voltar", ""))
            return redirect(destino or url_for("preventivas.lista"))
    return render_template("preventivas/registrar.html", eq=eq, plano=plano, form=form,
                           RESULTADOS=RESULTADOS_ITEM, hoje=date.today().isoformat(),
                           prev=preventivas.situacao(eq, preventivas.planos(db())),
                           voltar=_voltar_seguro(request.args.get("voltar", "") or request.form.get("voltar", "")))


@bp.route("/<int:preventiva_id>/anexo")
@preventiva_obrigatorio
def anexo(preventiva_id: int):
    p = preventivas.obter(db(), preventiva_id)
    if p is None or not p.anexo_arquivo:
        abort(404)
    ext = arquivos_disco.extensao(p.anexo_nome or "")
    exibir = ext in TIPOS_EXIBIVEIS and request.args.get("baixar") is None
    try:
        return send_file(arquivos_disco.caminho(p.anexo_arquivo),
                         mimetype=TIPOS_EXIBIVEIS.get(ext, "application/octet-stream"),
                         as_attachment=not exibir, download_name=p.anexo_nome, max_age=0)
    except FileNotFoundError:
        abort(404)


@bp.route("/planos", methods=["GET", "POST"])
@admin_obrigatorio
def planos():
    if request.method == "POST":
        f = request.form
        dados = {t: (f.get(f"meses_{i}", "0"), f.get(f"itens_{i}", "")) for i, t in enumerate(TIPOS_EQUIPAMENTO)}
        try:
            preventivas.salvar_planos(db(), dados)
        except ErroValidacao as e:
            db().rollback()
            flash(f"Nada foi salvo: {e}", "erro")
        else:
            flash("Planos de preventiva salvos.", "ok")
            return redirect(url_for("preventivas.planos"))
    return render_template("preventivas/planos.html", planos=preventivas.planos(db()), TIPOS=TIPOS_EQUIPAMENTO)


@bp.route("/relatorio")
@preventiva_obrigatorio
def relatorio():
    try:
        ini = date.fromisoformat(request.args.get("de", ""))
        fim = date.fromisoformat(request.args.get("ate", ""))
    except ValueError:
        flash("Informe as datas inicial e final do relatório.", "erro")
        return redirect(url_for("preventivas.lista"))
    if fim < ini:
        flash("A data final não pode ser anterior à inicial.", "erro")
        return redirect(url_for("preventivas.lista"))
    if (fim - ini) > timedelta(days=3660):
        flash("Escolha um período de até 10 anos.", "erro")
        return redirect(url_for("preventivas.lista"))
    return send_file(exportacao.gerar_excel_preventivas(preventivas.no_periodo(db(), ini, fim)), as_attachment=True,
                     download_name=f"Preventivas_{ini:%Y%m%d}_{fim:%Y%m%d}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
