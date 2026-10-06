"""Paletas de cor de destaque (botões, links, títulos, gráficos).

Fonte única das cores: o arquivo static/cores.css é gerado a partir daqui
(python -m app.temas). Um teste confere que os dois estão iguais.

Cada paleta tem a versão para o modo claro e para o escuro. A cor do texto sobre
os botões (branco ou quase preto) é escolhida pelo maior contraste.
"""

import os

# chave: (nome, claro, escuro) — cada modo: primaria, hover, suave (fundo de destaque), foco, serie (gráficos)
PALETAS = {
    "azul": ("Azul", ("#1f3a5f", "#16304f", "#e6edf6", "#2a78d6", "#2a78d6"),
                     ("#4d8fe0", "#639ee6", "#1c2a3d", "#6aa5ee", "#3987e5")),
    "petroleo": ("Petróleo", ("#0f5e66", "#0b4a50", "#e3f1f2", "#13838e", "#13838e"),
                             ("#3cb4bf", "#5cc3cc", "#12302f", "#5cc3cc", "#2ea7b2")),
    "verde": ("Verde", ("#1e6b3a", "#17552e", "#e5f3ea", "#2e8b57", "#2e8b57"),
                       ("#4fbf7c", "#66cc8f", "#163024", "#5fd18f", "#3fae6c")),
    "roxo": ("Roxo", ("#4a3aa7", "#3c2f8a", "#ecebfa", "#6b5bd2", "#6b5bd2"),
                     ("#9085e9", "#a399ee", "#24203f", "#a399ee", "#8a7fe6")),
    "vermelho": ("Vermelho", ("#b42328", "#931c20", "#fbe9ea", "#d33a40", "#d33a40"),
                             ("#ef6b6f", "#f38588", "#3a1718", "#f38588", "#e45b60")),
    "laranja": ("Laranja", ("#a84d08", "#8a3f06", "#fdf0e4", "#e07a1f", "#e07a1f"),
                           ("#f0973f", "#f4a95e", "#3a2612", "#f4a95e", "#e8893a")),
    "grafite": ("Grafite", ("#374151", "#1f2937", "#eceef1", "#4b5563", "#4b5563"),
                           ("#a5b0bf", "#bcc5d1", "#262b33", "#bcc5d1", "#8b97a8")),
}
PADRAO = "azul"
CLARO_TEXTO, ESCURO_TEXTO = "#ffffff", "#111418"


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
    return CLARO_TEXTO if contraste(fundo, CLARO_TEXTO) >= contraste(fundo, ESCURO_TEXTO) else ESCURO_TEXTO


def opcoes() -> list[tuple[str, str, str, str]]:
    """(chave, nome, amostra no modo claro, amostra no modo escuro) para o seletor na tela."""
    return [(chave, nome, claro[0], escuro[0]) for chave, (nome, claro, escuro) in PALETAS.items()]


def _vars(cores: tuple) -> str:
    primaria, hover, suave, foco, serie = cores
    return (f"--primaria: {primaria}; --primaria-hover: {hover}; --primaria-suave: {suave}; "
            f"--foco: {foco}; --serie: {serie}; --sobre-primaria: {texto_sobre(primaria)};")


def gerar_css() -> str:
    linhas = [
        "/* GERADO por app/temas.py (python -m app.temas). Não edite à mão. */",
        "/* Cor de destaque escolhida no botão 🎨: data-cor no <html>. Sem data-cor = azul (padrão). */",
        "",
        f":root {{ {_vars(PALETAS[PADRAO][1])} }}",
        "@media (prefers-color-scheme: dark) {",
        f"  :root:not([data-theme=\"light\"]) {{ {_vars(PALETAS[PADRAO][2])} }}",
        "}",
        f":root[data-theme=\"dark\"] {{ {_vars(PALETAS[PADRAO][2])} }}",
    ]
    for chave, (_nome, claro, escuro) in PALETAS.items():
        if chave == PADRAO:
            continue
        linhas += [
            "",
            f":root[data-cor=\"{chave}\"]:not([data-theme=\"dark\"]) {{ {_vars(claro)} }}",
            "@media (prefers-color-scheme: dark) {",
            f"  :root[data-cor=\"{chave}\"]:not([data-theme=\"light\"]) {{ {_vars(escuro)} }}",
            "}",
            f":root[data-cor=\"{chave}\"][data-theme=\"dark\"] {{ {_vars(escuro)} }}",
        ]
    return "\n".join(linhas) + "\n"


CAMINHO_CSS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "cores.css")

if __name__ == "__main__":
    with open(CAMINHO_CSS, "w", encoding="utf-8", newline="\n") as f:
        f.write(gerar_css())
    for chave, (nome, claro, escuro) in PALETAS.items():
        print(f"{nome:10} claro: botão {contraste(claro[0], texto_sobre(claro[0])):.1f}:1, "
              f"link sobre branco {contraste(claro[0], '#ffffff'):.1f}:1 | "
              f"escuro: botão {contraste(escuro[0], texto_sobre(escuro[0])):.1f}:1, "
              f"link sobre fundo {contraste(escuro[0], '#1b1e22'):.1f}:1")
    print("gerado:", CAMINHO_CSS)
