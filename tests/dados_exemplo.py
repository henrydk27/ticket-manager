"""Dados de exemplo para testes e demonstração."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app import servicos
from app.modelos import (STATUS_AGUARDANDO, STATUS_ANDAMENTO, STATUS_FECHADO, Chamado, Comentario,
                         agora)

# login: (nome, setor, senha)  — o primeiro vira administrador
CONTAS = {
    "admin": ("Administrador do Sistema", "T.I", "admin123"),
    "carlos": ("Carlos Técnico", "T.I", "carlos123"),
    "marta": ("Marta Manutenção", "Manutenção", "marta123"),
    "ana": ("Ana Souza", "Fiscal", "ana12345"),
    "bruno": ("Bruno Lima", "Vendas", "bruno123"),
}

# fila: (descrição, atendentes, tipos de pedido)
FILAS = {
    "T.I": ("Computadores, impressoras, sistemas, acessos, rede e e-mail",
            ["admin", "carlos"], ["Acesso e senha", "Computador", "Impressora", "Sistemas"]),
    "Manutenção": ("Elétrica, hidráulica, ar-condicionado e predial",
                   ["marta"], ["Ar-condicionado", "Elétrica", "Hidráulica"]),
    "RH": ("Férias, benefícios, holerite e documentos", [], []),
}


def popular(s: Session, chamados: bool = True) -> dict:
    u = {login: servicos.criar_conta(s, nome, login, "", setor, senha)
         for login, (nome, setor, senha) in CONTAS.items()}
    filas = {}
    for nome, (descricao, atendentes, tipos) in FILAS.items():
        f = servicos.criar_fila(s, nome, descricao)
        servicos.definir_atendentes(s, f, [u[a].id for a in atendentes])
        for t in tipos:
            servicos.adicionar_categoria(s, f, t)
        filas[nome] = f
    u["_filas"] = filas
    if not chamados:
        return u

    def tipo(fila, nome):
        return next(c for c in filas[fila].categorias if c.nome == nome)

    base = agora()
    exemplos = [
        # título, fila, tipo, setor de origem, prioridade, quem pediu, status, responsável, dias atrás
        ("Impressora do fiscal não imprime", "T.I", "Impressora", "Fiscal", "Alta", "ana", None, None, 0),
        ("Sem acesso à pasta da rede", "T.I", "Acesso e senha", "Vendas", "Média", "bruno", STATUS_ANDAMENTO, "carlos", 1),
        ("Erro ao emitir nota fiscal", "T.I", "Sistemas", "Fiscal", "Alta", "ana", STATUS_AGUARDANDO, "admin", 2),
        ("Trocar teclado", "T.I", "Computador", "Vendas", "Baixa", "bruno", STATUS_FECHADO, "carlos", 5),
        ("E-mail não sincroniza no celular", "T.I", "Sistemas", "Fiscal", "Média", "ana", STATUS_FECHADO, "admin", 12),
        ("Ar-condicionado da sala de reuniões pingando", "Manutenção", "Ar-condicionado", "Vendas", "Média", "bruno", None, None, 1),
        ("Tomada queimada na recepção", "Manutenção", "Elétrica", "Fiscal", "Alta", "ana", STATUS_ANDAMENTO, "marta", 3),
        ("Dúvida sobre saldo de férias", "RH", None, "Vendas", "Baixa", "bruno", None, None, 2),
        ("Monitor piscando", "T.I", "Computador", "Vendas", "Média", "bruno", STATUS_FECHADO, "carlos", 40),
    ]
    for i, (titulo, fila, tp, setor, prio, dono, status, resp, dias) in enumerate(exemplos):
        aberto = base - timedelta(days=dias, hours=i * 3)
        c = Chamado(titulo=titulo, descricao=f"{titulo}.\nDetalhes informados por quem pediu.",
                    fila=filas[fila], categoria=tipo(fila, tp) if tp else None,
                    prioridade=prio, setor=setor, solicitante_id=u[dono].id,
                    status=status or "Aberto", aberto_em=aberto, atualizado_em=aberto,
                    responsavel_id=u[resp].id if resp else None)
        if status == STATUS_FECHADO:
            c.fechado_em = aberto + timedelta(hours=20)
        if titulo.startswith("E-mail"):
            c.avaliacao, c.avaliado_em = "Bom", c.fechado_em
        s.add(c)
        s.add(Comentario(chamado=c, autor_id=u[dono].id, texto="Qualquer novidade me avise.",
                         criado_em=aberto + timedelta(minutes=30)))
    s.commit()
    return u
