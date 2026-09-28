"""Dados de exemplo para testes e demonstração."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app import servicos
from app.modelos import (PAPEL_TECNICO, STATUS_AGUARDANDO, STATUS_ANDAMENTO, STATUS_FECHADO, Chamado,
                         Comentario, agora)

# login: (nome, setor, senha)  — o primeiro vira administrador
CONTAS = {
    "admin": ("Administrador do Sistema", "T.I", "admin123"),
    "carlos": ("Carlos Técnico", "T.I", "carlos123"),
    "ana": ("Ana Souza", "Fiscal", "ana12345"),
    "bruno": ("Bruno Lima", "Vendas", "bruno123"),
}


def popular(s: Session, chamados: bool = True) -> dict:
    u = {login: servicos.criar_conta(s, nome, login, "", setor, senha)
         for login, (nome, setor, senha) in CONTAS.items()}
    u["carlos"].papel = PAPEL_TECNICO
    s.commit()
    if not chamados:
        return u

    base = agora()
    exemplos = [
        ("Impressora do fiscal não imprime", "Fiscal", "Alta", "ana", None, None, 0),
        ("Sem acesso à pasta da rede", "RH", "Média", "bruno", STATUS_ANDAMENTO, "carlos", 1),
        ("Erro ao emitir nota fiscal", "Faturamento", "Alta", "ana", STATUS_AGUARDANDO, "admin", 2),
        ("Trocar teclado", "Vendas", "Baixa", "bruno", STATUS_FECHADO, "carlos", 5),
        ("E-mail não sincroniza no celular", "Diretoria", "Média", "ana", STATUS_FECHADO, "admin", 12),
        ("Instalar leitor de PDF", "Qualidade", "Baixa", "bruno", None, None, 3),
        ("Sistema lento no recebimento", "Recebimento", "Alta", "ana", STATUS_ANDAMENTO, "admin", 4),
        ("Monitor piscando", "Expedição", "Média", "bruno", STATUS_FECHADO, "carlos", 40),
    ]
    for i, (titulo, setor, prio, dono, status, resp, dias) in enumerate(exemplos):
        aberto = base - timedelta(days=dias, hours=i * 3)
        c = Chamado(titulo=titulo, descricao=f"{titulo}.\nDetalhes informados pelo usuário.",
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
