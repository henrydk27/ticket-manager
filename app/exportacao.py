"""Relatório de chamados em Excel (openpyxl) e PDF (reportlab), gerados em memória."""

import io
from datetime import date, datetime
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import formatos, sla
from .modelos import IMPACTOS, URGENCIAS

# (cabeçalho, valor, largura Excel em caracteres, largura PDF em mm; 0 = só no Excel)
COLUNAS = [
    ("Nº", lambda c: c.id, 8, 13),
    ("Título", lambda c: c.titulo, 40, 38),
    ("Para o setor", lambda c: c.setor_destino, 16, 24),
    ("Status", lambda c: c.status, 18, 24),
    ("Prioridade", lambda c: c.prioridade, 11, 19),
    ("Categoria", lambda c: c.categoria or "", 12, 18),
    ("Setor de origem", lambda c: c.setor, 16, 22),
    ("Solicitante", lambda c: c.solicitante.nome, 22, 22),
    ("Responsável", lambda c: c.responsavel.nome if c.responsavel else "", 22, 22),
    ("Abertura", lambda c: formatos.data(c.aberto_em), 12, 19),
    ("Fechamento", lambda c: formatos.data(c.fechado_em), 12, 21),
    ("Avaliação", lambda c: c.avaliacao or "", 11, 19),
    ("Quem é afetado", lambda c: IMPACTOS.get(c.impacto or "", ""), 22, 0),
    ("Quanto atrapalha", lambda c: URGENCIAS.get(c.urgencia or "", ""), 26, 0),
    ("Meta 1º atendimento", lambda c: sla.texto_meta(c.sla_atendimento_min) if c.sla_inicio else "", 14, 0),
    ("SLA 1º atendimento", lambda c: sla.rotulo(sla.relogio_atendimento(c)), 16, 0),
    ("Meta solução", lambda c: sla.texto_meta(c.sla_solucao_min) if c.sla_inicio else "", 12, 0),
    ("SLA solução", lambda c: sla.rotulo(sla.relogio_solucao(c)), 16, 16),
]
COLUNAS_PDF = [x for x in COLUNAS if x[3]]
AZUL = "1F3A5F"


