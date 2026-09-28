"""Filtros de template para exibir datas, tamanhos e status."""

from datetime import date, datetime

from markupsafe import Markup, escape


def data(v) -> str:
    return v.strftime("%d/%m/%Y") if isinstance(v, (date, datetime)) else ("" if v is None else str(v))


def data_hora(v) -> str:
    return v.strftime("%d/%m/%Y %H:%M") if isinstance(v, datetime) else data(v)


def tamanho(n) -> str:
    n = n or 0
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


def duracao(v) -> str:
    """Duração em dias (float) como "2 d 4 h", "3 h 20 min" ou "45 min"."""
    if v is None:
        return "—"
    minutos = max(0, round(float(v) * 24 * 60))
    d, resto = divmod(minutos, 24 * 60)
    h, m = divmod(resto, 60)
    if d:
        return f"{d} d {h} h" if h else f"{d} d"
    if h:
        return f"{h} h {m} min" if m else f"{h} h"
    return f"{m} min"


_CLASSE_STATUS = {
    "Aberto": "aberto",
    "Em andamento": "andamento",
    "Aguardando usuário": "aguardando",
    "Fechado": "fechado",
}


def status(v) -> Markup:
    classe = _CLASSE_STATUS.get(v or "", "outro")
    return Markup(f'<span class="badge badge-{classe}">{escape(v or "—")}</span>')


def prioridade(v) -> Markup:
    classe = {"Alta": "alta", "Média": "media", "Baixa": "baixa"}.get(v or "", "outro")
    return Markup(f'<span class="prio prio-{classe}">{escape(v or "—")}</span>')


def registrar(app) -> None:
    for nome in ("data", "data_hora", "tamanho", "duracao", "status", "prioridade"):
        app.jinja_env.filters[nome] = globals()[nome]
