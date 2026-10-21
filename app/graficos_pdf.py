"""Páginas de resumo do PDF do relatório: os mesmos gráficos do painel, desenhados com o ReportLab.

Recebe o dicionário de servicos.indicadores() e devolve "flowables" para o SimpleDocTemplate.
Cores fixas do modo claro (papel), as mesmas do painel.
"""

import math

from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String, Wedge
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

from . import formatos

S1, S2 = colors.HexColor("#2A78D6"), colors.HexColor("#EB6834")
NEUTRO, PERIGO = colors.HexColor("#9AA3AD"), colors.HexColor("#B42318")
GRADE, BASE, TINTA, TINTA2 = (colors.HexColor("#E1E0D9"), colors.HexColor("#C3C2B7"),
                              colors.HexColor("#1B1F24"), colors.HexColor("#5B636E"))
TRILHO = colors.HexColor("#EEF1F4")
STATUS = {"Aberto": colors.HexColor("#1D4F91"), "Em andamento": colors.HexColor("#8A5300"),
          "Aguardando usuário": colors.HexColor("#5B2D91")}
AVAL = [colors.HexColor("#0CA30C"), colors.HexColor("#EDA100"), colors.HexColor("#D03B3B")]
PRIO = [PERIGO, S1, NEUTRO]
SEQ = [colors.HexColor("#A9CBF0"), colors.HexColor("#6AA5E6"), S1, PERIGO]


def _titulo(d: Drawing, texto: str, sub: str = "") -> None:
    d.add(String(0, d.height - 11, texto, fontName="Helvetica-Bold", fontSize=10, fillColor=TINTA))
    if sub:
        d.add(String(0, d.height - 23, sub, fontName="Helvetica", fontSize=7.5, fillColor=TINTA2))


def _legenda(d: Drawing, x: float, y: float, itens: list[tuple[str, object]]) -> None:
    for texto, cor in itens:
        d.add(Rect(x, y, 7, 7, fillColor=cor, strokeColor=None))
        d.add(String(x + 10, y + 0.5, texto, fontName="Helvetica", fontSize=7.5, fillColor=TINTA2))
        x += 18 + len(texto) * 4.1


def linha(serie: list[dict], agrupamento: str, largura: float, altura: float) -> Drawing:
    d = Drawing(largura, altura)
    _titulo(d, f"Abertos x encerrados por {agrupamento}", "A fila está crescendo ou diminuindo?")
    _legenda(d, 0, altura - 36, [("Abertos", S1), ("Encerrados", S2)])
    esq, dir_, topo, base = 22, 8, 44, 16
    rot = [b["rotulo"] for b in serie]
    sa, se = [b["abertos"] for b in serie], [b["encerrados"] for b in serie]
    mx = max(sa + se + [1])
    passo = max(1, math.ceil(mx / 4))
    mx = passo * math.ceil(mx / passo)
    n = max(len(rot) - 1, 1)

    def x(i):
        return esq + i * (largura - esq - dir_) / n

    def y(v):
        return base + (altura - topo - base) * v / mx

    for v in range(0, mx + 1, passo):
        d.add(Line(esq, y(v), largura - dir_, y(v), strokeColor=BASE if v == 0 else GRADE, strokeWidth=0.5))
        d.add(String(esq - 4, y(v) - 2.5, str(v), fontName="Helvetica", fontSize=7, fillColor=TINTA2,
                     textAnchor="end"))
    pula = max(1, math.ceil(len(rot) / 12))
    for i, r in enumerate(rot):
        if i % pula == 0 or i == len(rot) - 1:
            d.add(String(x(i), 3, r, fontName="Helvetica", fontSize=7, fillColor=TINTA2, textAnchor="middle"))
    for vs, cor in ((sa, S1), (se, S2)):
        if len(vs) > 1:
            d.add(PolyLine([c for i, v in enumerate(vs) for c in (x(i), y(v))], strokeColor=cor, strokeWidth=1.6,
                           strokeLineJoin=1, strokeLineCap=1))
        for i, v in enumerate(vs):
            d.add(Circle(x(i), y(v), 2.4 if i == len(vs) - 1 else 1.4, fillColor=cor, strokeColor=None))
    return d


