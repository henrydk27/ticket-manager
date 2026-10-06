"""Temas de cor da tela inteira: uma cor principal + intensidade (1 a 5).

Fonte única: static/cores.css é gerado daqui (python -m app.temas). Um teste confere que
os dois estão iguais e que TODAS as combinações (cor × intensidade × claro/escuro) têm
contraste legível. As cores de alerta e de situação (aberto, fechado, erro...) não mudam.

As cores são calculadas em OKLCH (claridade, croma, matiz): a intensidade aumenta o croma
(quanto de cor) de fundos, bordas e destaques de forma parecida em todos os tons.
"""

import math
import os

# chave: (nome, matiz OKLCH em graus, fator de croma) — Grafite é quase cinza
CORES = {
    "azul": ("Azul", 255, 1.0),
    "petroleo": ("Petróleo", 210, 1.0),
    "verde": ("Verde", 150, 1.0),
    "roxo": ("Roxo", 300, 1.0),
    "rosa": ("Rosa", 355, 1.0),
    "vermelho": ("Vermelho", 27, 1.0),
    "laranja": ("Laranja", 55, 1.0),
    "grafite": ("Grafite", 260, 0.18),
}
INTENSIDADES = {1: "Suave", 2: "Leve", 3: "Média", 4: "Forte", 5: "Intensa"}
INTENSIDADE_PADRAO = 3

# "Padrão": o visual original do sistema (fundo neutro, destaque azul-marinho)
PADRAO_CLARO = {"primaria": "#1f3a5f", "primaria-hover": "#16304f", "primaria-suave": "#e6edf6",
                "foco": "#2a78d6", "serie": "#2a78d6"}
PADRAO_ESCURO = {"primaria": "#4d8fe0", "primaria-hover": "#639ee6", "primaria-suave": "#1c2a3d",
                 "foco": "#6aa5ee", "serie": "#3987e5"}
TEXTO_CLARO, TEXTO_ESCURO = "#ffffff", "#111418"

# Contraste mínimo exigido (WCAG): texto 4,5:1; texto principal 7:1; gráficos 3:1
MIN_TEXTO, MIN_TEXTO_PRINCIPAL, MIN_GRAFICO = 4.5, 7.0, 3.0


# ─── conversão de cores ─────────────────────────────────────────────────────

def _oklch_para_rgb_linear(L: float, C: float, h: float) -> tuple[float, float, float]:
    a, b = C * math.cos(math.radians(h)), C * math.sin(math.radians(h))
    l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
            -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
            -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)


def oklch(L: float, C: float, h: float) -> str:
    """Cor OKLCH em hexadecimal; reduz o croma até caber nas cores da tela (sRGB)."""
    while True:
        rgb = _oklch_para_rgb_linear(L, C, h)
        if all(-1e-6 <= v <= 1 + 1e-6 for v in rgb) or C <= 0:
            break
        C = max(0.0, C - 0.002)

    def codificar(v):
        v = min(1.0, max(0.0, v))
        v = 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
        return round(v * 255)
    return "#" + "".join(f"{codificar(v):02x}" for v in rgb)


