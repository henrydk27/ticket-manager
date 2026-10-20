"""Revisão preventiva dos ativos: planos por tipo, vencimentos, registro e chamado automático.

- Cada tipo tem um plano (a cada N meses + checklist); o admin ajusta em Preventivas → Planos.
  Um equipamento pode ter a própria periodicidade (Equipamento.preventiva_meses).
- Só equipamentos "Em uso" entram na conta. A próxima preventiva é a data da última (ou do
  cadastro, se nunca teve) mais o período do plano.
- Item marcado como "Problema" abre um chamado para a T.I automaticamente.
"""

import calendar
import json
from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from . import anexos as arquivos_disco
from .anexos import Arquivo
from .modelos import (PLANOS_PADRAO, PRIORIDADES, RESULTADO_PROBLEMA, RESULTADOS_ITEM, SETOR_TI, SITUACAO_USO,
                      TIPOS_EQUIPAMENTO, Equipamento, MovimentoEquipamento, PlanoPreventiva, Preventiva, Usuario,
                      agora)
from .servicos import ErroValidacao, _escapar_like

AVISO_DIAS = 15                      # "vence em breve": até 15 dias antes
MESES_OPCOES = [1, 2, 3, 4, 6, 12, 24]

# estado da preventiva de um equipamento
ESTADOS = {"atrasada": "Atrasadas", "vence": f"Vencem em {AVISO_DIAS} dias", "em_dia": "Em dia",
           "sem_plano": "Sem preventiva"}


# ─── planos ─────────────────────────────────────────────────────────────────

@dataclass
class Plano:
    tipo: str
    meses: int
    itens: list[str]


def planos(s: Session) -> dict[str, Plano]:
    """Plano de cada tipo: o salvo pelo admin ou o padrão."""
    salvos = {p.tipo: p for p in s.scalars(select(PlanoPreventiva))}
    resultado = {}
    for tipo in TIPOS_EQUIPAMENTO:
        if tipo in salvos:
            p = salvos[tipo]
            resultado[tipo] = Plano(tipo, p.meses, [i for i in (p.itens or "").splitlines() if i.strip()])
        else:
            meses, itens = PLANOS_PADRAO.get(tipo, (0, []))
            resultado[tipo] = Plano(tipo, meses, list(itens))
    return resultado


def salvar_planos(s: Session, dados: dict[str, tuple[str, str]]) -> None:
    """dados: {tipo: (meses, itens um por linha)}. Tudo ou nada."""
    for tipo, (meses, itens) in dados.items():
        if tipo not in TIPOS_EQUIPAMENTO:
            continue
        try:
            n = int(meses or 0)
        except ValueError:
            raise ErroValidacao(f"{tipo}: periodicidade inválida.") from None
        if n < 0 or n > 60:
            raise ErroValidacao(f"{tipo}: use de 0 (sem preventiva) a 60 meses.")
        linhas = [" ".join(i.split())[:150] for i in (itens or "").splitlines() if i.strip()]
        if n and not linhas:
            raise ErroValidacao(f"{tipo}: informe pelo menos um item do checklist (ou 0 meses).")
        if len(linhas) > 40:
            raise ErroValidacao(f"{tipo}: no máximo 40 itens.")
        p = s.get(PlanoPreventiva, tipo) or PlanoPreventiva(tipo=tipo)
        p.meses, p.itens = n, "\n".join(linhas)
        s.add(p)
    s.commit()


# ─── vencimentos ────────────────────────────────────────────────────────────

def somar_meses(d: date, meses: int) -> date:
    total = d.year * 12 + d.month - 1 + meses
    ano, mes = divmod(total, 12)
    return date(ano, mes + 1, min(d.day, calendar.monthrange(ano, mes + 1)[1]))


@dataclass
class Situacao:
    eq: Equipamento
    meses: int
    ultima: Preventiva | None
    proxima: date | None
    estado: str              # chave de ESTADOS
    dias: int | None         # dias até a próxima (negativo = atrasada)


def situacao(eq: Equipamento, todos_planos: dict[str, Plano], hoje: date | None = None) -> Situacao:
    hoje = hoje or date.today()
    if eq.preventiva_meses is not None:
        meses = eq.preventiva_meses
    else:
        meses = todos_planos[eq.tipo].meses if eq.tipo in todos_planos else 0
    ultima = eq.preventivas[0] if eq.preventivas else None
    if eq.situacao != SITUACAO_USO or not meses:
        return Situacao(eq, meses, ultima, None, "sem_plano", None)
    base = ultima.data if ultima else eq.criado_em.date()
    proxima = somar_meses(base, meses)
    dias = (proxima - hoje).days
    estado = "atrasada" if dias < 0 else ("vence" if dias <= AVISO_DIAS else "em_dia")
    return Situacao(eq, meses, ultima, proxima, estado, dias)


@dataclass
class Filtros:
    texto: str = ""
    setor: str = ""
    tipo: str = ""
    estado: str = ""          # "" = atrasadas + vencem em breve + em dia (sem as que não têm preventiva)


def listar(s: Session, f: Filtros) -> tuple[list[Situacao], dict[str, int]]:
    """Equipamentos com a situação da preventiva (mais urgentes primeiro) e a contagem por estado."""
    cond = []
    if f.texto:
        termo = f"%{_escapar_like(f.texto.strip())}%"
        cond.append(or_(*(c.ilike(termo, escape="\\") for c in (
            Equipamento.patrimonio, Equipamento.marca, Equipamento.modelo, Equipamento.hostname, Usuario.nome))))
    if f.setor:
        cond.append(Equipamento.setor == f.setor)
    if f.tipo:
        cond.append(Equipamento.tipo == f.tipo)
    consulta = (select(Equipamento).outerjoin(Usuario, Usuario.id == Equipamento.usuario_id).where(*cond)
                .options(selectinload(Equipamento.preventivas)))
    todos_planos = planos(s)
    hoje = date.today()
    todas = [situacao(e, todos_planos, hoje) for e in s.scalars(consulta).unique()]
    contagem = {k: sum(1 for x in todas if x.estado == k) for k in ESTADOS}
    if f.estado in ESTADOS:
        lista = [x for x in todas if x.estado == f.estado]
    else:
        lista = [x for x in todas if x.estado != "sem_plano"]
    lista.sort(key=lambda x: (x.proxima is None, x.proxima or date.max, x.eq.patrimonio_ordem))
    return lista, contagem