def rosca(por_status: list[tuple[str, int]], largura: float, altura: float) -> Drawing:
    d = Drawing(largura, altura)
    total = sum(n for _s, n in por_status)
    _titulo(d, "Em aberto por status (agora)")
    cx, cy, r = 48, (altura - 16) / 2, min(42, (altura - 24) / 2)
    if not total:
        d.add(String(0, altura - 34, "Nenhum chamado em aberto.", fontName="Helvetica", fontSize=8, fillColor=TINTA2))
        return d
    ang = 90.0
    for st, n in por_status:
        if not n:
            continue
        passo = 360 * n / total
        d.add(Wedge(cx, cy, r, ang - passo, ang, radius1=r * 0.62, fillColor=STATUS.get(st, S1),
                    strokeColor=colors.white, strokeWidth=1.5))
        ang -= passo
    d.add(String(cx, cy - 6, str(total), fontName="Helvetica-Bold", fontSize=16, fillColor=TINTA, textAnchor="middle"))
    y = cy + 14
    for st, n in por_status:
        d.add(Rect(cx + r + 16, y, 7, 7, fillColor=STATUS.get(st, S1), strokeColor=None))
        d.add(String(cx + r + 27, y + 0.5, f"{st}  {n}", fontName="Helvetica", fontSize=8, fillColor=TINTA))
        y -= 16
    return d


def barras(titulo: str, itens: list[tuple[str, list[int]]], cores: list, largura: float, sub: str = "",
           legenda: list[str] | None = None, vazio: str = "Nada no período.", cor_por_linha: bool = False) -> Drawing:
    """Barras horizontais (empilhadas quando cada item tem mais de um valor).

    cores: uma por segmento; com cor_por_linha, uma por linha (barra simples)."""
    linha_h = 15
    extra = 12 if legenda else 0
    altura = 30 + extra + max(len(itens), 1) * linha_h
    d = Drawing(largura, altura)
    _titulo(d, titulo, sub)
    if legenda:
        _legenda(d, 0, altura - 36, list(zip(legenda, cores)))
    if not itens or not any(sum(v) for _r, v in itens):
        d.add(String(0, altura - 34 - extra, vazio, fontName="Helvetica", fontSize=8, fillColor=TINTA2))
        return d
    esq, dir_ = largura * 0.34, 22
    mx = max(sum(v) for _r, v in itens) or 1
    y = altura - 30 - extra - linha_h + 3
    for linha_i, (rotulo, valores) in enumerate(itens):
        d.add(String(0, y + 2, rotulo[:34], fontName="Helvetica", fontSize=8, fillColor=TINTA))
        x = esq
        for v, cor in zip(valores, [cores[linha_i]] if cor_por_linha else cores):
            if v:
                w = (largura - esq - dir_) * v / mx
                d.add(Rect(x, y, max(w - 1, 1), 9, fillColor=cor, strokeColor=None))
                x += w
        d.add(String(largura, y + 2, str(sum(valores)), fontName="Helvetica-Bold", fontSize=8, fillColor=TINTA,
                     textAnchor="end"))
        y -= linha_h
    return d


def calor(dados: dict, largura: float) -> Drawing:
    dias, horas = dados["dias"], dados["horas"]
    altura = 40 + len(dias) * 14
    d = Drawing(largura, altura)
    fora = f" · {dados['fora']} fora do expediente" if dados["fora"] else ""
    _titulo(d, "Quando os chamados chegam", "Abertos no período, por dia da semana e hora" + fora)
    mx = max([max(v) for _d, v in dias] + [0])
    if not mx:
        d.add(String(0, altura - 34, "Nenhum chamado no período.", fontName="Helvetica", fontSize=8, fillColor=TINTA2))
        return d
    esq = 26
    cw = (largura - esq) / len(horas)
    y = altura - 30 - 14
    for nome, valores in dias:
        d.add(String(0, y + 3, nome, fontName="Helvetica", fontSize=7.5, fillColor=TINTA2))
        for i, v in enumerate(valores):
            nivel = 0 if not v else min(4, 1 + math.ceil(3 * v / mx))
            cor = TRILHO if nivel == 0 else colors.Color(
                *[a + (b - a) * (nivel / 4) for a, b in zip((1, 1, 1), (S1.red, S1.green, S1.blue))])
            d.add(Rect(esq + i * cw + 1, y, cw - 2, 11, fillColor=cor, strokeColor=None))
        y -= 14
    for i, h in enumerate(horas):
        if i % 2 == 0:
            d.add(String(esq + i * cw + cw / 2, y + 4, f"{h}h", fontName="Helvetica", fontSize=7, fillColor=TINTA2,
                         textAnchor="middle"))
    return d


def avaliacao(avaliacoes: list[tuple[str, int]], sem: int, largura: float) -> Drawing:
    d = Drawing(largura, 56)
    _titulo(d, "Avaliação do atendimento", "Encerrados no período" + (f" · {sem} sem avaliação" if sem else ""))
    total = sum(n for _a, n in avaliacoes)
    if not total:
        d.add(String(0, 22, "Nenhuma avaliação no período.", fontName="Helvetica", fontSize=8, fillColor=TINTA2))
        return d
    x = 0
    for (a, n), cor in zip(avaliacoes, AVAL):
        if n:
            w = largura * n / total
            d.add(Rect(x, 16, max(w - 1.5, 1), 10, fillColor=cor, strokeColor=None))
            x += w
    _legenda(d, 0, 2, [(f"{a} {n} ({round(100 * n / total)}%)", cor) for (a, n), cor in zip(avaliacoes, AVAL)])
    return d