def gerar_excel(chamados: list) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Chamados"
    fundo, fonte = PatternFill("solid", fgColor=AZUL), Font(bold=True, color="FFFFFF")
    for col, (titulo, _c, largura, _p) in enumerate(COLUNAS, start=1):
        cel = ws.cell(row=1, column=col, value=titulo)
        cel.fill, cel.font = fundo, fonte
        ws.column_dimensions[cel.column_letter].width = largura
    for c in chamados:
        ws.append([valor(c) for _t, valor, _l, _p in COLUNAS])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def gerar_pdf(chamados: list, inicio: date, fim: date, indicadores: dict | None = None,
              escopo: str = "") -> io.BytesIO:
    """Lista dos chamados do período; com `indicadores` (servicos.indicadores), começa pelas
    páginas de resumo com os gráficos do painel."""
    buf = io.BytesIO()
    pagina = landscape(A4)
    doc = SimpleDocTemplate(buf, pagesize=pagina, leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm, title="Relatório de Chamados")
    estilos = getSampleStyleSheet()
    celula = estilos["BodyText"].clone("celula", fontSize=8, leading=10)
    # cabeçalho em parágrafo: quebra a linha em vez de cortar o texto
    titulo_col = estilos["BodyText"].clone("titulo_col", fontSize=8, leading=9.5, fontName="Helvetica-Bold",
                                           textColor=colors.white)

    dados = [[Paragraph(escape(t), titulo_col) for t, *_ in COLUNAS_PDF]]
    for c in chamados:
        dados.append([Paragraph(escape(str(valor(c))), celula) for _t, valor, _l, _p in COLUNAS_PDF])

    tabela = Table(dados, colWidths=[p * mm for *_x, p in COLUNAS_PDF], repeatRows=1)
    tabela.hAlign = "LEFT"
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#" + AZUL)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F5F8")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C8CDD5")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
    ]))

    def rodape(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawString(10 * mm, 7 * mm, f"Gerado em {datetime.now():%d/%m/%Y %H:%M}")
        canvas.drawRightString(pagina[0] - 10 * mm, 7 * mm, f"Página {doc_.page}")
        canvas.restoreState()

    cabecalho = [
        Paragraph("Relatório de Chamados", estilos["Title"]),
        Paragraph(f"Período: {inicio:%d/%m/%Y} a {fim:%d/%m/%Y} — {len(chamados)} chamado(s)"
                  + (f" — {escape(escopo)}" if escopo else ""), estilos["Normal"]),
        Spacer(1, 6 * mm),
    ]
    resumo = []
    if indicadores is not None:
        from . import graficos_pdf
        resumo = graficos_pdf.resumo(indicadores, estilos, pagina[0] - 20 * mm) + [
            PageBreak(), Paragraph("Chamados do período", estilos["Heading2"]), Spacer(1, 3 * mm)]
    doc.build(cabecalho + resumo + [tabela], onFirstPage=rodape, onLaterPages=rodape)
    buf.seek(0)
    return buf


# ─── inventário ─────────────────────────────────────────────────────────────

COLUNAS_INVENTARIO = [
    ("Patrimônio", lambda e: e.patrimonio, 14),
    ("Tipo", lambda e: e.tipo, 14),
    ("Marca", lambda e: e.marca, 14),
    ("Modelo", lambda e: e.modelo, 24),
    ("Nº de série", lambda e: e.numero_serie, 20),
    ("Situação", lambda e: e.situacao, 14),
    ("Setor", lambda e: e.setor, 14),
    ("Usuário", lambda e: e.usuario.nome if e.usuario else None, 22),
    ("Processador", lambda e: e.processador, 22),
    ("Memória", lambda e: e.memoria, 10),
    ("Armazenamento", lambda e: e.armazenamento, 16),
    ("Sistema operacional", lambda e: e.sistema_operacional, 20),
    ("Licença do Windows", lambda e: e.licenca_windows, 32),
    ("Hostname", lambda e: e.hostname, 16),
    ("IP", lambda e: e.ip, 15),
    ("MAC", lambda e: e.mac, 18),
    ("Observações", lambda e: e.observacoes, 40),
    ("Atualizado em", lambda e: formatos.data_hora(e.atualizado_em), 16),
]


def gerar_excel_inventario(equipamentos: list) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Inventário"
    fundo, fonte = PatternFill("solid", fgColor=AZUL), Font(bold=True, color="FFFFFF")
    for col, (titulo, _v, largura) in enumerate(COLUNAS_INVENTARIO, start=1):
        cel = ws.cell(row=1, column=col, value=titulo)
        cel.fill, cel.font = fundo, fonte
        ws.column_dimensions[cel.column_letter].width = largura
    for e in equipamentos:
        ws.append([valor(e) or "" for _t, valor, _l in COLUNAS_INVENTARIO])
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ─── preventivas ────────────────────────────────────────────────────────────

COLUNAS_PREVENTIVAS = [
    ("Data", lambda p: formatos.data(p.data), 12),
    ("Patrimônio", lambda p: p.equipamento.patrimonio, 14),
    ("Tipo", lambda p: p.equipamento.tipo, 14),
    ("Equipamento", lambda p: p.equipamento.descricao, 24),
    ("Setor", lambda p: p.equipamento.setor, 14),
    ("Usuário", lambda p: p.equipamento.usuario.nome if p.equipamento.usuario else None, 20),
    ("Técnico", lambda p: p.tecnico.nome if p.tecnico else None, 20),
    ("OK", lambda p: p.contar("OK"), 6),
    ("Corrigidos", lambda p: p.contar("Corrigido"), 10),
    ("Problemas", lambda p: p.contar("Problema"), 10),
    ("Itens com problema", lambda p: "; ".join(i + (f" ({n})" if n else "") for i, _r, n in p.problemas), 40),
    ("Itens corrigidos", lambda p: "; ".join(i for i, r, _n in p.itens if r == "Corrigido"), 40),
    ("Peças", lambda p: p.pecas, 24),
    ("Observações", lambda p: p.observacoes, 40),
    ("Chamado", lambda p: f"#{p.chamado_id}" if p.chamado_id else None, 10),
]


def gerar_excel_preventivas(lista: list) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Preventivas"
    fundo, fonte = PatternFill("solid", fgColor=AZUL), Font(bold=True, color="FFFFFF")
    for col, (titulo, _v, largura) in enumerate(COLUNAS_PREVENTIVAS, start=1):
        cel = ws.cell(row=1, column=col, value=titulo)
        cel.fill, cel.font = fundo, fonte
        ws.column_dimensions[cel.column_letter].width = largura
    for p in lista:
        ws.append([(lambda v: "" if v is None else v)(valor(p)) for _t, valor, _l in COLUNAS_PREVENTIVAS])
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ─── pesquisa de satisfação ─────────────────────────────────────────────────

def _colunas_pesquisa():
    from .pesquisas import RESOLVIDOS
    return [
        ("Respondida em", lambda r: formatos.data_hora(r.respondida_em), 17),
        ("Nome", lambda r: r.usuario.nome if r.usuario else "(conta apagada)", 26),
        ("Setor", lambda r: r.setor, 16),
        ("Chamados resolvidos?", lambda r: RESOLVIDOS.get(r.resolvidos, r.resolvidos), 30),
        ("Nota (0 a 10)", lambda r: r.nota, 13),
        ("Comentário ou sugestão", lambda r: r.comentario or "", 70),
    ]


def gerar_excel_pesquisa(p, res) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Respostas"
    fundo, fonte = PatternFill("solid", fgColor=AZUL), Font(bold=True, color="FFFFFF")
    colunas = _colunas_pesquisa()
    for col, (titulo, _v, largura) in enumerate(colunas, start=1):
        cel = ws.cell(row=1, column=col, value=titulo)
        cel.fill, cel.font = fundo, fonte
        ws.column_dimensions[cel.column_letter].width = largura
    for r in res.respostas:
        ws.append([valor(r) for _t, valor, _l in colunas])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    resumo = wb.create_sheet("Resumo")
    linhas = [("Pesquisa", p.titulo), ("Período", f"{formatos.data(p.aberta_em)} a {formatos.data(p.encerra_em)}"),
              ("Respostas", f"{res.total} de {res.convidados}"),
              ("Nota média", round(res.media, 1) if res.media is not None else "—"),
              ("NPS", res.nps if res.nps is not None else "—"),
              ("Notas 9-10 (satisfeitos)", res.promotores), ("Notas 7-8 (neutros)", res.neutros),
              ("Notas 0-6 (insatisfeitos)", res.detratores)]
    linhas += [(f"Resolvidos: {rotulo}", n) for rotulo, n in res.resolvidos]
    for linha in linhas:
        resumo.append(list(linha))
    resumo.column_dimensions["A"].width, resumo.column_dimensions["B"].width = 34, 50
    for cel in resumo["A"]:
        cel.font = Font(bold=True)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def gerar_pdf_pesquisa(p, res) -> io.BytesIO:
    buf = io.BytesIO()
    pagina = A4
    doc = SimpleDocTemplate(buf, pagesize=pagina, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm, title=p.titulo)
    estilos = getSampleStyleSheet()
    celula = estilos["BodyText"].clone("p_cel", fontSize=8.5, leading=11)
    cab = estilos["BodyText"].clone("p_cab", fontSize=8.5, leading=10, fontName="Helvetica-Bold", textColor=colors.white)
    largura = pagina[0] - 28 * mm

    def tabela(linhas, larguras, cabecalho=True):
        t = Table(linhas, colWidths=larguras, repeatRows=1 if cabecalho else 0, hAlign="LEFT")
        estilo = [("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C8CDD5")), ("VALIGN", (0, 0), (-1, -1), "TOP")]
        if cabecalho:
            estilo += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#" + AZUL)),
                       ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F5F8")])]
        t.setStyle(TableStyle(estilo))
        return t

    media = f"{res.media:.1f}".replace(".", ",") if res.media is not None else "—"
    taxa = f" ({round(res.taxa)}%)" if res.taxa is not None else ""
    kpis = [[Paragraph(escape(a), cab) for a in ("Respostas", "Nota média", "NPS", "Satisfeitos (9-10)",
                                                  "Neutros (7-8)", "Insatisfeitos (0-6)")],
            [Paragraph(x, celula) for x in (f"{res.total} de {res.convidados}{taxa}", media,
                                            str(res.nps) if res.nps is not None else "—",
                                            str(res.promotores), str(res.neutros), str(res.detratores))]]
    notas = [[Paragraph("Nota", cab)] + [Paragraph(str(n), cab) for n in range(11)],
             [Paragraph("Respostas", celula)] + [Paragraph(str(v), celula) for v in res.notas]]
    resolvidos = [[Paragraph("Nos últimos 6 meses, seus chamados foram resolvidos?", cab), Paragraph("Respostas", cab)]]
    resolvidos += [[Paragraph(escape(r), celula), Paragraph(str(n), celula)] for r, n in res.resolvidos]

    from .pesquisas import RESOLVIDOS
    respostas = [[Paragraph(t, cab) for t in ("Nome", "Setor", "Resolvidos?", "Nota", "Comentário ou sugestão")]]
    respostas += [[Paragraph(escape(r.usuario.nome if r.usuario else "—"), celula), Paragraph(escape(r.setor), celula),
                   Paragraph(escape(RESOLVIDOS.get(r.resolvidos, r.resolvidos)), celula), Paragraph(str(r.nota), celula),
                   Paragraph(escape(r.comentario or ""), celula)] for r in res.respostas]

    def rodape(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawString(14 * mm, 8 * mm, f"Gerado em {datetime.now():%d/%m/%Y %H:%M}")
        canvas.drawRightString(pagina[0] - 14 * mm, 8 * mm, f"Página {doc_.page}")
        canvas.restoreState()

    partes = [Paragraph(escape(p.titulo), estilos["Title"]),
              Paragraph(f"Aberta de {p.aberta_em:%d/%m/%Y} a {p.encerra_em:%d/%m/%Y}", estilos["Normal"]),
              Spacer(1, 5 * mm), tabela(kpis, [largura / 6] * 6), Spacer(1, 5 * mm),
              tabela(notas, [22 * mm] + [(largura - 22 * mm) / 11] * 11), Spacer(1, 5 * mm),
              tabela(resolvidos, [largura - 30 * mm, 30 * mm]), Spacer(1, 6 * mm),
              Paragraph("Respostas", estilos["Heading3"]),
              tabela(respostas, [40 * mm, 26 * mm, 32 * mm, 12 * mm, largura - 110 * mm])]
    doc.build(partes, onFirstPage=rodape, onLaterPages=rodape)
    buf.seek(0)
    return buf