def pendentes(s: Session) -> list[Situacao]:
    """Atrasadas e que vencem em breve (para o e-mail semanal)."""
    lista, _ = listar(s, Filtros())
    return [x for x in lista if x.estado in ("atrasada", "vence")]


# ─── registro ───────────────────────────────────────────────────────────────

@dataclass
class Registro:
    preventiva: Preventiva
    chamado: object | None       # chamado aberto por causa de um problema
    sem_atendente: bool          # havia problema, mas ninguém atende a T.I para receber o chamado


def _responsavel_ti(s: Session, tecnico: Usuario) -> Usuario | None:
    from .servicos import atendentes_do_setor
    if tecnico.ativo and tecnico.atende and tecnico.setor == SETOR_TI:
        return tecnico
    lista = atendentes_do_setor(s, SETOR_TI)
    return lista[0] if lista else None


def registrar(s: Session, eq: Equipamento, tecnico: Usuario, data_txt: str, resultados: dict[str, str],
              notas: dict[str, str], pecas: str, observacoes: str, arquivo: Arquivo | None) -> Registro:
    """Grava a preventiva, registra no histórico e, se houver item com problema, abre um chamado."""
    from . import servicos

    if not tecnico.faz_preventiva:
        raise ErroValidacao("Só administradores e quem atende a T.I registram preventivas.")
    try:
        quando = date.fromisoformat(data_txt or "")
    except ValueError:
        raise ErroValidacao("Informe a data da preventiva.") from None
    if quando > date.today():
        raise ErroValidacao("A data da preventiva não pode ser no futuro.")

    plano = planos(s).get(eq.tipo)
    itens_plano = plano.itens if plano else []
    linhas = []
    for item in itens_plano:
        r = resultados.get(item, "")
        if r not in RESULTADOS_ITEM:
            raise ErroValidacao(f"Marque o resultado de: {item}.")
        linhas.append([item, r, " ".join((notas.get(item) or "").split())[:300]])
    pecas, observacoes = (pecas or "").strip()[:2000] or None, (observacoes or "").strip()[:4000] or None
    if not linhas and not observacoes:
        raise ErroValidacao("Este tipo não tem checklist: descreva o que foi feito nas observações.")

    p = Preventiva(equipamento=eq, data=quando, tecnico_id=tecnico.id, pecas=pecas, observacoes=observacoes,
                   resultados=json.dumps(linhas, ensure_ascii=False))
    if arquivo is not None:
        p.anexo_arquivo = arquivos_disco.gravar(arquivo)
        p.anexo_nome, p.anexo_tipo, p.anexo_tamanho = arquivo.nome, arquivo.tipo[:100], len(arquivo.conteudo)
    s.add(p)
    problemas = [l for l in linhas if l[1] == RESULTADO_PROBLEMA]
    resumo = f"Preventiva de {quando:%d/%m/%Y}: " + ", ".join(
        f"{sum(1 for l in linhas if l[1] == r)} {r.lower()}" for r in RESULTADOS_ITEM
        if any(l[1] == r for l in linhas)) if linhas else f"Preventiva de {quando:%d/%m/%Y}."
    s.add(MovimentoEquipamento(equipamento=eq, autor_id=tecnico.id, descricao=resumo.rstrip(".") + "."))
    try:
        s.commit()
    except Exception:
        s.rollback()
        if p.anexo_arquivo:
            arquivos_disco.remover(p.anexo_arquivo)
        raise

    chamado, sem_atendente = None, False
    if problemas:
        responsavel = _responsavel_ti(s, tecnico)
        if responsavel is None:
            sem_atendente = True
        else:
            texto = "\n".join(f"- {item}" + (f": {nota}" if nota else "") for item, _r, nota in problemas)
            descricao = (f"Problemas encontrados na preventiva de {quando:%d/%m/%Y} do patrimônio {eq.patrimonio} "
                         f"({eq.tipo} {eq.descricao}"
                         + (f", setor {eq.setor}" if eq.setor else "")
                         + (f", com {eq.usuario.nome}" if eq.usuario else "") + "):\n\n" + texto
                         + (f"\n\nObservações: {observacoes}" if observacoes else ""))
            chamado = servicos.criar_chamado(
                s, tecnico, SETOR_TI, responsavel.id,
                f"Preventiva: problema no patrimônio {eq.patrimonio}"[:150], descricao, PRIORIDADES[1], [])
            p.chamado_id = chamado.id
            s.commit()
    return Registro(p, chamado, sem_atendente)


def obter(s: Session, preventiva_id: int) -> Preventiva | None:
    return s.get(Preventiva, preventiva_id)


def no_periodo(s: Session, inicio: date, fim: date) -> list[Preventiva]:
    return list(s.scalars(select(Preventiva).where(Preventiva.data >= inicio, Preventiva.data <= fim)
                          .order_by(Preventiva.data, Preventiva.id)))


def remover_anexos(eq: Equipamento) -> list[str]:
    """Arquivos das preventivas de um equipamento (para apagar do disco depois de excluir)."""
    return [p.anexo_arquivo for p in eq.preventivas if p.anexo_arquivo]