def _variacao(v, melhor=None) -> str:
    if v is None:
        return "sem dados anteriores"
    seta = "▲" if v > 0 else ("▼" if v < 0 else "=")
    return f"{seta} {'+' if v > 0 else ''}{round(v)}% vs período anterior"


def resumo(d: dict, estilos, largura_util: float) -> list:
    """Flowables das páginas de resumo."""
    r = d["resumo"]
    rotulo = estilos["BodyText"].clone("kpi_r", fontSize=7.5, leading=9, textColor=TINTA2)
    valor = estilos["BodyText"].clone("kpi_v", fontSize=16, leading=19, fontName="Helvetica-Bold", textColor=TINTA)
    nota = estilos["BodyText"].clone("kpi_n", fontSize=7, leading=8.5, textColor=TINTA2)
    sat = f"{round(r['satisfacao'])}%" if r["satisfacao"] is not None else "—"
    kpis = [
        ("Em aberto agora", str(r["abertos"]), f"{r['sem_responsavel']} sem responsável"),
        ("Abertos no período", str(r["novos"]), _variacao(r["novos_var"])),
        ("Encerrados no período", str(r["fechados"]), _variacao(r["fechados_var"])),
        ("Tempo médio até encerrar", formatos.horas(r["tempo_medio"]), "em horário de expediente; "
         + _variacao(r["tempo_var"])),
        ("Satisfação", sat, f"{r['avaliacoes']} avaliação(ões), \"Bom\""),
    ]
    tabela = Table([[[Paragraph(a, rotulo), Paragraph(b, valor), Paragraph(c, nota)] for a, b, c in kpis]],
                   colWidths=[largura_util / len(kpis)] * len(kpis))
    tabela.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#DFE3E8")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DFE3E8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))

    meia = (largura_util - 10 * mm) / 2
    grade = Table([[linha(d["serie"], d["agrupamento"], largura_util * 0.64, 62 * mm),
                    rosca(d["por_status"], largura_util * 0.34, 62 * mm)]],
                  colWidths=[largura_util * 0.66, largura_util * 0.34])
    titulo_setor = f"Em aberto por {'setor' if d['por_destino'] else 'setor de quem pediu'} e prioridade (agora)"
    meio = Table([[barras(titulo_setor, d["setor_prioridade"][:10], PRIO, meia, legenda=["Alta", "Média", "Baixa"],
                          vazio="Nenhum chamado em aberto."),
                   barras("Há quanto tempo estão em aberto (agora)", [(rt, [n]) for rt, n in d["idade"]],
                          SEQ, meia, sub="Em horas de expediente", vazio="Nenhum chamado em aberto.",
                          cor_por_linha=True)]],
                 colWidths=[meia + 10 * mm, meia])

    baixo = Table([[calor(d["calor"], meia), avaliacao(d["avaliacoes"], d["sem_avaliacao"], meia)]],
                  colWidths=[meia + 10 * mm, meia])
    for t in (grade, meio, baixo):
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))

    partes = [tabela, Spacer(1, 5 * mm), grade, Spacer(1, 4 * mm), KeepTogether([meio]), Spacer(1, 4 * mm),
              KeepTogether([baixo])]
    if d["responsaveis"]:
        cab = estilos["BodyText"].clone("resp_c", fontSize=8, fontName="Helvetica-Bold", textColor=colors.white)
        cel = estilos["BodyText"].clone("resp_l", fontSize=8, leading=10)
        linhas = [[Paragraph(t, cab) for t in ("Responsável", "Em aberto agora", "Encerrados no período",
                                               "Tempo médio (expediente)")]]
        linhas += [[Paragraph(x["nome"], cel), x["em_aberto"], x["encerrados"], formatos.horas(x["tempo"])]
                   for x in d["responsaveis"]]
        t = Table(linhas, colWidths=[70 * mm, 35 * mm, 40 * mm, 45 * mm], hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F5F8")]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C8CDD5")),
            ("FONTSIZE", (0, 1), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        partes += [Spacer(1, 5 * mm), KeepTogether([Paragraph("Por responsável", estilos["Heading4"].clone(
            "resp_t", fontName="Helvetica-Bold", fontSize=10, textColor=TINTA)), t])]
    return partes
