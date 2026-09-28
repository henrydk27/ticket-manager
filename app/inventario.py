"""Inventário de TI: cadastro de equipamentos, atribuição a setor/usuário e histórico."""

import ipaddress
import re
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .modelos import (SETORES, SITUACAO_DESCARTADO, SITUACAO_ESTOQUE, SITUACAO_USO, SITUACOES,
                      TIPOS_EQUIPAMENTO, Equipamento, MovimentoEquipamento, Usuario)
from .servicos import ErroValidacao, _escapar_like

# campo: (rótulo, tamanho máximo) — campos de texto livre
CAMPOS_TEXTO = {
    "marca": ("Marca", 60),
    "modelo": ("Modelo", 100),
    "numero_serie": ("Nº de série", 100),
    "processador": ("Processador", 100),
    "memoria": ("Memória", 50),
    "armazenamento": ("Armazenamento", 100),
    "sistema_operacional": ("Sistema operacional", 100),
    "hostname": ("Hostname", 100),
}
ROTULOS = {"patrimonio": "Patrimônio", "tipo": "Tipo", "ip": "IP", "mac": "MAC",
           "observacoes": "Observações", **{k: v[0] for k, v in CAMPOS_TEXTO.items()}}


# ─── listagem ───────────────────────────────────────────────────────────────

ORDENACAO = {
    "patrimonio": func.lower(Equipamento.patrimonio),
    "tipo": Equipamento.tipo,
    "modelo": func.lower(func.coalesce(Equipamento.marca, "") + " " + func.coalesce(Equipamento.modelo, "")),
    "setor": Equipamento.setor,
    "usuario": func.lower(Usuario.nome),
    "situacao": Equipamento.situacao,
    "atualizado": Equipamento.atualizado_em,
}


@dataclass
class Filtros:
    texto: str = ""
    tipo: str = ""
    situacao: str = ""       # "" = todas menos Descartado, "todas", ou uma situação
    setor: str = ""          # "" = todos, "sem" = sem setor, ou um setor
    ordenar: str = "patrimonio"
    direcao: str = "asc"
    pagina: int = 1
    por_pagina: int = 50


def _consulta(f: Filtros):
    cond = []
    if f.texto:
        termo = f"%{_escapar_like(f.texto.strip())}%"
        cond.append(or_(*(c.ilike(termo, escape="\\") for c in (
            Equipamento.patrimonio, Equipamento.marca, Equipamento.modelo, Equipamento.numero_serie,
            Equipamento.hostname, Equipamento.ip, Equipamento.mac, Usuario.nome))))
    if f.tipo:
        cond.append(Equipamento.tipo == f.tipo)
    if f.situacao == "":
        cond.append(Equipamento.situacao != SITUACAO_DESCARTADO)
    elif f.situacao != "todas":
        cond.append(Equipamento.situacao == f.situacao)
    if f.setor == "sem":
        cond.append(Equipamento.setor.is_(None))
    elif f.setor:
        cond.append(Equipamento.setor == f.setor)
    return select(Equipamento).outerjoin(Usuario, Usuario.id == Equipamento.usuario_id).where(*cond)


def _ordenada(consulta, f: Filtros):
    coluna = ORDENACAO.get(f.ordenar, ORDENACAO["patrimonio"])
    ordem = coluna.desc() if f.direcao == "desc" else coluna.asc()
    return consulta.order_by(ordem.nulls_last(), Equipamento.id)


def listar(s: Session, f: Filtros) -> tuple[list[Equipamento], int]:
    consulta = _consulta(f)
    total = s.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    itens = s.scalars(_ordenada(consulta, f).offset((f.pagina - 1) * f.por_pagina)
                      .limit(f.por_pagina)).unique()
    return list(itens), total


def todos(s: Session, f: Filtros) -> list[Equipamento]:
    """Mesmos filtros da tela, sem paginação (para exportar)."""
    return list(s.scalars(_ordenada(_consulta(f), f)).unique())


def contagem_por_situacao(s: Session) -> dict[str, int]:
    return dict(s.execute(select(Equipamento.situacao, func.count(Equipamento.id))
                          .group_by(Equipamento.situacao)).all())


def obter(s: Session, equipamento_id: int) -> Equipamento | None:
    return s.get(Equipamento, equipamento_id)


# ─── cadastro e edição ──────────────────────────────────────────────────────

def _texto(dados: dict, campo: str, rotulo: str, maximo: int) -> str | None:
    valor = " ".join((dados.get(campo) or "").split())
    if len(valor) > maximo:
        raise ErroValidacao(f"{rotulo}: no máximo {maximo} caracteres.")
    return valor or None


def _ip(valor: str) -> str | None:
    valor = (valor or "").strip()
    if not valor:
        return None
    try:
        return str(ipaddress.ip_address(valor))
    except ValueError:
        raise ErroValidacao(f"IP inválido: {valor}") from None


