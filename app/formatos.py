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


def dias(v) -> str:
    """Duração em dias (float) como texto legível."""
    if not v:
        return "—"
    horas = float(v) * 24
    if horas < 24:
        return f"{horas:.1f} h".replace(".", ",")
    return f"{float(v):.1f} dias".replace(".", ",")


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
    for nome in ("data", "data_hora", "tamanho", "dias", "status", "prioridade"):
        app.jinja_env.filters[nome] = globals()[nome]
