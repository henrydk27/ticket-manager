"""Dados de exemplo para testes e demonstração."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app import servicos
from app.modelos import (PAPEL_ADMIN, PAPEL_USUARIO, STATUS_AGUARDANDO, STATUS_ANDAMENTO,
                         STATUS_FECHADO, Chamado, Comentario, agora)

# login: (nome, setor, senha, atende chamados do setor)  — o primeiro vira administrador
CONTAS = {
    "admin": ("Administrador do Sistema", "T.I", "admin123", True),
    "carlos": ("Carlos Técnico", "T.I", "carlos123", True),
    "marta": ("Marta Manutenção", "Manutenção", "marta123", True),
    "rita": ("Rita Recursos Humanos", "RH", "rita1234", True),
    "ana": ("Ana Souza", "Fiscal", "ana12345", False),
    "bruno": ("Bruno Lima", "Vendas", "bruno123", False),
}


def popular(s: Session, chamados: bool = True) -> dict:
    u = {}
    for login, (nome, setor, senha, atende) in CONTAS.items():
        conta = servicos.criar_conta(s, nome, login, f"{login}@empresa.com.br", setor, senha)
        servicos.atualizar_usuario(s, conta, setor, atende,
                                   PAPEL_ADMIN if login == "admin" else PAPEL_USUARIO)
        u[login] = conta
    if not chamados:
        return u

    base = agora()
    exemplos = [
        # título, para o setor, prioridade, quem pediu, status, responsável, dias atrás
        ("Impressora do fiscal não imprime", "T.I", "Alta", "ana", None, "carlos", 0),
        ("Sem acesso à pasta da rede", "T.I", "Média", "bruno", STATUS_ANDAMENTO, "carlos", 1),
        ("Erro ao emitir nota fiscal", "T.I", "Alta", "ana", STATUS_AGUARDANDO, "admin", 2),
        ("Trocar teclado", "T.I", "Baixa", "bruno", STATUS_FECHADO, "carlos", 5),
        ("E-mail não sincroniza no celular", "T.I", "Média", "ana", STATUS_FECHADO, "admin", 12),
        ("Ar-condicionado da sala de reuniões pingando", "Manutenção", "Média", "bruno", None, "marta", 1),
        ("Tomada queimada na recepção", "Manutenção", "Alta", "ana", STATUS_ANDAMENTO, "marta", 3),
        ("Dúvida sobre saldo de férias", "RH", "Baixa", "bruno", None, "rita", 2),
        ("Monitor piscando", "T.I", "Média", "bruno", STATUS_FECHADO, "carlos", 40),
    ]
    for i, (titulo, destino, prio, dono, status, resp, dias) in enumerate(exemplos):
        aberto = base - timedelta(days=dias, hours=i * 3)
        c = Chamado(titulo=titulo, descricao=f"{titulo}.\nDetalhes informados por quem pediu.",
                    setor_destino=destino, prioridade=prio, setor=u[dono].setor,
                    solicitante_id=u[dono].id, responsavel_id=u[resp].id,
                    status=status or "Aberto", aberto_em=aberto, atualizado_em=aberto)
        if status == STATUS_FECHADO:
            c.fechado_em = aberto + timedelta(hours=20)
        if titulo.startswith("E-mail"):
            c.avaliacao, c.avaliado_em = "Bom", c.fechado_em
        s.add(c)
        s.add(Comentario(chamado=c, autor_id=u[dono].id, texto="Qualquer novidade me avise.",
                         criado_em=aberto + timedelta(minutes=30)))
    s.commit()
    return u