def _mac(valor: str) -> str | None:
    digitos = re.sub(r"[^0-9A-Fa-f]", "", valor or "")
    if not digitos:
        return None
    if len(digitos) != 12:
        raise ErroValidacao(f"MAC inválido: {valor} (use 12 dígitos, ex.: AA:BB:CC:DD:EE:FF)")
    return ":".join(digitos[i:i + 2] for i in range(0, 12, 2)).upper()


def _validar(s: Session, dados: dict, atual: Equipamento | None) -> dict:
    patrimonio = " ".join((dados.get("patrimonio") or "").split())
    if not patrimonio or len(patrimonio) > 50:
        raise ErroValidacao("Informe o nº de patrimônio (até 50 caracteres).")
    repetido = s.scalar(select(Equipamento.id).where(func.lower(Equipamento.patrimonio) == patrimonio.lower()))
    if repetido and (atual is None or repetido != atual.id):
        raise ErroValidacao(f"Já existe um equipamento com o patrimônio {patrimonio}.")
    if dados.get("tipo") not in TIPOS_EQUIPAMENTO:
        raise ErroValidacao("Escolha o tipo do equipamento.")
    if dados.get("situacao") not in SITUACOES:
        raise ErroValidacao("Escolha a situação do equipamento.")
    setor = dados.get("setor") or None
    if setor is not None and setor not in SETORES:
        raise ErroValidacao("Setor inválido.")

    usuario = None
    uid = str(dados.get("usuario_id") or "")
    if uid:
        usuario = s.get(Usuario, int(uid)) if uid.isdigit() else None
        if usuario is None or (not usuario.ativo and (atual is None or atual.usuario_id != usuario.id)):
            raise ErroValidacao("Escolha um usuário ativo.")

    valores = {"patrimonio": patrimonio, "tipo": dados["tipo"], "situacao": dados["situacao"],
               "setor": setor, "usuario": usuario, "ip": _ip(dados.get("ip")), "mac": _mac(dados.get("mac")),
               "observacoes": (dados.get("observacoes") or "").strip() or None}
    for campo, (rotulo, maximo) in CAMPOS_TEXTO.items():
        valores[campo] = _texto(dados, campo, rotulo, maximo)

    # Regras práticas de atribuição
    if valores["usuario"] is not None and valores["setor"] is None:
        valores["setor"] = valores["usuario"].setor           # com a pessoa → setor dela
    if valores["situacao"] == SITUACAO_DESCARTADO:
        valores["usuario"], valores["setor"] = None, None      # descartado não fica com ninguém
    elif valores["situacao"] == SITUACAO_ESTOQUE and (valores["usuario"] or valores["setor"]):
        valores["situacao"] = SITUACAO_USO                     # atribuído deixa de estar em estoque
    return valores


def _nome(u: Usuario | None) -> str:
    return u.nome if u else "ninguém"


def salvar(s: Session, atual: Equipamento | None, dados: dict, autor: Usuario) -> Equipamento:
    """Cria (atual=None) ou atualiza o equipamento e registra o que mudou no histórico."""
    v = _validar(s, dados, atual)

    if atual is None:
        eq = Equipamento(**{k: val for k, val in v.items() if k != "usuario"}, usuario=v["usuario"])
        s.add(eq)
        partes = [v["situacao"]]
        if v["setor"]:
            partes.append(f"setor {v['setor']}")
        if v["usuario"]:
            partes.append(f"com {v['usuario'].nome}")
        s.add(MovimentoEquipamento(equipamento=eq, autor_id=autor.id,
                                   descricao="Cadastrado: " + ", ".join(partes) + "."))
        s.commit()
        return eq

    eq = atual
    mudancas = []
    if v["setor"] != eq.setor:
        mudancas.append(f"Setor: {eq.setor or 'nenhum'} → {v['setor'] or 'nenhum'}")
    if (v["usuario"].id if v["usuario"] else None) != eq.usuario_id:
        mudancas.append(f"Usuário: {_nome(eq.usuario)} → {_nome(v['usuario'])}")
    if v["situacao"] != eq.situacao:
        mudancas.append(f"Situação: {eq.situacao} → {v['situacao']}")
    editados = [ROTULOS[c] for c in ROTULOS if v[c] != getattr(eq, c)]

    for campo, valor in v.items():
        setattr(eq, campo, valor)
    if editados:
        mudancas.append("Dados alterados: " + ", ".join(editados))
    if mudancas:
        s.add(MovimentoEquipamento(equipamento=eq, autor_id=autor.id, descricao=". ".join(mudancas) + "."))
    s.commit()
    return eq


def apagar(s: Session, eq: Equipamento) -> None:
    s.delete(eq)
    s.commit()


def usuarios_para_atribuir(s: Session) -> list[Usuario]:
    return list(s.scalars(select(Usuario).where(Usuario.ativo).order_by(Usuario.nome)))
