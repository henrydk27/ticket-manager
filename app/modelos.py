"""Tabelas do sistema (SQLAlchemy). Mudanças de estrutura: ver migracoes/ (Alembic)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# ─── valores fixos ──────────────────────────────────────────────────────────

# Quem atende chamados é marcado pelo admin (Usuario.atende), junto com o setor da pessoa
PAPEL_USUARIO, PAPEL_ADMIN = "usuario", "admin"
PAPEIS = {PAPEL_USUARIO: "Usuário", PAPEL_ADMIN: "Administrador"}

STATUS_ABERTO, STATUS_ANDAMENTO, STATUS_AGUARDANDO, STATUS_FECHADO = (
    "Aberto", "Em andamento", "Aguardando usuário", "Fechado")
STATUS = [STATUS_ABERTO, STATUS_ANDAMENTO, STATUS_AGUARDANDO, STATUS_FECHADO]

PRIORIDADES = ["Alta", "Média", "Baixa"]
AVALIACOES = ["Bom", "Regular", "Ruim"]
SETORES = [
    "Contábil", "Diretoria", "Enfermaria", "Engenharia", "Expedição", "Fábrica",
    "Faturamento", "Financeiro", "Fiscal", "Inspeção", "Manutenção", "Portaria",
    "Qualidade", "Recebimento", "RH", "T.I", "Vendas",
]


def agora() -> datetime:
    """Hora local do servidor, sem fuso (o servidor deve estar em America/Sao_Paulo)."""
    return datetime.now().replace(microsecond=0)


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    login: Mapped[str] = mapped_column(String(50), unique=True)  # sempre minúsculo
    email: Mapped[str | None] = mapped_column(String(150))
    setor: Mapped[str] = mapped_column(String(50))
    atende: Mapped[bool] = mapped_column(Boolean, default=False)  # recebe chamados do seu setor
    senha_hash: Mapped[str] = mapped_column(String(255))
    papel: Mapped[str] = mapped_column(String(20), default=PAPEL_USUARIO)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    trocar_senha: Mapped[bool] = mapped_column(Boolean, default=False)  # após reset pelo admin
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    ultimo_acesso: Mapped[datetime | None] = mapped_column(DateTime)

    @property
    def is_admin(self) -> bool:
        return self.papel == PAPEL_ADMIN

    @property
    def is_atendente(self) -> bool:
        """Atende chamados do seu setor (o administrador atende todos)."""
        return self.is_admin or (self.atende and self.ativo)

    @property
    def papel_nome(self) -> str:
        return PAPEIS.get(self.papel, self.papel)

    def trabalha_em(self, chamado: "Chamado") -> bool:
        """Pode atender o chamado: assumir, mudar status, encaminhar."""
        return self.is_admin or (self.atende and self.ativo and chamado.setor_destino == self.setor)

    def pode_ver(self, chamado: "Chamado") -> bool:
        return chamado.solicitante_id == self.id or self.trabalha_em(chamado)


class Chamado(Base):
    __tablename__ = "chamados"
    __table_args__ = (
        Index("ix_chamados_status", "status"),
        Index("ix_chamados_solicitante", "solicitante_id"),
        Index("ix_chamados_responsavel", "responsavel_id"),
        Index("ix_chamados_aberto_em", "aberto_em"),
        Index("ix_chamados_setor_destino", "setor_destino"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titulo: Mapped[str] = mapped_column(String(150))
    descricao: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default=STATUS_ABERTO)
    prioridade: Mapped[str] = mapped_column(String(10))
    setor: Mapped[str] = mapped_column(String(50))  # setor de quem pediu (origem)
    setor_destino: Mapped[str] = mapped_column(String(50))  # setor que atende
    solicitante_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    responsavel_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    aberto_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=agora, onupdate=agora)
    fechado_em: Mapped[datetime | None] = mapped_column(DateTime)
    avaliacao: Mapped[str | None] = mapped_column(String(10))
    avaliado_em: Mapped[datetime | None] = mapped_column(DateTime)

    solicitante: Mapped[Usuario] = relationship(foreign_keys=[solicitante_id], lazy="joined")
    responsavel: Mapped[Usuario | None] = relationship(foreign_keys=[responsavel_id], lazy="joined")
    comentarios: Mapped[list["Comentario"]] = relationship(
        back_populates="chamado", cascade="all, delete-orphan", passive_deletes=True,
        order_by="Comentario.criado_em, Comentario.id")
    anexos: Mapped[list["Anexo"]] = relationship(
        back_populates="chamado", cascade="all, delete-orphan", passive_deletes=True,
        order_by="Anexo.id")

    @property
    def fechado(self) -> bool:
        return self.status == STATUS_FECHADO


class Comentario(Base):
    __tablename__ = "comentarios"
    __table_args__ = (Index("ix_comentarios_chamado", "chamado_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chamado_id: Mapped[int] = mapped_column(ForeignKey("chamados.id", ondelete="CASCADE"))
    autor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    texto: Mapped[str] = mapped_column(Text)
    evento: Mapped[bool] = mapped_column(Boolean, default=False)  # registro automático (status etc.)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    chamado: Mapped[Chamado] = relationship(back_populates="comentarios")
    autor: Mapped[Usuario] = relationship(lazy="joined")
    anexos: Mapped[list["Anexo"]] = relationship(back_populates="comentario", order_by="Anexo.id")


class Anexo(Base):
    """O arquivo fica em disco (config: anexos_pasta); aqui só o registro."""
    __tablename__ = "anexos"
    __table_args__ = (Index("ix_anexos_chamado", "chamado_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chamado_id: Mapped[int] = mapped_column(ForeignKey("chamados.id", ondelete="CASCADE"))
    comentario_id: Mapped[int | None] = mapped_column(ForeignKey("comentarios.id", ondelete="SET NULL"))
    autor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    nome: Mapped[str] = mapped_column(String(255))
    tipo: Mapped[str] = mapped_column(String(100))
    tamanho: Mapped[int] = mapped_column(Integer)
    arquivo: Mapped[str] = mapped_column(String(100), unique=True)  # nome em disco (aleatório)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    chamado: Mapped[Chamado] = relationship(back_populates="anexos")
    comentario: Mapped[Comentario | None] = relationship(back_populates="anexos")


class TentativaLogin(Base):
    """Senhas erradas recentes, para bloquear força bruta (vale para todos os processos)."""
    __tablename__ = "tentativas_login"
    __table_args__ = (Index("ix_tentativas_chave_momento", "chave", "momento"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chave: Mapped[str] = mapped_column(String(120))
    momento: Mapped[datetime] = mapped_column(DateTime, default=agora)

