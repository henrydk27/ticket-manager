"""SLA dos chamados da T.I (padrão ITIL): dois relógios contados só no expediente.

- Primeiro atendimento: da abertura até a T.I assumir, mudar o status ou comentar.
- Solução: da abertura até "Fechado". Pausa em "Aguardando usuário" (e enquanto está fechado:
  se reabrir, retoma de onde parou).

A meta vem da tabela de metas (categoria x prioridade, editável pelo administrador) e fica
gravada no chamado. Chamados antigos e de outros setores ficam sem SLA (sla_inicio vazio).
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .expediente import EXPEDIENTE_FIM, EXPEDIENTE_INICIO, segundos_expediente, somar_expediente
from .modelos import (CATEGORIA_INCIDENTE, CATEGORIA_PROBLEMA, CATEGORIA_SOLICITACAO, CATEGORIAS, PRIORIDADES,
                      SETOR_TI, STATUS_AGUARDANDO, STATUS_FECHADO, Chamado, MetaSla, Usuario, agora)

SETOR_SLA = SETOR_TI
MIN_DIA_UTIL = (EXPEDIENTE_FIM - EXPEDIENTE_INICIO) * 60      # 11 h = 660 min
RISCO = 0.75                                                  # a partir de 75% do prazo usado: "em risco"
STATUS_PAUSA = {STATUS_AGUARDANDO, STATUS_FECHADO}

# (primeiro atendimento, solução) em minutos de expediente; None = sem SLA
METAS_PADRAO = {
    (CATEGORIA_INCIDENTE, "Alta"): (30, 4 * 60),
    (CATEGORIA_INCIDENTE, "Média"): (2 * 60, MIN_DIA_UTIL),
    (CATEGORIA_INCIDENTE, "Baixa"): (4 * 60, 3 * MIN_DIA_UTIL),
    (CATEGORIA_SOLICITACAO, "Alta"): (60, MIN_DIA_UTIL),
    (CATEGORIA_SOLICITACAO, "Média"): (4 * 60, 3 * MIN_DIA_UTIL),
    (CATEGORIA_SOLICITACAO, "Baixa"): (MIN_DIA_UTIL, 5 * MIN_DIA_UTIL),
    (CATEGORIA_PROBLEMA, "Alta"): (None, None),
    (CATEGORIA_PROBLEMA, "Média"): (None, None),
    (CATEGORIA_PROBLEMA, "Baixa"): (None, None),
}

ATENDIMENTO, SOLUCAO = "atendimento", "solucao"
NOMES = {ATENDIMENTO: "Primeiro atendimento", SOLUCAO: "Solução"}


# ─── METAS ──────────────────────────────────────────────────────────────────

def metas(s: Session) -> dict[tuple[str, str], tuple[int | None, int | None]]:
    """Metas em vigor: as gravadas pelo administrador, ou as padrão."""
    m = dict(METAS_PADRAO)
    for x in s.scalars(select(MetaSla)):
        if (x.categoria, x.prioridade) in m:
            m[(x.categoria, x.prioridade)] = (x.atendimento_min, x.solucao_min)
    return m


def ler_horas(texto: str) -> int | None:
    """"0,5" ou "4" (horas de expediente) → minutos. Vazio = sem SLA."""
    texto = (texto or "").strip().replace(",", ".")
    if not texto:
        return None
    try:
        h = float(texto)
    except ValueError:
        raise ValueError(f"\"{texto}\" não é um número de horas.") from None
    if h <= 0 or h > 2000:
        raise ValueError("Use um número de horas maior que zero (ou deixe vazio para não ter SLA).")
    return round(h * 60)


def salvar_metas(s: Session, valores: dict[tuple[str, str], tuple[int | None, int | None]]) -> None:
    """Grava a tabela inteira. Vale para os chamados abertos daqui em diante (e os reclassificados)."""
    for (cat, prio), (at, sol) in valores.items():
        if (cat, prio) not in METAS_PADRAO:
            continue
        if at is not None and sol is not None and at > sol:
            raise ValueError(f"{cat} – {prio}: o primeiro atendimento não pode ter prazo maior que a solução.")
        x = s.scalar(select(MetaSla).where(MetaSla.categoria == cat, MetaSla.prioridade == prio))
        if x is None:
            x = MetaSla(categoria=cat, prioridade=prio)
            s.add(x)
        x.atendimento_min, x.solucao_min = at, sol
    s.commit()


# ─── LIGAR, RECALCULAR E MARCAR EVENTOS ─────────────────────────────────────

def aplica(c: Chamado) -> bool:
    return c.setor_destino == SETOR_SLA


def _aplicar_metas(s: Session, c: Chamado) -> None:
    c.sla_atendimento_min, c.sla_solucao_min = metas(s).get((c.categoria, c.prioridade), (None, None))
    c.sla_aviso_atendimento = c.sla_aviso_solucao = 0


def iniciar(s: Session, c: Chamado, momento: datetime | None = None) -> None:
    """Chamado aberto para a T.I (ou encaminhado para ela): liga os relógios."""
    if not aplica(c):
        return
    c.sla_inicio = momento or c.aberto_em or agora()
    c.primeiro_atendimento_em = c.pausado_em = None
    c.pausa_segundos = 0
    _aplicar_metas(s, c)


def desligar(c: Chamado) -> None:
    """Encaminhado para fora da T.I: o chamado deixa de ter SLA."""
    c.sla_inicio = c.sla_atendimento_min = c.sla_solucao_min = None
    c.primeiro_atendimento_em = c.pausado_em = None
    c.pausa_segundos = c.sla_aviso_atendimento = c.sla_aviso_solucao = 0


def recalcular(s: Session, c: Chamado) -> None:
    """Categoria ou prioridade mudou: troca as metas (os relógios continuam de onde estão)."""
    if c.sla_inicio is not None:
        _aplicar_metas(s, c)


def mudou_status(c: Chamado, anterior: str, novo: str, momento: datetime | None = None) -> None:
    """Pausa ao entrar em "Aguardando usuário" ou "Fechado"; retoma ao sair."""
    if c.sla_inicio is None:
        return
    momento = momento or agora()
    if anterior in STATUS_PAUSA and novo not in STATUS_PAUSA and c.pausado_em:
        c.pausa_segundos = (c.pausa_segundos or 0) + round(segundos_expediente(c.pausado_em, momento))
        c.pausado_em = None
    elif novo in STATUS_PAUSA and anterior not in STATUS_PAUSA:
        c.pausado_em = momento


def atendeu(c: Chamado, autor: Usuario, momento: datetime | None = None) -> None:
    """Primeira ação de quem atende (assumir, mudar status ou comentar) para o relógio do atendimento."""
    if (c.sla_inicio is not None and c.primeiro_atendimento_em is None
            and autor.id != c.solicitante_id and autor.trabalha_em(c)):
        c.primeiro_atendimento_em = momento or agora()


# ─── SITUAÇÃO DOS RELÓGIOS ──────────────────────────────────────────────────

@dataclass
class Relogio:
    tipo: str                    # ATENDIMENTO ou SOLUCAO
    meta: int                    # segundos de expediente
    usado: float                 # segundos de expediente já gastos
    estado: str                  # ok, risco, estourado, pausado (em curso) · cumprido, violado (encerrado)
    prazo: datetime | None       # quando estoura, se continuar correndo (None se encerrado ou pausado)

    @property
    def nome(self) -> str:
        return NOMES[self.tipo]

    @property
    def restante(self) -> float:
        return self.meta - self.usado

    @property
    def pct(self) -> float:
        return 100 * self.usado / self.meta if self.meta else 0

    @property
    def em_curso(self) -> bool:
        return self.estado in ("ok", "risco", "estourado", "pausado")

    @property
    def dentro(self) -> bool:
        return self.usado <= self.meta

    @property
    def classe(self) -> str:
        """Cor do selo: normal, risco ou estourado."""
        if not self.dentro:
            return "estourado"
        return "risco" if self.estado == "risco" else "normal"


def _estado_em_curso(usado: float, meta: int) -> str:
    if usado > meta:
        return "estourado"
    return "risco" if usado >= RISCO * meta else "ok"


def relogio_atendimento(c: Chamado, momento: datetime | None = None) -> Relogio | None:
    if c.sla_inicio is None or not c.sla_atendimento_min:
        return None
    meta = c.sla_atendimento_min * 60
    fim = c.primeiro_atendimento_em or (c.fechado_em if c.status == STATUS_FECHADO else None)
    if fim is not None:
        usado = segundos_expediente(c.sla_inicio, fim)
        return Relogio(ATENDIMENTO, meta, usado, "cumprido" if usado <= meta else "violado", None)
    usado = segundos_expediente(c.sla_inicio, momento or agora())
    return Relogio(ATENDIMENTO, meta, usado, _estado_em_curso(usado, meta), somar_expediente(c.sla_inicio, meta))


def relogio_solucao(c: Chamado, momento: datetime | None = None) -> Relogio | None:
    if c.sla_inicio is None or not c.sla_solucao_min:
        return None
    meta = c.sla_solucao_min * 60
    agora_ = momento or agora()
    ate = c.pausado_em or (c.fechado_em if c.status == STATUS_FECHADO else None) or agora_
    usado = max(0.0, segundos_expediente(c.sla_inicio, ate) - (c.pausa_segundos or 0))
    if c.status == STATUS_FECHADO:
        return Relogio(SOLUCAO, meta, usado, "cumprido" if usado <= meta else "violado", None)
    if c.pausado_em is not None:
        return Relogio(SOLUCAO, meta, usado, "estourado" if usado > meta else "pausado", None)
    prazo = somar_expediente(agora_, meta - usado) if usado <= meta else None
    return Relogio(SOLUCAO, meta, usado, _estado_em_curso(usado, meta), prazo)


def relogios(c: Chamado, momento: datetime | None = None) -> list[Relogio]:
    return [r for r in (relogio_atendimento(c, momento), relogio_solucao(c, momento)) if r]


def principal(c: Chamado, momento: datetime | None = None) -> Relogio | None:
    """O relógio que importa agora (selo da lista): o mais apertado entre os que estão correndo;
    num chamado encerrado, a solução."""
    rs = relogios(c, momento)
    correndo = [r for r in rs if r.em_curso]
    if correndo:
        return max(correndo, key=lambda r: (r.estado != "pausado", r.pct))
    return next((r for r in rs if r.tipo == SOLUCAO), None)


def estado_geral(c: Chamado, momento: datetime | None = None) -> str | None:
    """Pior situação entre os relógios em curso: estourado, risco ou ok (None = sem SLA correndo)."""
    estados = {r.estado for r in relogios(c, momento) if r.em_curso}
    for e in ("estourado", "risco"):
        if e in estados:
            return e
    return "ok" if estados else None


def texto(segundos: float) -> str:
    """Tempo de expediente: "45 min", "3 h 20 min" ou "2 d 4 h" (dia útil = 11 h)."""
    minutos = max(0, round(abs(segundos) / 60))
    d, resto = divmod(minutos, MIN_DIA_UTIL)
    h, m = divmod(resto, 60)
    if d:
        return f"{d} d {h} h" if h else f"{d} d"
    if h:
        return f"{h} h {m} min" if m else f"{h} h"
    return f"{m} min"


ROTULOS = {"ok": "Em curso", "risco": "Em risco", "estourado": "Estourado", "pausado": "Pausado",
           "cumprido": "No prazo", "violado": "Fora do prazo"}


def rotulo(r: Relogio | None) -> str:
    """Situação do relógio para o relatório (vazio = sem SLA)."""
    return ROTULOS.get(r.estado, "") if r else ""


def texto_meta(minutos: int | None) -> str:
    return "sem SLA" if not minutos else texto(minutos * 60)


# ─── ALERTAS (manage.py verificar-sla) ──────────────────────────────────────

NIVEL_RISCO, NIVEL_ESTOURADO = 1, 2


def alertas(s: Session, momento: datetime | None = None) -> list[tuple[Chamado, Relogio, int]]:
    """Relógios que chegaram a 75% ou estouraram e ainda não foram avisados: (chamado, relógio, nível)."""
    momento = momento or agora()
    saida = []
    abertos = s.scalars(select(Chamado).where(Chamado.status != STATUS_FECHADO,
                                              Chamado.sla_inicio.is_not(None))).unique()
    for c in abertos:
        for r, campo in ((relogio_atendimento(c, momento), "sla_aviso_atendimento"),
                         (relogio_solucao(c, momento), "sla_aviso_solucao")):
            if r is None or r.estado not in ("risco", "estourado"):
                continue
            nivel = NIVEL_ESTOURADO if r.estado == "estourado" else NIVEL_RISCO
            if (getattr(c, campo) or 0) < nivel:
                saida.append((c, r, nivel))
    return saida


def marcar_aviso(c: Chamado, r: Relogio, nivel: int) -> None:
    campo = "sla_aviso_atendimento" if r.tipo == ATENDIMENTO else "sla_aviso_solucao"
    setattr(c, campo, max(nivel, getattr(c, campo) or 0))


# ─── INDICADORES ────────────────────────────────────────────────────────────

def percentual(rs: list[Relogio | None]) -> tuple[float | None, int]:
    """(% dentro do prazo, quantos relógios contaram)."""
    rs = [r for r in rs if r is not None]
    if not rs:
        return None, 0
    return 100 * sum(1 for r in rs if r.dentro) / len(rs), len(rs)


def resumo(encerrados: list[Chamado], abertos: list[Chamado], momento: datetime | None = None) -> dict:
    """% no prazo dos encerrados (atendimento e solução) e os abertos em risco/estourados."""
    momento = momento or agora()
    com_sla = [c for c in encerrados if c.sla_inicio is not None]
    at, n_at = percentual([relogio_atendimento(c) for c in com_sla])
    sol, n_sol = percentual([relogio_solucao(c) for c in com_sla])
    estados = [estado_geral(c, momento) for c in abertos if c.sla_inicio is not None]

    def linhas(chave, ordem):
        grupos = {}
        for c in com_sla:
            grupos.setdefault(chave(c), []).append(c)
        saida = []
        for nome in ordem + sorted(k for k in grupos if k not in ordem):
            cs = grupos.get(nome)
            if not cs:
                continue
            p_at, _ = percentual([relogio_atendimento(c) for c in cs])
            p_sol, _ = percentual([relogio_solucao(c) for c in cs])
            saida.append({"nome": nome, "total": len(cs), "atendimento": p_at, "solucao": p_sol})
        return saida

    return {
        "encerrados": len(com_sla), "atendimento": at, "n_atendimento": n_at, "solucao": sol, "n_solucao": n_sol,
        "em_risco": estados.count("risco"), "estourados": estados.count("estourado"),
        "por_prioridade": linhas(lambda c: c.prioridade, PRIORIDADES),
        "por_categoria": linhas(lambda c: c.categoria or "Sem categoria", CATEGORIAS),
        "por_responsavel": sorted(linhas(lambda c: c.responsavel.nome if c.responsavel else "Sem responsável", []),
                                  key=lambda x: -x["total"])[:8],
    }
