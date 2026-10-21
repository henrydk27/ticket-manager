"""Gráficos do painel em SVG, desenhados no servidor (sem biblioteca nem JavaScript).

As cores vêm de variáveis CSS (style.css, bloco "Painel"), então seguem o tema e o modo escuro.
Cada gráfico tem <title> nos elementos (dica ao passar o mouse) e um aria-label com o resumo.
"""

import math

from markupsafe import Markup, escape


def _fmt(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def spark(valores: list[float | None], largura: int = 120, altura: int = 28) -> Markup:
    """Linha pequena da tendência (os vazios são ignorados)."""
    pontos = [(i, v) for i, v in enumerate(valores) if v is not None]
    if len(pontos) < 2:
        return Markup("")
    n = max(len(valores) - 1, 1)
    vs = [v for _i, v in pontos]
    mn, mx = min(vs), max(vs)
    faixa = (mx - mn) or 1
    xy = [(3 + i * (largura - 6) / n, altura - 4 - (v - mn) / faixa * (altura - 8)) for i, v in pontos]
    linha = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in xy)
    x, y = xy[-1]
    return Markup(
        f'<svg class="spark" viewBox="0 0 {largura} {altura}" width="{largura}" height="{altura}" aria-hidden="true">'
        f'<polyline points="{linha}" class="g-linha g-serie"/>'
        f'<circle cx="{_fmt(x)}" cy="{_fmt(y)}" r="3" class="g-ponto g-serie-fill"/></svg>')


def linhas(rotulos: list[str], series: list[tuple[str, str, list[int]]], largura: int = 1000,
           altura: int = 240) -> Markup:
    """Linhas de várias séries no mesmo eixo. series: [(nome, classe CSS, valores)]."""
    esq, dir_, topo, base = 34, 16, 14, 28
    n = max(len(rotulos) - 1, 1)
    mx = max([v for _n, _c, vs in series for v in vs] + [1])
    passo = max(1, math.ceil(mx / 4))
    mx = passo * math.ceil(mx / passo)

    def x(i):
        return esq + i * (largura - esq - dir_) / n

    def y(v):
        return topo + (altura - topo - base) * (1 - v / mx)

    partes = [f'<svg class="grafico-svg" viewBox="0 0 {largura} {altura}" role="img" '
              f'aria-label="{escape(", ".join(f"{nm}: {sum(vs)} no total" for nm, _c, vs in series))}">']
    for v in range(0, mx + 1, passo):
        partes.append(f'<line x1="{esq}" x2="{largura - dir_}" y1="{_fmt(y(v))}" y2="{_fmt(y(v))}" '
                      f'class="{"g-base" if v == 0 else "g-grade"}"/>'
                      f'<text x="{esq - 8}" y="{_fmt(y(v) + 4)}" text-anchor="end" class="g-eixo">{v}</text>')
    pula = max(1, math.ceil(len(rotulos) / 12))
    for i, r in enumerate(rotulos):
        if i % pula == 0 or i == len(rotulos) - 1:
            partes.append(f'<text x="{_fmt(x(i))}" y="{altura - 8}" text-anchor="middle" class="g-eixo">{escape(r)}</text>')
    for nome, classe, vs in series:
        pts = " ".join(f"{_fmt(x(i))},{_fmt(y(v))}" for i, v in enumerate(vs))
        partes.append(f'<polyline points="{pts}" class="g-linha {classe}"/>')
        for i, v in enumerate(vs):
            ultimo = i == len(vs) - 1
            partes.append(f'<circle cx="{_fmt(x(i))}" cy="{_fmt(y(v))}" r="{4 if ultimo else 2.5}" '
                          f'class="g-ponto {classe}-fill{" g-anel" if ultimo else ""}">'
                          f'<title>{escape(rotulos[i])}: {v} {escape(nome.lower())}</title></circle>')
            # área de passar o mouse maior que o ponto
            partes.append(f'<circle cx="{_fmt(x(i))}" cy="{_fmt(y(v))}" r="10" class="g-alvo">'
                          f'<title>{escape(rotulos[i])}: {v} {escape(nome.lower())}</title></circle>')
    partes.append("</svg>")
    return Markup("".join(partes))


def rosca(itens: list[tuple[str, int, str]], tamanho: int = 150) -> Markup:
    """Rosca com o total no meio. itens: [(rótulo, valor, classe CSS)]."""
    total = sum(v for _r, v, _c in itens)
    c = tamanho / 2
    raio, espessura = c - 14, 20
    circ = 2 * math.pi * raio
    partes = [f'<svg class="rosca" viewBox="0 0 {tamanho} {tamanho}" width="{tamanho}" height="{tamanho}" role="img" '
              f'aria-label="{escape(", ".join(f"{r}: {v}" for r, v, _c in itens))}">',
              f'<circle cx="{c}" cy="{c}" r="{_fmt(raio)}" class="g-trilho" stroke-width="{espessura}" fill="none"/>']
    feito = 0.0
    for rotulo, v, classe in itens:
        if not v or not total:
            continue
        comp = circ * v / total
        vao = 3 if len([i for i in itens if i[1]]) > 1 else 0
        partes.append(f'<circle cx="{c}" cy="{c}" r="{_fmt(raio)}" fill="none" stroke-width="{espessura}" '
                      f'class="{classe}" stroke-dasharray="{_fmt(max(comp - vao, 1))} {_fmt(circ)}" '
                      f'stroke-dashoffset="{_fmt(-feito)}" transform="rotate(-90 {c} {c})">'
                      f'<title>{escape(rotulo)}: {v}</title></circle>')
        feito += comp
    partes.append(f'<text x="{c}" y="{c + 9}" text-anchor="middle" class="g-total">{total}</text></svg>')
    return Markup("".join(partes))