def _luminancia(hexa: str) -> float:
    def canal(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hexa[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def contraste(a: str, b: str) -> float:
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def texto_sobre(fundo: str) -> str:
    """Branco ou quase preto, o que tiver mais contraste com o fundo."""
    return TEXTO_CLARO if contraste(fundo, TEXTO_CLARO) >= contraste(fundo, TEXTO_ESCURO) else TEXTO_ESCURO


def _garantir(L: float, C: float, h: float, fundos: list[str], minimo: float, escurecer: bool) -> str:
    """Ajusta a claridade até a cor ter o contraste mínimo com todos os fundos."""
    for _ in range(100):
        cor = oklch(L, C, h)
        if all(contraste(cor, f) >= minimo for f in fundos):
            return cor
        L += -0.01 if escurecer else 0.01
    return cor


# ─── geração das variáveis de cada tema ─────────────────────────────────────

def variaveis(cor: str, n: int, escuro: bool) -> dict[str, str]:
    """Todas as cores da tela para uma cor principal, intensidade (1–5) e modo."""
    _nome, h, fator = CORES[cor]
    k = (n - 1) / 4                       # 0 (suave) … 1 (intensa)
    tinta = (0.006 + 0.044 * k) * fator   # croma dos fundos
    destaque = (0.10 + 0.07 * k) * max(fator, 0.15)
    v: dict[str, str] = {}
    if not escuro:
        v["fundo"] = oklch(0.965 - 0.025 * k, tinta, h)
        v["superficie"] = oklch(0.995 - 0.012 * k, tinta * 0.45, h)
        v["superficie-2"] = oklch(0.975 - 0.02 * k, tinta * 0.75, h)
        v["borda"] = oklch(0.89 - 0.03 * k, tinta * 1.3, h)
        v["trilho"] = oklch(0.93 - 0.025 * k, tinta * 0.9, h)
        fundos = [v["fundo"], v["superficie"], v["superficie-2"]]
        v["texto"] = _garantir(0.22, min(0.02, tinta * 0.5), h, fundos, MIN_TEXTO_PRINCIPAL, True)
        v["texto-2"] = _garantir(0.48, min(0.04, tinta * 0.8), h, fundos, MIN_TEXTO, True)
        v["primaria-suave"] = oklch(0.92 - 0.03 * k, 0.03 + 0.03 * k * fator, h)
        v["primaria"] = _garantir(0.42 - 0.03 * k, destaque, h, fundos + [v["primaria-suave"]], MIN_TEXTO, True)
        v["primaria-hover"] = oklch(0.36 - 0.03 * k, destaque, h)
        v["foco"] = oklch(0.58, 0.14 * max(fator, 0.15), h)
        v["serie"] = _garantir(0.58, (0.12 + 0.05 * k) * max(fator, 0.15), h, [v["superficie"]], MIN_GRAFICO, True)
    else:
        v["fundo"] = oklch(0.17 + 0.02 * k, tinta * 0.9, h)
        v["superficie"] = oklch(0.215 + 0.02 * k, tinta, h)
        v["superficie-2"] = oklch(0.25 + 0.02 * k, tinta, h)
        v["borda"] = oklch(0.32 + 0.03 * k, tinta * 1.1, h)
        v["trilho"] = oklch(0.27 + 0.02 * k, tinta, h)
        fundos = [v["fundo"], v["superficie"], v["superficie-2"]]
        v["texto"] = _garantir(0.95, min(0.015, tinta * 0.4), h, fundos, MIN_TEXTO_PRINCIPAL, False)
        v["texto-2"] = _garantir(0.76, min(0.03, tinta * 0.6), h, fundos, MIN_TEXTO, False)
        v["primaria-suave"] = oklch(0.30 + 0.03 * k, 0.04 + 0.04 * k * fator, h)
        v["primaria"] = _garantir(0.72, destaque, h, fundos + [v["primaria-suave"]], MIN_TEXTO, False)
        v["primaria-hover"] = oklch(0.78, destaque, h)
        v["foco"] = oklch(0.76, 0.13 * max(fator, 0.15), h)
        v["serie"] = _garantir(0.66, (0.12 + 0.05 * k) * max(fator, 0.15), h, [v["superficie"]], MIN_GRAFICO, False)
    v["sobre-primaria"] = texto_sobre(v["primaria"])
    return v


def variaveis_padrao(escuro: bool) -> dict[str, str]:
    v = dict(PADRAO_ESCURO if escuro else PADRAO_CLARO)
    v["sobre-primaria"] = texto_sobre(v["primaria"])
    return v


def opcoes() -> list[tuple[str, str, str, str]]:
    """(chave, nome, amostra no modo claro, amostra no modo escuro) para a tela."""
    lista = [("padrao", "Padrão", PADRAO_CLARO["primaria"], PADRAO_ESCURO["primaria"])]
    for chave, (nome, _h, _f) in CORES.items():
        lista.append((chave, nome, variaveis(chave, 5, False)["primaria"], variaveis(chave, 5, True)["primaria"]))
    return lista


# ─── CSS ────────────────────────────────────────────────────────────────────

def _bloco(seletor: str, v: dict[str, str]) -> str:
    return seletor + " { " + " ".join(f"--{k}: {c};" for k, c in v.items()) + " }"


def gerar_css() -> str:
    linhas = [
        "/* GERADO por app/temas.py (python -m app.temas). Não edite à mão. */",
        "/* Tema escolhido no botão de cor: data-cor e data-intensidade no <html>. */",
        "/* Sem data-cor = Padrão (fundos neutros do style.css + destaque azul-marinho). */",
        "",
        _bloco(":root", variaveis_padrao(False)),
        "@media (prefers-color-scheme: dark) {",
        "  " + _bloco(':root:not([data-theme="light"])', variaveis_padrao(True)),
        "}",
        _bloco(':root[data-theme="dark"]', variaveis_padrao(True)),
    ]
    for cor in CORES:
        linhas.append("")
        for n in INTENSIDADES:
            sel = f':root[data-cor="{cor}"][data-intensidade="{n}"]'
            linhas.append(_bloco(sel + ':not([data-theme="dark"])', variaveis(cor, n, False)))
        linhas.append("@media (prefers-color-scheme: dark) {")
        for n in INTENSIDADES:
            sel = f':root[data-cor="{cor}"][data-intensidade="{n}"]'
            linhas.append("  " + _bloco(sel + ':not([data-theme="light"])', variaveis(cor, n, True)))
        linhas.append("}")
        for n in INTENSIDADES:
            sel = f':root[data-cor="{cor}"][data-intensidade="{n}"]'
            linhas.append(_bloco(sel + '[data-theme="dark"]', variaveis(cor, n, True)))
    return "\n".join(linhas) + "\n"


def verificar(cor: str, n: int, escuro: bool) -> list[str]:
    """Problemas de contraste de uma combinação (lista vazia = tudo legível)."""
    v = variaveis(cor, n, escuro)
    problemas = []
    for fundo in ("fundo", "superficie", "superficie-2"):
        if contraste(v["texto"], v[fundo]) < MIN_TEXTO_PRINCIPAL:
            problemas.append(f"texto/{fundo}")
        if contraste(v["texto-2"], v[fundo]) < MIN_TEXTO:
            problemas.append(f"texto-2/{fundo}")
        if contraste(v["primaria"], v[fundo]) < MIN_TEXTO:
            problemas.append(f"primaria/{fundo}")
    if contraste(v["primaria"], v["primaria-suave"]) < MIN_TEXTO:
        problemas.append("primaria/primaria-suave")
    if contraste(v["sobre-primaria"], v["primaria"]) < MIN_TEXTO:
        problemas.append("botao")
    if contraste(v["serie"], v["superficie"]) < MIN_GRAFICO:
        problemas.append("grafico")
    return problemas


CAMINHO_CSS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "cores.css")

if __name__ == "__main__":
    with open(CAMINHO_CSS, "w", encoding="utf-8", newline="\n") as f:
        f.write(gerar_css())
    ruins = [(c, n, e, p) for c in CORES for n in INTENSIDADES for e in (False, True) if (p := verificar(c, n, e))]
    print(f"gerado: {CAMINHO_CSS} ({os.path.getsize(CAMINHO_CSS) // 1024} KB)")
    print("combinações com problema de contraste:", ruins or "nenhuma")
