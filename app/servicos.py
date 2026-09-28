"""Regras do sistema: contas, chamados, comentários, anexos, avaliações, painel e relatório.

As rotas só leem o formulário e chamam estas funções; toda escrita no banco passa por aqui.
"""

import re
import secrets
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, aliased
from werkzeug.security import check_password_hash, generate_password_hash

from . import anexos as arquivos_disco
from .anexos import Arquivo
from .modelos import (AVALIACOES, PAPEIS, PAPEL_ADMIN, PAPEL_TECNICO, PAPEL_USUARIO, PRIORIDADES,
                      SETORES, STATUS, STATUS_ABERTO, STATUS_ANDAMENTO, STATUS_FECHADO, Anexo,
                      Chamado, Comentario, TentativaLogin, Usuario, agora)


class ErroValidacao(ValueError):
    """Mensagem pronta para mostrar ao usuário."""


# ─── CONTAS ─────────────────────────────────────────────────────────────────

LOGIN_VALIDO = re.compile(r"^[a-z0-9][a-z0-9._-]{2,49}$")
SENHA_MINIMA = 8


def normalizar_login(login: str) -> str:
    return (login or "").strip().lower()


def validar_senha(senha: str) -> None:
    if len(senha) < SENHA_MINIMA:
        raise ErroValidacao(f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres.")
    if senha.isdigit() or senha.isalpha():
        raise ErroValidacao("Use letras e números na senha.")


def criar_conta(s: Session, nome: str, login: str, email: str, setor: str, senha: str) -> Usuario:
    """Cria a conta. A primeira conta do sistema vira administrador."""
    nome, login, email = nome.strip(), normalizar_login(login), (email or "").strip().lower()
    if not nome or len(nome) > 100:
        raise ErroValidacao("Informe seu nome.")
    if not LOGIN_VALIDO.match(login):
        raise ErroValidacao("Usuário: de 3 a 50 caracteres, só letras minúsculas, números, ponto, hífen ou _.")
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ErroValidacao("E-mail inválido.")
    if setor not in SETORES:
        raise ErroValidacao("Escolha seu setor.")
    validar_senha(senha)
    if s.scalar(select(Usuario.id).where(Usuario.login == login)):
        raise ErroValidacao("Esse nome de usuário já está em uso.")

    primeiro = not s.scalar(select(func.count(Usuario.id)))
    u = Usuario(nome=nome, login=login, email=email or None, setor=setor,
                senha_hash=generate_password_hash(senha),
                papel=PAPEL_ADMIN if primeiro else PAPEL_USUARIO)
    s.add(u)
    s.commit()
    return u


def autenticar(s: Session, login: str, senha: str) -> Usuario | None:
    u = s.scalar(select(Usuario).where(Usuario.login == normalizar_login(login)))
    if u is None or not check_password_hash(u.senha_hash, senha):
        return None
    return u


def registrar_acesso(s: Session, u: Usuario) -> None:
    u.ultimo_acesso = agora()
    s.commit()


def alterar_senha(s: Session, u: Usuario, atual: str | None, nova: str) -> None:
    """atual=None dispensa a senha atual (troca obrigatória logo após o login)."""
    if atual is not None and not check_password_hash(u.senha_hash, atual):
        raise ErroValidacao("Senha atual incorreta.")
    validar_senha(nova)
    u.senha_hash = generate_password_hash(nova)
    u.trocar_senha = False
    s.commit()


def atualizar_perfil(s: Session, u: Usuario, nome: str, email: str, setor: str) -> None:
    nome, email = nome.strip(), (email or "").strip().lower()
    if not nome or len(nome) > 100:
        raise ErroValidacao("Informe seu nome.")
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ErroValidacao("E-mail inválido.")
    if setor not in SETORES:
        raise ErroValidacao("Escolha seu setor.")
    u.nome, u.email, u.setor = nome, email or None, setor
    s.commit()


def listar_usuarios(s: Session) -> list[tuple[Usuario, int]]:
    total = (select(func.count(Chamado.id)).where(Chamado.solicitante_id == Usuario.id)
             .correlate(Usuario).scalar_subquery())
    return list(s.execute(select(Usuario, total).order_by(Usuario.ativo.desc(), Usuario.nome)).all())


def listar_tecnicos(s: Session) -> list[Usuario]:
    return list(s.scalars(select(Usuario).where(
        Usuario.papel.in_((PAPEL_TECNICO, PAPEL_ADMIN)), Usuario.ativo).order_by(Usuario.nome)))


def _admins_ativos(s: Session) -> int:
    return s.scalar(select(func.count(Usuario.id)).where(Usuario.papel == PAPEL_ADMIN, Usuario.ativo))


def definir_papel(s: Session, alvo: Usuario, papel: str) -> None:
    if papel not in PAPEIS:
        raise ErroValidacao("Papel inválido.")
    if alvo.is_admin and papel != PAPEL_ADMIN and _admins_ativos(s) <= 1:
        raise ErroValidacao("O sistema precisa de pelo menos um administrador ativo.")
    alvo.papel = papel
    s.commit()


def definir_ativo(s: Session, alvo: Usuario, ativo: bool) -> None:
    if not ativo and alvo.is_admin and alvo.ativo and _admins_ativos(s) <= 1:
        raise ErroValidacao("O sistema precisa de pelo menos um administrador ativo.")
    alvo.ativo = ativo
    s.commit()


def redefinir_senha(s: Session, alvo: Usuario) -> str:
    """Gera uma senha temporária; o usuário é obrigado a trocá-la no próximo acesso."""
    temporaria = secrets.token_urlsafe(9)
    alvo.senha_hash = generate_password_hash(temporaria)
    alvo.trocar_senha = True
    s.commit()
    return temporaria


# ─── LIMITE DE TENTATIVAS DE LOGIN ──────────────────────────────────────────

MAX_TENTATIVAS = 5
BLOQUEIO = timedelta(minutes=5)


def segundos_bloqueado(s: Session, chave: str) -> int:
    inicio = agora() - BLOQUEIO
    s.execute(TentativaLogin.__table__.delete().where(TentativaLogin.momento < inicio))
    s.commit()
    momentos = list(s.scalars(select(TentativaLogin.momento).where(TentativaLogin.chave == chave)
                              .order_by(TentativaLogin.momento)))
    if len(momentos) < MAX_TENTATIVAS:
        return 0
    return max(1, int((momentos[-MAX_TENTATIVAS] + BLOQUEIO - agora()).total_seconds()))


def registrar_falha(s: Session, chave: str) -> None:
    s.add(TentativaLogin(chave=chave[:120]))
    s.commit()


def limpar_falhas(s: Session, chave: str) -> None:
    s.execute(TentativaLogin.__table__.delete().where(TentativaLogin.chave == chave))
    s.commit()


# ─── LISTAGEM DE CHAMADOS ───────────────────────────────────────────────────

Solicitante = aliased(Usuario)
Responsavel = aliased(Usuario)

_ORDEM_PRIORIDADE = case({p: i for i, p in enumerate(PRIORIDADES)}, value=Chamado.prioridade)
ORDENACAO = {
    "id": Chamado.id,
    "titulo": func.lower(Chamado.titulo),
    "setor": Chamado.setor,
    "status": Chamado.status,
    "prioridade": _ORDEM_PRIORIDADE,
    "abertura": Chamado.aberto_em,
    "fechamento": Chamado.fechado_em,
    "solicitante": func.lower(Solicitante.nome),
    "responsavel": func.lower(Responsavel.nome),
}


@dataclass
class Filtros:
    texto: str = ""
    status: str = ""          # "" = todos, "abertos" = todos menos Fechado
    setor: str = ""
    prioridade: str = ""
    responsavel: str = ""     # "" = todos, "nenhum", "eu" ou id
    de: date | None = None
    ate: date | None = None
    ordenar: str = "id"
    direcao: str = "desc"
    pagina: int = 1
    por_pagina: int = 25


def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def listar_chamados(s: Session, f: Filtros, usuario: Usuario) -> tuple[list[Chamado], int]:
    cond = []
    if not usuario.is_tecnico:
        cond.append(Chamado.solicitante_id == usuario.id)
    if f.texto:
        termo = f"%{_escapar_like(f.texto.strip())}%"
        busca = [Chamado.titulo.ilike(termo, escape="\\"), Chamado.descricao.ilike(termo, escape="\\")]
        numero = f.texto.strip().lstrip("#")
        if numero.isdigit():
            busca.append(Chamado.id == int(numero))
        cond.append(or_(*busca))
    if f.status == "abertos":
        cond.append(Chamado.status != STATUS_FECHADO)
    elif f.status:
        cond.append(Chamado.status == f.status)
    if f.setor:
        cond.append(Chamado.setor == f.setor)
    if f.prioridade:
        cond.append(Chamado.prioridade == f.prioridade)
    if f.responsavel == "nenhum":
        cond.append(Chamado.responsavel_id.is_(None))
    elif f.responsavel == "eu":
        cond.append(Chamado.responsavel_id == usuario.id)
    elif f.responsavel.isdigit():
        cond.append(Chamado.responsavel_id == int(f.responsavel))
    if f.de:
        cond.append(Chamado.aberto_em >= datetime.combine(f.de, datetime.min.time()))
    if f.ate:
        cond.append(Chamado.aberto_em < datetime.combine(f.ate + timedelta(days=1), datetime.min.time()))

    base = (select(Chamado)
            .join(Solicitante, Solicitante.id == Chamado.solicitante_id)
            .outerjoin(Responsavel, Responsavel.id == Chamado.responsavel_id)
            .where(*cond))
    total = s.scalar(select(func.count()).select_from(base.subquery()))

    coluna = ORDENACAO.get(f.ordenar, Chamado.id)
    ordem = coluna.asc() if f.direcao == "asc" else coluna.desc()
    linhas = s.scalars(base.order_by(ordem.nulls_last(), Chamado.id.desc())
                       .offset((f.pagina - 1) * f.por_pagina).limit(f.por_pagina)).unique()
    return list(linhas), total or 0


def contar_anexos(s: Session, ids: list[int]) -> dict[int, int]:
    if not ids:
        return {}
    return dict(s.execute(select(Anexo.chamado_id, func.count(Anexo.id))
                          .where(Anexo.chamado_id.in_(ids)).group_by(Anexo.chamado_id)).all())


# ─── CHAMADO ────────────────────────────────────────────────────────────────

def _gravar_anexos(s: Session, chamado: Chamado, autor: Usuario, arquivos: list[Arquivo],
                   comentario: Comentario | None = None) -> list[str]:
    gravados = []
    for arq in arquivos:
        nome_disco = arquivos_disco.gravar(arq)
        gravados.append(nome_disco)
        s.add(Anexo(chamado=chamado, comentario=comentario, autor_id=autor.id, nome=arq.nome,
                    tipo=arq.tipo, tamanho=len(arq.conteudo), arquivo=nome_disco))
    return gravados


def _commit_com_arquivos(s: Session, gravados: list[str]) -> None:
    """Se o banco falhar, apaga os arquivos já gravados para não sobrar lixo no disco."""
    try:
        s.commit()
    except Exception:
        s.rollback()
        for nome in gravados:
            arquivos_disco.remover(nome)
        raise


def criar_chamado(s: Session, autor: Usuario, titulo: str, descricao: str, prioridade: str,
                  setor: str, arquivos: list[Arquivo]) -> Chamado:
    titulo, descricao = titulo.strip(), descricao.strip()
    if not titulo or not descricao:
        raise ErroValidacao("Preencha título e descrição.")
    if len(titulo) > 150:
        raise ErroValidacao("O título pode ter no máximo 150 caracteres.")
    if prioridade not in PRIORIDADES or setor not in SETORES:
        raise ErroValidacao("Escolha prioridade e setor.")

    c = Chamado(titulo=titulo, descricao=descricao, prioridade=prioridade, setor=setor,
                solicitante_id=autor.id, status=STATUS_ABERTO)
    s.add(c)
    gravados = _gravar_anexos(s, c, autor, arquivos)
    _commit_com_arquivos(s, gravados)
    return c


def obter_chamado(s: Session, chamado_id: int) -> Chamado | None:
    return s.get(Chamado, chamado_id)


def _evento(s: Session, c: Chamado, autor: Usuario, texto: str) -> None:
    s.add(Comentario(chamado=c, autor_id=autor.id, texto=texto, evento=True))


def comentar(s: Session, c: Chamado, autor: Usuario, texto: str, arquivos: list[Arquivo]) -> None:
    texto = texto.strip()
    if not texto and not arquivos:
        raise ErroValidacao("Digite um comentário ou anexe um arquivo.")
    if not texto:
        texto = "Anexou " + ", ".join(a.nome for a in arquivos) + "."
    m = Comentario(chamado=c, autor_id=autor.id, texto=texto)
    s.add(m)
    gravados = _gravar_anexos(s, c, autor, arquivos, m)
    c.atualizado_em = agora()
    _commit_com_arquivos(s, gravados)


def alterar_status(s: Session, c: Chamado, novo: str, autor: Usuario) -> bool:
    if novo not in STATUS:
        raise ErroValidacao("Status inválido.")
    if novo == c.status:
        return False
    anterior = c.status
    c.status = novo
    if novo == STATUS_FECHADO:
        c.fechado_em = agora()
    elif anterior == STATUS_FECHADO:
        c.fechado_em = None  # reaberto
        c.avaliacao = c.avaliado_em = None
    _evento(s, c, autor, f"Status alterado de \"{anterior}\" para \"{novo}\".")
    s.commit()
    return True


def atribuir(s: Session, c: Chamado, responsavel: Usuario | None, autor: Usuario) -> bool:
    if responsavel is not None and (not responsavel.is_tecnico or not responsavel.ativo):
        raise ErroValidacao("Escolha um técnico ativo.")
    novo_id = responsavel.id if responsavel else None
    if novo_id == c.responsavel_id:
        return False
    c.responsavel_id = novo_id
    _evento(s, c, autor, f"Chamado atribuído a {responsavel.nome}." if responsavel
            else "Responsável removido.")
    s.commit()
    return True


def assumir(s: Session, c: Chamado, tecnico: Usuario) -> None:
    atribuir(s, c, tecnico, tecnico)
    if c.status == STATUS_ABERTO:
        alterar_status(s, c, STATUS_ANDAMENTO, tecnico)


def apagar_chamado(s: Session, c: Chamado) -> None:
    nomes = [a.arquivo for a in c.anexos]
    s.delete(c)
    s.commit()
    for nome in nomes:
        arquivos_disco.remover(nome)


def obter_anexo(s: Session, anexo_id: int) -> Anexo | None:
    return s.get(Anexo, anexo_id)


# ─── AVALIAÇÕES ─────────────────────────────────────────────────────────────

def avaliacoes_pendentes(s: Session, usuario: Usuario) -> list[Chamado]:
    return list(s.scalars(select(Chamado).where(
        Chamado.solicitante_id == usuario.id, Chamado.status == STATUS_FECHADO,
        Chamado.avaliacao.is_(None)).order_by(Chamado.fechado_em)).unique())


def avaliar(s: Session, c: Chamado, usuario: Usuario, avaliacao: str) -> bool:
    if avaliacao not in AVALIACOES:
        raise ErroValidacao("Avaliação inválida.")
    if c.solicitante_id != usuario.id or not c.fechado or c.avaliacao:
        return False
    c.avaliacao, c.avaliado_em = avaliacao, agora()
    s.commit()
    return True


# ─── PAINEL ─────────────────────────────────────────────────────────────────

def painel(s: Session, dias: int) -> dict:
    limite = agora() - timedelta(days=dias)
    abertos = list(s.scalars(select(Chamado).where(Chamado.status != STATUS_FECHADO)).unique())
    fechados = list(s.execute(select(Chamado.aberto_em, Chamado.fechado_em, Chamado.avaliacao)
                              .where(Chamado.status == STATUS_FECHADO, Chamado.fechado_em >= limite)).all())
    novos = s.scalar(select(func.count(Chamado.id)).where(Chamado.aberto_em >= limite)) or 0

    # Últimos 6 meses, incluindo os que não tiveram chamados
    hoje = date.today()
    meses_ref = [divmod(hoje.year * 12 + hoje.month - 1 - i, 12) for i in range(5, -1, -1)]
    inicio_meses = datetime(meses_ref[0][0], meses_ref[0][1] + 1, 1)
    por_mes = Counter(d.strftime("%m/%Y") for d in s.scalars(
        select(Chamado.aberto_em).where(Chamado.aberto_em >= inicio_meses)))
    meses = [(r, por_mes.get(r, 0)) for r in (f"{m + 1:02d}/{a}" for a, m in meses_ref)]

    def contar(valores):
        return Counter(valores).most_common()

    tempos = [(f - a).total_seconds() / 86400 for a, f, _ in fechados if a and f]
    return {
        "resumo": {
            "abertos": len(abertos),
            "sem_responsavel": sum(1 for c in abertos if c.responsavel_id is None),
            "novos": novos,
            "fechados": len(fechados),
            "tempo_medio": sum(tempos) / len(tempos) if tempos else None,
        },
        "por_status": contar(c.status for c in abertos),
        "por_responsavel": contar(c.responsavel.nome if c.responsavel else "Sem responsável" for c in abertos),
        "por_setor": contar(c.setor for c in abertos),
        "por_prioridade": sorted(contar(c.prioridade for c in abertos),
                                 key=lambda x: PRIORIDADES.index(x[0]) if x[0] in PRIORIDADES else 99),
        "avaliacoes": contar(av or "Sem avaliação" for _, _, av in fechados),
        "por_mes": meses,
    }


# ─── RELATÓRIO ──────────────────────────────────────────────────────────────

def chamados_por_periodo(s: Session, inicio: date, fim: date) -> list[Chamado]:
    return list(s.scalars(select(Chamado).where(
        Chamado.aberto_em >= datetime.combine(inicio, datetime.min.time()),
        Chamado.aberto_em < datetime.combine(fim + timedelta(days=1), datetime.min.time()),
    ).order_by(Chamado.aberto_em)).unique())
