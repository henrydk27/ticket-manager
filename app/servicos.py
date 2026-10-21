"""Regras do sistema: contas, atendentes, chamados, comentários, anexos, avaliações, painel e relatório.

As rotas só leem o formulário e chamam estas funções; toda escrita no banco passa por aqui.
"""

import re
import secrets
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, aliased
from werkzeug.security import check_password_hash, generate_password_hash

from . import anexos as arquivos_disco
from .anexos import Arquivo
from .modelos import (AVALIACOES, PAPEIS, PAPEL_ADMIN, PAPEL_USUARIO, PRIORIDADES, SETORES, STATUS,
                      STATUS_ABERTO, STATUS_ANDAMENTO, STATUS_FECHADO, Anexo, Chamado, Comentario,
                      Equipamento, TentativaLogin, Usuario, agora)


class ErroValidacao(ValueError):
    """Mensagem pronta para mostrar ao usuário."""


# ─── CONTAS ─────────────────────────────────────────────────────────────────

LOGIN_VALIDO = re.compile(r"^[a-z0-9][a-z0-9._-]{2,49}$")
EMAIL_VALIDO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SENHA_MINIMA = 8


def normalizar_login(login: str) -> str:
    return (login or "").strip().lower()


def validar_senha(senha: str) -> None:
    if len(senha) < SENHA_MINIMA:
        raise ErroValidacao(f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres.")
    if senha.isdigit() or senha.isalpha():
        raise ErroValidacao("Use letras e números na senha.")


def _validar_nome_email(nome: str, email: str) -> tuple[str, str]:
    nome, email = (nome or "").strip(), (email or "").strip().lower()
    if not nome or len(nome) > 100:
        raise ErroValidacao("Informe seu nome.")
    if not email:
        raise ErroValidacao("Informe seu e-mail: é por ele que chegam os avisos dos chamados.")
    if len(email) > 150 or not EMAIL_VALIDO.match(email):
        raise ErroValidacao("E-mail inválido.")
    return nome, email


def criar_conta(s: Session, nome: str, login: str, email: str, setor: str, senha: str) -> Usuario:
    """Cria a conta. A primeira conta do sistema vira administrador."""
    nome, email = _validar_nome_email(nome, email)
    if setor not in SETORES:
        raise ErroValidacao("Escolha seu setor.")
    login = normalizar_login(login)
    if not LOGIN_VALIDO.match(login):
        raise ErroValidacao("Usuário: de 3 a 50 caracteres, só letras minúsculas, números, ponto, hífen ou _.")
    validar_senha(senha)
    if s.scalar(select(Usuario.id).where(Usuario.login == login)):
        raise ErroValidacao("Esse nome de usuário já está em uso.")

    primeiro = not s.scalar(select(func.count(Usuario.id)))
    u = Usuario(nome=nome, login=login, email=email, setor=setor,
                senha_hash=generate_password_hash(senha),
                papel=PAPEL_ADMIN if primeiro else PAPEL_USUARIO)
    s.add(u)
    s.commit()
    return u


def _senha_inutilizavel() -> str:
    """Hash de uma senha aleatória que ninguém conhece (conta sem senha válida)."""
    return generate_password_hash(secrets.token_urlsafe(32))


def _dados_conta_admin(s: Session, nome: str, login: str, email: str, setor: str, papel: str,
                       atual: Usuario | None = None) -> tuple[str, str, str | None]:
    """Valida o que o admin digitou no cadastro/edição. Devolve (nome, login, e-mail)."""
    nome, email = " ".join((nome or "").split()), (email or "").strip().lower()
    if not nome or len(nome) > 100:
        raise ErroValidacao("Informe o nome.")
    if email and (len(email) > 150 or not EMAIL_VALIDO.match(email)):
        raise ErroValidacao("E-mail inválido.")
    if setor not in SETORES:
        raise ErroValidacao("Escolha o setor.")
    if papel not in PAPEIS:
        raise ErroValidacao("Perfil inválido.")
    login = normalizar_login(login)
    if not LOGIN_VALIDO.match(login):
        raise ErroValidacao("Usuário: de 3 a 50 caracteres, só letras minúsculas, números, ponto, hífen ou _.")
    outro = s.scalar(select(Usuario.id).where(Usuario.login == login))
    if outro and (atual is None or outro != atual.id):
        raise ErroValidacao("Esse nome de usuário já está em uso.")
    return nome, login, email or None


def cadastrar_pelo_admin(s: Session, nome: str, login: str, email: str, setor: str, atende: bool,
                         papel: str) -> Usuario:
    """Conta criada pelo admin (ex.: para atribuir equipamentos). Sem senha: a pessoa cria a
    própria no primeiro acesso. O e-mail é opcional aqui; se faltar, é pedido depois do login."""
    nome, login, email = _dados_conta_admin(s, nome, login, email, setor, papel)
    u = Usuario(nome=nome, login=login, email=email, setor=setor, atende=atende, papel=papel,
                senha_hash=_senha_inutilizavel(), senha_liberada_em=agora())
    s.add(u)
    s.commit()
    return u


def editar_usuario(s: Session, alvo: Usuario, ator: Usuario, nome: str, login: str, email: str,
                   setor: str, atende: bool, papel: str) -> None:
    """Admin corrige os dados de uma conta (ex.: quem se cadastrou com nome ou setor errado).

    A senha não muda. Ninguém muda o próprio perfil, e o sistema mantém pelo menos um admin.
    O e-mail pode ficar vazio: nesse caso a pessoa é levada a preenchê-lo no próximo acesso.
    """
    if alvo.id == ator.id:
        papel = alvo.papel
    nome, login, email = _dados_conta_admin(s, nome, login, email, setor, papel, atual=alvo)
    if alvo.is_admin and alvo.ativo and papel != PAPEL_ADMIN and _admins_ativos(s) <= 1:
        raise ErroValidacao("O sistema precisa de pelo menos um administrador ativo.")
    alvo.nome, alvo.login, alvo.email = nome, login, email
    alvo.setor, alvo.atende, alvo.papel = setor, atende, papel
    _liberar_chamados(s, alvo)
    s.commit()


def liberar_nova_senha(s: Session, alvo: Usuario) -> None:
    """A senha atual deixa de valer; no próximo acesso a pessoa cria uma nova (prazo de 7 dias)."""
    alvo.senha_hash = _senha_inutilizavel()
    alvo.senha_liberada_em = agora()
    alvo.senha_solicitada_em = None
    alvo.trocar_senha = False
    s.commit()


def criar_senha(s: Session, u: Usuario, senha: str) -> None:
    """Primeiro acesso / senha liberada: a pessoa define a própria senha."""
    if not u.pode_criar_senha:
        raise ErroValidacao("O prazo para criar a senha venceu. Use \"Solicitar nova senha\".")
    validar_senha(senha)
    u.senha_hash = generate_password_hash(senha)
    u.senha_liberada_em = None
    u.senha_solicitada_em = None
    u.trocar_senha = False
    s.commit()


ESPERA_NOVO_PEDIDO_MIN = 15


def solicitar_nova_senha(s: Session, identificacao: str) -> Usuario | None:
    """Registra o pedido feito na tela de login (por usuário ou e-mail).

    Devolve a conta quando é preciso avisar o CPD; None se não existe, está desativada ou
    já pediu há menos de 15 minutos (evita encher a caixa do CPD).
    """
    ident = (identificacao or "").strip().lower()
    if not ident:
        return None
    campo = Usuario.email if "@" in ident else Usuario.login
    u = s.scalars(select(Usuario).where(campo == ident, Usuario.ativo).order_by(Usuario.id)).first()
    if u is None:
        return None
    if u.senha_solicitada_em and agora() - u.senha_solicitada_em < timedelta(minutes=ESPERA_NOVO_PEDIDO_MIN):
        return None
    u.senha_solicitada_em = agora()
    s.commit()
    return u


def pedidos_de_senha(s: Session) -> int:
    return s.scalar(select(func.count(Usuario.id)).where(Usuario.senha_solicitada_em.is_not(None),
                                                         Usuario.ativo)) or 0


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


def atualizar_perfil(s: Session, u: Usuario, nome: str, email: str) -> None:
    """O setor não é alterado aqui: ele define quais chamados a pessoa atende, então só o admin muda."""
    u.nome, u.email = _validar_nome_email(nome, email)
    s.commit()


# Filtro "situação" da tela de usuários
SITUACOES_CONTA = {"ativas": "Ativas", "desativadas": "Desativadas", "senha": "Pediram nova senha",
                   "primeiro": "Aguardando primeiro acesso"}


@dataclass
class FiltrosUsuarios:
    texto: str = ""
    setor: str = ""
    papel: str = ""
    situacao: str = ""       # "" = todas, ou uma chave de SITUACOES_CONTA


def listar_usuarios(s: Session, f: FiltrosUsuarios | None = None) -> list[tuple[Usuario, int]]:
    """Contas com o total de chamados abertos por cada uma (busca por nome, usuário ou e-mail)."""
    f = f or FiltrosUsuarios()
    total = (select(func.count(Chamado.id)).where(Chamado.solicitante_id == Usuario.id)
             .correlate(Usuario).scalar_subquery())
    cond = []
    if f.texto:
        termo = f"%{_escapar_like(f.texto.strip())}%"
        cond.append(or_(*(c.ilike(termo, escape="\\") for c in (Usuario.nome, Usuario.login, Usuario.email))))
    if f.setor:
        cond.append(Usuario.setor == f.setor)
    if f.papel:
        cond.append(Usuario.papel == f.papel)
    if f.situacao == "ativas":
        cond.append(Usuario.ativo)
    elif f.situacao == "desativadas":
        cond.append(~Usuario.ativo)
    elif f.situacao == "senha":
        cond += [Usuario.ativo, Usuario.senha_solicitada_em.is_not(None)]
    elif f.situacao == "primeiro":
        cond += [Usuario.ativo, Usuario.senha_liberada_em.is_not(None), Usuario.ultimo_acesso.is_(None)]
    return list(s.execute(select(Usuario, total).where(*cond)
                          .order_by(Usuario.ativo.desc(), func.lower(Usuario.nome))).all())


def contagem_de_contas(s: Session) -> dict[str, int]:
    """Números do topo da tela de usuários (mesmas chaves de SITUACOES_CONTA)."""
    def contar(*cond):
        return s.scalar(select(func.count(Usuario.id)).where(*cond)) or 0
    return {
        "ativas": contar(Usuario.ativo),
        "desativadas": contar(~Usuario.ativo),
        "senha": contar(Usuario.ativo, Usuario.senha_solicitada_em.is_not(None)),
        "primeiro": contar(Usuario.ativo, Usuario.senha_liberada_em.is_not(None), Usuario.ultimo_acesso.is_(None)),
    }


def _admins_ativos(s: Session) -> int:
    return s.scalar(select(func.count(Usuario.id)).where(Usuario.papel == PAPEL_ADMIN, Usuario.ativo))


def _liberar_chamados(s: Session, u: Usuario) -> None:
    """Tira a pessoa de responsável pelos chamados em aberto que ela não atende mais."""
    for c in s.scalars(select(Chamado).where(Chamado.responsavel_id == u.id,
                                             Chamado.status != STATUS_FECHADO)).unique():
        if not (u.ativo and u.atende and c.setor_destino == u.setor):
            c.responsavel_id = None


def atualizar_usuario(s: Session, alvo: Usuario, setor: str, atende: bool, papel: str) -> None:
    """Admin define setor, se a pessoa atende chamados do setor e o perfil."""
    if setor not in SETORES:
        raise ErroValidacao("Setor inválido.")
    if papel not in PAPEIS:
        raise ErroValidacao("Perfil inválido.")
    if alvo.is_admin and papel != PAPEL_ADMIN and _admins_ativos(s) <= 1:
        raise ErroValidacao("O sistema precisa de pelo menos um administrador ativo.")
    alvo.setor, alvo.atende, alvo.papel = setor, atende, papel
    _liberar_chamados(s, alvo)
    s.commit()


def apagar_usuario(s: Session, alvo: Usuario, ator: Usuario) -> None:
    """Apaga de vez uma conta desativada sem histórico (ex.: cadastro feito por engano).

    Quem tem chamados, comentários, anexos ou equipamentos continua desativado: apagar
    tiraria o nome da pessoa do histórico.
    """
    if alvo.id == ator.id:
        raise ErroValidacao("Você não pode apagar a própria conta.")
    if alvo.ativo:
        raise ErroValidacao("Desative a conta antes de apagar.")
    motivos = []
    if s.scalar(select(func.count(Chamado.id)).where(or_(Chamado.solicitante_id == alvo.id,
                                                       Chamado.responsavel_id == alvo.id))):
        motivos.append("chamados")
    if s.scalar(select(func.count(Comentario.id)).where(Comentario.autor_id == alvo.id)):
        motivos.append("comentários")
    if s.scalar(select(func.count(Anexo.id)).where(Anexo.autor_id == alvo.id)):
        motivos.append("anexos")
    if s.scalar(select(func.count(Equipamento.id)).where(Equipamento.usuario_id == alvo.id)):
        motivos.append("equipamentos")
    from .modelos import Preventiva
    if s.scalar(select(func.count(Preventiva.id)).where(Preventiva.tecnico_id == alvo.id)):
        motivos.append("preventivas")
    if motivos:
        raise ErroValidacao(f"{alvo.nome} tem {', '.join(motivos)} no sistema e não pode ser apagado. "
                            "A conta continua desativada (sem acesso).")
    s.delete(alvo)
    s.commit()


def definir_ativo(s: Session, alvo: Usuario, ativo: bool) -> None:
    if not ativo and alvo.is_admin and alvo.ativo and _admins_ativos(s) <= 1:
        raise ErroValidacao("O sistema precisa de pelo menos um administrador ativo.")
    alvo.ativo = ativo
    _liberar_chamados(s, alvo)
    s.commit()


# ─── ATENDENTES POR SETOR ───────────────────────────────────────────────────

def atendentes_por_setor(s: Session) -> dict[str, list[Usuario]]:
    """Setores que recebem chamados e quem atende em cada um (só contas ativas)."""
    grupos: dict[str, list[Usuario]] = defaultdict(list)
    for u in s.scalars(select(Usuario).where(Usuario.atende, Usuario.ativo).order_by(Usuario.nome)):
        grupos[u.setor].append(u)
    return {setor: grupos[setor] for setor in SETORES if setor in grupos}


def atendentes_do_setor(s: Session, setor: str) -> list[Usuario]:
    return atendentes_por_setor(s).get(setor, [])


def _responsavel_valido(s: Session, setor: str, responsavel_id) -> Usuario:
    if setor not in SETORES:
        raise ErroValidacao("Escolha para qual setor é o pedido.")
    u = s.get(Usuario, int(responsavel_id)) if str(responsavel_id or "").isdigit() else None
    if u is None or not u.ativo or not u.atende or u.setor != setor:
        raise ErroValidacao(f"Escolha um funcionário do setor {setor}.")
    return u


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


# ─── VISIBILIDADE ───────────────────────────────────────────────────────────

def _visiveis(usuario: Usuario):
    """Condição SQL dos chamados que o usuário pode ver (None = todos)."""
    if usuario.is_admin:
        return None
    if usuario.ve_setor:
        return or_(Chamado.solicitante_id == usuario.id, Chamado.setor_destino == usuario.setor)
    return Chamado.solicitante_id == usuario.id


def _escopo_atendimento(usuario: Usuario, setor: str | None = None) -> list:
    """Chamados que o usuário atende: do setor dele (admin: todos, ou o setor escolhido)."""
    if usuario.is_admin:
        return [Chamado.setor_destino == setor] if setor else []
    return [Chamado.setor_destino == usuario.setor]


def _escopo_painel(usuario: Usuario, setor: str | None = None) -> list:
    """Painel e relatório: admin vê todos (ou o setor escolhido); quem atende e o supervisor, os
    chamados enviados ao próprio setor; os demais, os chamados que abriram."""
    if usuario.ve_setor:
        return _escopo_atendimento(usuario, setor)
    return [Chamado.solicitante_id == usuario.id]


# ─── HORÁRIO DE EXPEDIENTE ──────────────────────────────────────────────────

# O tempo até encerrar conta só o expediente: de segunda a sexta, das 7h às 18h
EXPEDIENTE_INICIO, EXPEDIENTE_FIM = 7, 18
DIAS_EXPEDIENTE = {0, 1, 2, 3, 4}          # segunda = 0 … domingo = 6


def segundos_expediente(inicio: datetime, fim: datetime) -> float:
    """Tempo entre dois momentos contando só o horário de expediente."""
    if fim <= inicio:
        return 0.0
    total = 0.0
    dia = inicio.date()
    while dia <= fim.date():
        if dia.weekday() in DIAS_EXPEDIENTE:
            abre = datetime.combine(dia, datetime.min.time()).replace(hour=EXPEDIENTE_INICIO)
            fecha = abre.replace(hour=EXPEDIENTE_FIM)
            ini, fi = max(inicio, abre), min(fim, fecha)
            if fi > ini:
                total += (fi - ini).total_seconds()
        dia += timedelta(days=1)
    return total


# ─── LISTAGEM DE CHAMADOS ───────────────────────────────────────────────────

Solicitante = aliased(Usuario)
Responsavel = aliased(Usuario)

ORDENACAO = {
    "id": Chamado.id,
    "titulo": func.lower(Chamado.titulo),
    "para": Chamado.setor_destino,
    "status": Chamado.status,
    "prioridade": case({p: i for i, p in enumerate(PRIORIDADES)}, value=Chamado.prioridade),
    "abertura": Chamado.aberto_em,
    "responsavel": func.lower(Responsavel.nome),
}

VISOES = {
    "": "Tudo",
    "setor": "Do meu setor",
    "atribuidos": "Atribuídos a mim",
    "meus": "Que eu abri",
}


@dataclass
class Filtros:
    visao: str = ""       # ver VISOES
    texto: str = ""
    status: str = ""      # "" = todos, "abertos" = todos menos Fechado, ou um status
    setor: str = ""       # setor de destino (só o admin filtra por setor)
    ordenar: str = "id"
    direcao: str = "desc"
    pagina: int = 1
    por_pagina: int = 25


def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def listar_chamados(s: Session, f: Filtros, usuario: Usuario) -> tuple[list[Chamado], int]:
    cond = [c for c in [_visiveis(usuario)] if c is not None]
    if f.visao == "setor":
        cond += _escopo_atendimento(usuario)
    elif f.visao == "atribuidos":
        cond.append(Chamado.responsavel_id == usuario.id)
    elif f.visao == "meus":
        cond.append(Chamado.solicitante_id == usuario.id)
    if f.setor and usuario.is_admin:
        cond.append(Chamado.setor_destino == f.setor)
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


def criar_chamado(s: Session, autor: Usuario, setor_destino: str, responsavel_id, titulo: str,
                  descricao: str, prioridade: str, arquivos: list[Arquivo]) -> Chamado:
    responsavel = _responsavel_valido(s, setor_destino, responsavel_id)
    titulo, descricao = titulo.strip(), descricao.strip()
    if not titulo or not descricao:
        raise ErroValidacao("Preencha título e descrição.")
    if len(titulo) > 150:
        raise ErroValidacao("O título pode ter no máximo 150 caracteres.")
    if prioridade not in PRIORIDADES:
        raise ErroValidacao("Escolha a prioridade.")

    c = Chamado(titulo=titulo, descricao=descricao, prioridade=prioridade, setor=autor.setor,
                setor_destino=setor_destino, responsavel_id=responsavel.id,
                solicitante_id=autor.id, status=STATUS_ABERTO)
    s.add(c)
    gravados = _gravar_anexos(s, c, autor, arquivos)
    _commit_com_arquivos(s, gravados)
    return c


def obter_chamado(s: Session, chamado_id: int) -> Chamado | None:
    return s.get(Chamado, chamado_id)


def _evento(s: Session, c: Chamado, autor: Usuario, texto: str) -> None:
    s.add(Comentario(chamado=c, autor_id=autor.id, texto=texto, evento=True))


def comentar(s: Session, c: Chamado, autor: Usuario, texto: str, arquivos: list[Arquivo]) -> Comentario:
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
    return m


TAMANHO_MAX_COMENTARIO = 10000


def editar_comentario(s: Session, m: Comentario, ator: Usuario, texto: str) -> bool:
    """Administrador corrige o texto de um comentário. Registros automáticos (status,
    encaminhamento) não são editáveis. Devolve False se o texto não mudou."""
    if not ator.is_admin:
        raise ErroValidacao("Só o administrador edita comentários.")
    if m.evento:
        raise ErroValidacao("Registros automáticos do histórico não podem ser editados.")
    texto = (texto or "").strip()
    if not texto:
        raise ErroValidacao("O comentário não pode ficar vazio.")
    if len(texto) > TAMANHO_MAX_COMENTARIO:
        raise ErroValidacao(f"O comentário pode ter no máximo {TAMANHO_MAX_COMENTARIO} caracteres.")
    if texto == m.texto:
        return False
    m.texto, m.editado_em, m.editado_por_id = texto, agora(), ator.id
    s.commit()
    return True


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


def encaminhar(s: Session, c: Chamado, setor: str, responsavel_id, autor: Usuario) -> bool:
    """Troca o responsável, no mesmo setor ou em outro. Cobre "atribuir" e "transferir"."""
    responsavel = _responsavel_valido(s, setor, responsavel_id)
    if setor == c.setor_destino and responsavel.id == c.responsavel_id:
        return False
    if setor != c.setor_destino:
        _evento(s, c, autor, f"Encaminhado de {c.setor_destino} para {setor} ({responsavel.nome}).")
        c.setor_destino = setor
    else:
        _evento(s, c, autor, f"Chamado atribuído a {responsavel.nome}.")
    c.responsavel = responsavel  # objeto, não só o id: quem usa c.responsavel já vê o novo
    s.commit()
    return True


def assumir(s: Session, c: Chamado, atendente: Usuario) -> None:
    encaminhar(s, c, c.setor_destino, atendente.id, atendente)
    if c.status == STATUS_ABERTO:
        alterar_status(s, c, STATUS_ANDAMENTO, atendente)


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

HORAS_DIA_UTIL = EXPEDIENTE_FIM - EXPEDIENTE_INICIO      # 11 h
# Faixas de "há quanto tempo está em aberto" (horas de expediente)
FAIXAS_IDADE = [("Até 4 h", 4), ("4 h a 1 dia", HORAS_DIA_UTIL), ("1 a 3 dias", 3 * HORAS_DIA_UTIL),
                ("Mais de 3 dias", None)]
DIAS_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def _baldes(inicio: datetime, fim: datetime) -> list[tuple[str, datetime, datetime]]:
    """Fatias da série: semanas (até ~3 meses) ou meses. (rótulo, começo, fim exclusivo)."""
    baldes = []
    if (fim - inicio).days <= 95:      # mesma regra de "agrupamento" em indicadores()
        cur = datetime.combine((inicio - timedelta(days=inicio.weekday())).date(), datetime.min.time())
        while cur < fim:
            prox = cur + timedelta(days=7)
            baldes.append((f"{max(cur, inicio):%d/%m}", max(cur, inicio), min(prox, fim)))
            cur = prox
    else:
        cur = datetime(inicio.year, inicio.month, 1)
        while cur < fim:
            prox = datetime(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
            baldes.append((f"{cur:%m/%Y}", max(cur, inicio), min(prox, fim)))
            cur = prox
    return baldes


def _medias(fechados: list[Chamado]) -> tuple[float | None, float | None, int]:
    """(tempo médio em horas de expediente, % de "Bom" entre os avaliados, nº de avaliações)."""
    tempos = [segundos_expediente(c.aberto_em, c.fechado_em) / 3600 for c in fechados if c.aberto_em and c.fechado_em]
    avaliados = [c.avaliacao for c in fechados if c.avaliacao]
    tempo = sum(tempos) / len(tempos) if tempos else None
    satisf = 100 * avaliados.count(AVALIACOES[0]) / len(avaliados) if avaliados else None
    return tempo, satisf, len(avaliados)


def indicadores(s: Session, inicio: datetime, fim: datetime, usuario: Usuario, setor: str | None = None) -> dict:
    """Tudo o que o painel e o PDF do relatório mostram, para o período [inicio, fim).

    Escopo: admin vê todos (ou o setor escolhido); quem atende e o supervisor, o próprio setor;
    o usuário que não atende, os chamados que abriu. Tempos em horas de expediente.
    """
    escopo = _escopo_painel(usuario, setor)
    duracao = fim - inicio
    ini_ant = inicio - duracao
    todos = list(s.scalars(select(Chamado).where(*escopo, or_(Chamado.status != STATUS_FECHADO,
                                                                Chamado.fechado_em >= ini_ant))).unique())
    abertos = [c for c in todos if c.status != STATUS_FECHADO]
    novos = [c for c in todos if inicio <= c.aberto_em < fim]
    fechados = [c for c in todos if c.status == STATUS_FECHADO and c.fechado_em and inicio <= c.fechado_em < fim]
    novos_ant = s.scalar(select(func.count(Chamado.id)).where(
        *escopo, Chamado.aberto_em >= ini_ant, Chamado.aberto_em < inicio)) or 0
    fechados_ant = [c for c in todos if c.status == STATUS_FECHADO and c.fechado_em
                    and ini_ant <= c.fechado_em < inicio]
    tempo, satisf, n_aval = _medias(fechados)
    tempo_ant, satisf_ant, _ = _medias(fechados_ant)

    # série: abertos x encerrados, e o que estava em aberto no fim de cada fatia
    serie = []
    for rotulo, a, b in _baldes(inicio, fim):
        fech_b = [c for c in fechados if a <= c.fechado_em < b]
        t_b, sat_b, _ = _medias(fech_b)
        serie.append({
            "rotulo": rotulo,
            "abertos": sum(1 for c in novos if a <= c.aberto_em < b),
            "encerrados": len(fech_b),
            "em_aberto": sum(1 for c in todos if c.aberto_em < b and (c.status != STATUS_FECHADO
                                                                       or (c.fechado_em and c.fechado_em >= b))),
            "tempo": t_b, "satisfacao": sat_b,
        })

    # idade dos que estão em aberto agora
    agora_ = agora()
    idades = [0] * len(FAIXAS_IDADE)
    for c in abertos:
        h = segundos_expediente(c.aberto_em, agora_) / 3600
        idades[next(i for i, (_r, lim) in enumerate(FAIXAS_IDADE) if lim is None or h <= lim)] += 1

    # em aberto por setor (destino para quem vê vários setores; de quem pediu para os demais) e prioridade
    por_destino = usuario.is_admin and not setor
    grupos: dict[str, Counter] = defaultdict(Counter)
    for c in abertos:
        grupos[c.setor_destino if por_destino else c.setor][c.prioridade] += 1
    setor_prioridade = sorted(((nome, [cont.get(p, 0) for p in PRIORIDADES]) for nome, cont in grupos.items()),
                              key=lambda x: (-sum(x[1]), x[0]))

    # mapa de calor: chamados abertos no período por dia da semana x hora do expediente
    horas = list(range(EXPEDIENTE_INICIO, EXPEDIENTE_FIM))
    calor = [[0] * len(horas) for _ in DIAS_SEMANA]
    fora = 0
    for c in novos:
        h = c.aberto_em.hour
        if EXPEDIENTE_INICIO <= h < EXPEDIENTE_FIM:
            calor[c.aberto_em.weekday()][h - EXPEDIENTE_INICIO] += 1
        else:
            fora += 1
    dias_calor = [i for i in range(7) if i < 5 or any(calor[i])]     # sábado/domingo só se houver

    # por responsável: em aberto agora e encerrados no período
    resp: dict[str, dict] = defaultdict(lambda: {"em_aberto": 0, "encerrados": 0, "tempos": []})
    for c in abertos:
        if c.responsavel:
            resp[c.responsavel.nome]["em_aberto"] += 1
    for c in fechados:
        if c.responsavel:
            r = resp[c.responsavel.nome]
            r["encerrados"] += 1
            r["tempos"].append(segundos_expediente(c.aberto_em, c.fechado_em) / 3600)
    responsaveis = sorted(
        ({"nome": n, "em_aberto": r["em_aberto"], "encerrados": r["encerrados"],
          "tempo": sum(r["tempos"]) / len(r["tempos"]) if r["tempos"] else None} for n, r in resp.items()),
        key=lambda x: (-(x["em_aberto"] + x["encerrados"]), x["nome"]))[:8]

    def variacao(atual, anterior):
        if atual is None or anterior in (None, 0):
            return None
        return 100 * (atual - anterior) / anterior

    return {
        "resumo": {
            "abertos": len(abertos),
            "sem_responsavel": sum(1 for c in abertos if c.responsavel_id is None),
            "novos": len(novos), "novos_var": variacao(len(novos), novos_ant),
            "fechados": len(fechados), "fechados_var": variacao(len(fechados), len(fechados_ant)),
            "tempo_medio": tempo, "tempo_var": variacao(tempo, tempo_ant),
            "satisfacao": satisf, "satisfacao_ant": satisf_ant, "avaliacoes": n_aval,
        },
        "serie": serie, "agrupamento": "semana" if duracao.days <= 95 else "mês",
        "por_status": [(st, sum(1 for c in abertos if c.status == st)) for st in STATUS if st != STATUS_FECHADO],
        "idade": [(r, n) for (r, _l), n in zip(FAIXAS_IDADE, idades)],
        "setor_prioridade": setor_prioridade, "por_destino": por_destino,
        "calor": {"horas": horas, "dias": [(DIAS_SEMANA[i], calor[i]) for i in dias_calor], "fora": fora},
        "avaliacoes": [(a, sum(1 for c in fechados if c.avaliacao == a)) for a in AVALIACOES],
        "sem_avaliacao": sum(1 for c in fechados if not c.avaliacao),
        "responsaveis": responsaveis,
    }


def painel(s: Session, dias: int, usuario: Usuario, setor: str | None = None) -> dict:
    """Indicadores dos últimos `dias` até agora (ver indicadores)."""
    fim = agora() + timedelta(seconds=1)
    return indicadores(s, fim - timedelta(days=dias), fim, usuario, setor)


# ─── RELATÓRIO ──────────────────────────────────────────────────────────────

def chamados_por_periodo(s: Session, inicio: date, fim: date, usuario: Usuario,
                         setor: str | None = None) -> list[Chamado]:
    return list(s.scalars(select(Chamado).where(
        *_escopo_painel(usuario, setor),
        Chamado.aberto_em >= datetime.combine(inicio, datetime.min.time()),
        Chamado.aberto_em < datetime.combine(fim + timedelta(days=1), datetime.min.time()),
    ).order_by(Chamado.aberto_em)).unique())
