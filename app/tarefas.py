"""Tarefas recorrentes da T.I (conferir backups, trocar senha do Wi-Fi...): cadastro, próxima data,
conclusão com histórico e lembrete diário por e-mail.

Administradores e quem atende a T.I veem, cadastram e concluem; só o administrador apaga.
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .modelos import Tarefa, TarefaExecucao, Usuario
from .preventivas import somar_meses
from .servicos import ErroValidacao

REPETICOES = {"mensal": "Todo mês", "semanal": "Toda semana", "meses": "A cada N meses", "unica": "Uma vez só"}
DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
VENCE_EM_BREVE_DIAS = 7
ESTADOS = {"atrasada": "Atrasadas", "hoje": "Para hoje", "vence": "Vencem em breve", "em_dia": "Em dia",
           "concluida": "Concluídas"}


# ─── datas ──────────────────────────────────────────────────────────────────

def _dia_do_mes(ano: int, mes: int, dia: int) -> date:
    """Dia do mês, usando o último dia quando o mês é mais curto (dia 31 em fevereiro → 28/29)."""
    return date(ano, mes, min(dia, calendar.monthrange(ano, mes)[1]))


def primeira_ocorrencia(t: Tarefa, a_partir: date) -> date:
    """Primeira data da tarefa em ou depois de `a_partir`."""
    if t.repeticao == "mensal":
        d = _dia_do_mes(a_partir.year, a_partir.month, t.dia_mes)
        if d < a_partir:
            prox = somar_meses(a_partir.replace(day=1), 1)
            d = _dia_do_mes(prox.year, prox.month, t.dia_mes)
        return d
    if t.repeticao == "semanal":
        return a_partir + timedelta(days=(t.dia_semana - a_partir.weekday()) % 7)
    return a_partir                                    # "meses" e "unica": a própria data de início


def seguinte(t: Tarefa, d: date) -> date | None:
    """Ocorrência depois de `d` (None para tarefa de uma vez só)."""
    if t.repeticao == "mensal":
        prox = somar_meses(d.replace(day=1), 1)
        return _dia_do_mes(prox.year, prox.month, t.dia_mes)
    if t.repeticao == "semanal":
        return d + timedelta(days=7)
    if t.repeticao == "meses":
        return somar_meses(d, t.intervalo_meses or 1)
    return None


def descricao_repeticao(t: Tarefa) -> str:
    if t.repeticao == "mensal":
        return f"Todo dia {t.dia_mes}" + (" (ou o último dia do mês)" if t.dia_mes > 28 else "")
    if t.repeticao == "semanal":
        return f"Toda {DIAS_SEMANA[t.dia_semana]}" if t.dia_semana < 5 else f"Todo {DIAS_SEMANA[t.dia_semana]}"
    if t.repeticao == "meses":
        n = t.intervalo_meses or 1
        return {1: "Todo mês", 3: "A cada 3 meses (trimestral)", 6: "A cada 6 meses (semestral)",
                12: "Todo ano"}.get(n, f"A cada {n} meses")
    return "Uma vez só"


@dataclass
class Situacao:
    tarefa: Tarefa
    estado: str
    dias: int | None          # dias até a próxima (negativo = atrasada)
    ultima: TarefaExecucao | None


def situacao(t: Tarefa, hoje: date | None = None) -> Situacao:
    hoje = hoje or date.today()
    ultima = t.execucoes[0] if t.execucoes else None
    if not t.ativa or t.proxima is None:
        return Situacao(t, "concluida", None, ultima)
    dias = (t.proxima - hoje).days
    estado = ("atrasada" if dias < 0 else "hoje" if dias == 0
              else "vence" if dias <= max(VENCE_EM_BREVE_DIAS, t.avisar_dias or 0) else "em_dia")
    return Situacao(t, estado, dias, ultima)


# ─── consultas ──────────────────────────────────────────────────────────────

def _todas(s: Session) -> list[Tarefa]:
    return list(s.scalars(select(Tarefa).options(selectinload(Tarefa.execucoes))
                          .order_by(Tarefa.proxima, func.lower(Tarefa.titulo))).unique())


def listar(s: Session, estado: str = "") -> tuple[list[Situacao], dict[str, int]]:
    hoje = date.today()
    todas = [situacao(t, hoje) for t in _todas(s)]
    contagem = {k: sum(1 for x in todas if x.estado == k) for k in ESTADOS}
    if estado in ESTADOS:
        lista = [x for x in todas if x.estado == estado]
    else:
        lista = [x for x in todas if x.estado != "concluida"]
    lista.sort(key=lambda x: (x.tarefa.proxima is None, x.tarefa.proxima or date.max))
    return lista, contagem


def obter(s: Session, tarefa_id: int) -> Tarefa | None:
    return s.get(Tarefa, tarefa_id)


def equipe_ti(s: Session) -> list[Usuario]:
    """Administradores e quem atende a T.I (quem pode ser responsável por tarefas)."""
    ativos = s.scalars(select(Usuario).where(Usuario.ativo).order_by(func.lower(Usuario.nome))).unique()
    return [u for u in ativos if u.faz_preventiva]


# ─── cadastro e conclusão ───────────────────────────────────────────────────

def _inteiro(valor, nome: str, minimo: int, maximo: int) -> int:
    try:
        n = int(valor)
    except (TypeError, ValueError):
        raise ErroValidacao(f"{nome}: informe um número.") from None
    if not minimo <= n <= maximo:
        raise ErroValidacao(f"{nome}: use de {minimo} a {maximo}.")
    return n


def salvar(s: Session, atual: Tarefa | None, dados: dict, autor: Usuario) -> Tarefa:
    titulo = " ".join((dados.get("titulo") or "").split())
    if not titulo or len(titulo) > 150:
        raise ErroValidacao("Informe o título da tarefa (até 150 caracteres).")
    repeticao = dados.get("repeticao") or ""
    if repeticao not in REPETICOES:
        raise ErroValidacao("Escolha como a tarefa se repete.")
    try:
        inicio = date.fromisoformat((dados.get("inicio") or "").strip())
    except ValueError:
        raise ErroValidacao("Informe a data de início (ou a data, se for uma vez só).") from None

    t = atual or Tarefa(criado_por_id=autor.id)
    t.titulo = titulo
    t.descricao = (dados.get("descricao") or "").strip()[:4000] or None
    t.repeticao = repeticao
    t.dia_mes = _inteiro(dados.get("dia_mes") or inicio.day, "Dia do mês", 1, 31) if repeticao == "mensal" else None
    t.dia_semana = (_inteiro(dados.get("dia_semana") or inicio.weekday(), "Dia da semana", 0, 6)
                    if repeticao == "semanal" else None)
    t.intervalo_meses = _inteiro(dados.get("intervalo_meses") or 1, "A cada quantos meses", 1, 60) \
        if repeticao == "meses" else None
    t.avisar_dias = _inteiro(dados.get("avisar_dias") or 0, "Avisar quantos dias antes", 0, 60)
    resp = str(dados.get("responsavel_id") or "")
    if resp:
        u = s.get(Usuario, int(resp)) if resp.isdigit() else None
        if u is None or not u.faz_preventiva:
            raise ErroValidacao("O responsável precisa ser administrador ou atender a T.I.")
        t.responsavel_id = u.id
    else:
        t.responsavel_id = None                         # toda a T.I
    # mudou a data ou a repetição: recalcula a próxima a partir do início
    if atual is None or t.inicio != inicio or dados.get("recalcular") or not t.ativa:
        t.inicio = inicio
        t.proxima = primeira_ocorrencia(t, inicio)
        t.ativa = True
    if atual is None:
        s.add(t)
    s.commit()
    return t


def concluir(s: Session, t: Tarefa, usuario: Usuario, observacao: str = "") -> TarefaExecucao:
    """Registra que a tarefa foi feita e calcula a próxima data (pulando as que ficaram para trás)."""
    if not t.ativa or t.proxima is None:
        raise ErroValidacao("Esta tarefa já foi concluída.")
    e = TarefaExecucao(tarefa=t, usuario_id=usuario.id, data_prevista=t.proxima,
                       observacao=(observacao or "").strip()[:2000] or None)
    s.add(e)
    hoje = date.today()
    prox = seguinte(t, t.proxima)
    while prox is not None and prox <= hoje:
        prox = seguinte(t, prox)
    if prox is None:
        t.ativa, t.proxima = False, None
    else:
        t.proxima = prox
    s.commit()
    return e


def apagar(s: Session, t: Tarefa) -> None:
    s.delete(t)
    s.commit()


# ─── avisos por e-mail ──────────────────────────────────────────────────────

def avisos_do_dia(s: Session, hoje: date | None = None) -> dict[Usuario, list[Situacao]]:
    """O que cada pessoa precisa ver hoje: atrasadas, as de hoje e as que estão no prazo de aviso.

    Tarefa com responsável vai só para ele; "toda a T.I" vai para todos da equipe.
    """
    hoje = hoje or date.today()
    equipe = [u for u in equipe_ti(s) if u.email]
    destino: dict[Usuario, list[Situacao]] = {}
    for t in _todas(s):
        x = situacao(t, hoje)
        if x.estado == "concluida":
            continue
        no_aviso = t.avisar_dias and 0 < x.dias <= t.avisar_dias
        if not (x.estado in ("atrasada", "hoje") or no_aviso):
            continue
        pessoas = [t.responsavel] if t.responsavel else equipe
        for u in pessoas:
            if u and u.ativo and u.email:
                destino.setdefault(u, []).append(x)
    return destino


def atrasadas(s: Session) -> list[Situacao]:
    return [x for x in (situacao(t) for t in _todas(s)) if x.estado == "atrasada"]
