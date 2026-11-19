"""Pesquisa de satisfação com a T.I, duas vezes por ano.

Abre sozinha no comando diário (manage.py avisos-diarios) a partir de 1º de junho e 1º de dezembro,
fica aberta PRAZO_DIAS dias e manda um lembrete a quem não respondeu. É identificada (guarda quem
respondeu) e só o administrador vê o resultado. Quem é da T.I (e os administradores) não responde.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import extract, select
from sqlalchemy.orm import Session, selectinload

from .modelos import SETOR_TI, Pesquisa, RespostaPesquisa, Usuario, agora
from .servicos import ErroValidacao

MESES = (6, 12)              # junho e dezembro
PRAZO_DIAS = 7               # aberta do dia da abertura até 6 dias depois (7 dias)
LEMBRETE_APOS_DIAS = 4       # lembrete a quem ainda não respondeu (3 dias antes de fechar)
RESOLVIDOS = {
    "todos": "Sim, todos",
    "maioria": "A maioria",
    "poucos": "Poucos ou nenhum",
    "nenhum": "Não abri chamados nesse período",
}
NOMES_MES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
             "outubro", "novembro", "dezembro"]


def participa(u: Usuario | None) -> bool:
    """Quem responde: contas ativas fora da T.I (a pesquisa avalia o atendimento da T.I)."""
    return bool(u and u.ativo and not u.is_admin and u.setor != SETOR_TI)


def participantes(s: Session) -> list[Usuario]:
    return [u for u in s.scalars(select(Usuario).where(Usuario.ativo).order_by(Usuario.nome)).unique() if participa(u)]


def aberta(s: Session, hoje: date | None = None) -> Pesquisa | None:
    hoje = hoje or date.today()
    p = s.scalar(select(Pesquisa).where(Pesquisa.encerrada_em.is_(None), Pesquisa.encerra_em >= hoje)
                 .order_by(Pesquisa.aberta_em.desc()).limit(1))
    return p


def listar(s: Session) -> list[Pesquisa]:
    return list(s.scalars(select(Pesquisa).options(selectinload(Pesquisa.respostas))
                          .order_by(Pesquisa.aberta_em.desc())).unique())


def obter(s: Session, pesquisa_id: int) -> Pesquisa | None:
    return s.get(Pesquisa, pesquisa_id)


def ja_respondeu(s: Session, p: Pesquisa, u: Usuario) -> bool:
    return s.scalar(select(RespostaPesquisa.id).where(RespostaPesquisa.pesquisa_id == p.id,
                                                      RespostaPesquisa.usuario_id == u.id)) is not None


def pendente_para(s: Session, u: Usuario | None) -> Pesquisa | None:
    """A pesquisa aberta que esta pessoa ainda precisa responder (None se não houver)."""
    if not participa(u):
        return None
    p = aberta(s)
    return p if p and not ja_respondeu(s, p, u) else None


def abrir(s: Session, autor: Usuario | None = None, hoje: date | None = None) -> Pesquisa:
    hoje = hoje or date.today()
    if aberta(s, hoje):
        raise ErroValidacao("Já existe uma pesquisa aberta.")
    p = Pesquisa(titulo=f"Pesquisa de satisfação da T.I – {NOMES_MES[hoje.month - 1]} de {hoje.year}",
                 aberta_em=agora(), encerra_em=hoje + timedelta(days=PRAZO_DIAS - 1),
                 convidados=len(participantes(s)), criado_por_id=autor.id if autor else None)
    s.add(p)
    s.commit()
    return p


def encerrar(s: Session, p: Pesquisa) -> None:
    if p.aberta():
        p.encerrada_em = agora()
        s.commit()


def responder(s: Session, p: Pesquisa, u: Usuario, dados) -> RespostaPesquisa:
    if not participa(u):
        raise ErroValidacao("Esta pesquisa é para quem usa o atendimento da T.I.")
    if not p.aberta():
        raise ErroValidacao("Esta pesquisa já foi encerrada.")
    if ja_respondeu(s, p, u):
        raise ErroValidacao("Você já respondeu esta pesquisa. Obrigado!")
    resolvidos = dados.get("resolvidos") or ""
    if resolvidos not in RESOLVIDOS:
        raise ErroValidacao("Responda se os seus chamados foram resolvidos.")
    nota = str(dados.get("nota") or "").strip()
    if not nota.isdigit() or not 0 <= int(nota) <= 10:
        raise ErroValidacao("Escolha uma nota de 0 a 10.")
    r = RespostaPesquisa(pesquisa=p, usuario_id=u.id, setor=u.setor, resolvidos=resolvidos, nota=int(nota),
                         comentario=(dados.get("comentario") or "").strip()[:4000] or None)
    s.add(r)
    s.commit()
    return r


# ─── resultado ──────────────────────────────────────────────────────────────

@dataclass
class Resultado:
    respostas: list[RespostaPesquisa]
    convidados: int
    media: float | None = None
    nps: int | None = None
    promotores: int = 0
    neutros: int = 0
    detratores: int = 0
    notas: list[int] = field(default_factory=lambda: [0] * 11)       # quantas respostas com cada nota 0..10
    resolvidos: list[tuple[str, int]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.respostas)

    @property
    def taxa(self) -> float | None:
        return 100 * self.total / self.convidados if self.convidados else None

    @property
    def comentarios(self) -> list[RespostaPesquisa]:
        return [r for r in self.respostas if r.comentario]


def resultado(p: Pesquisa) -> Resultado:
    """Nota média, NPS (% de notas 9-10 menos % de 0-6) e distribuições."""
    rs = list(p.respostas)
    res = Resultado(rs, p.convidados)
    for r in rs:
        res.notas[r.nota] += 1
    res.resolvidos = [(rotulo, sum(1 for r in rs if r.resolvidos == chave)) for chave, rotulo in RESOLVIDOS.items()]
    if rs:
        res.media = sum(r.nota for r in rs) / len(rs)
        res.promotores = sum(1 for r in rs if r.nota >= 9)
        res.detratores = sum(1 for r in rs if r.nota <= 6)
        res.neutros = len(rs) - res.promotores - res.detratores
        res.nps = round(100 * (res.promotores - res.detratores) / len(rs))
    return res


# ─── rotina diária ──────────────────────────────────────────────────────────

def deve_abrir(s: Session, hoje: date) -> bool:
    """Em junho e dezembro, do dia 1 ao 7 (o cron roda só em dias úteis), se ainda não abriu neste mês."""
    if hoje.month not in MESES or hoje.day > 7 or aberta(s, hoje):
        return False
    return s.scalar(select(Pesquisa.id).where(extract("year", Pesquisa.aberta_em) == hoje.year,
                                              extract("month", Pesquisa.aberta_em) == hoje.month)) is None


def a_lembrar(s: Session, hoje: date) -> tuple[Pesquisa | None, list[Usuario]]:
    """Pesquisa aberta que já está na hora do lembrete (uma vez só) e quem ainda não respondeu."""
    p = aberta(s, hoje)
    if p is None or p.lembrete_em is not None or hoje < p.aberta_em.date() + timedelta(days=LEMBRETE_APOS_DIAS):
        return None, []
    responderam = {r.usuario_id for r in p.respostas}
    return p, [u for u in participantes(s) if u.id not in responderam]


def marcar_lembrete(s: Session, p: Pesquisa) -> None:
    p.lembrete_em = agora()
    s.commit()


def dias_restantes(p: Pesquisa, hoje: date | None = None) -> int:
    return max(0, (p.encerra_em - (hoje or date.today())).days)


def convidar(p: Pesquisa, usuarios: list[Usuario], lembrete: bool = False) -> list:
    """Mensagens de convite (ou lembrete) para quem tem e-mail."""
    from . import notificacoes
    return [m for m in (notificacoes.mensagem_pesquisa(u, p, lembrete) for u in usuarios) if m]
