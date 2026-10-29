"""Tabelas do sistema (SQLAlchemy). Mudanças de estrutura: ver migracoes/ (Alembic)."""

import json
import re
from datetime import date, datetime, timedelta

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, validates

# ─── valores fixos ──────────────────────────────────────────────────────────

# Nível de acesso (papel) define as telas; "Atende chamados" (Usuario.atende) só define quem
# recebe e atende os chamados do próprio setor.
#   usuário:       Chamados e Painel
#   supervisor:    Chamados, Painel, Relatório e Documentos (vê os chamados do próprio setor)
#   administrador: tudo
PAPEL_USUARIO, PAPEL_SUPERVISOR, PAPEL_ADMIN = "usuario", "supervisor", "admin"
PAPEIS = {PAPEL_USUARIO: "Usuário", PAPEL_SUPERVISOR: "Supervisor", PAPEL_ADMIN: "Administrador"}

STATUS_ABERTO, STATUS_ANDAMENTO, STATUS_AGUARDANDO, STATUS_FECHADO = (
    "Aberto", "Em andamento", "Aguardando usuário", "Fechado")
STATUS = [STATUS_ABERTO, STATUS_ANDAMENTO, STATUS_AGUARDANDO, STATUS_FECHADO]

PRIORIDADES = ["Alta", "Média", "Baixa"]
AVALIACOES = ["Bom", "Regular", "Ruim"]
SETORES = [
    "Administração", "Compras", "Contábil", "Diretoria", "Enfermaria", "Engenharia", "Expedição", "Fábrica",
    "Faturamento", "Ferramentaria", "Financeiro", "Fiscal", "Inspeção", "Manutenção", "PCP",
    "Portaria", "Qualidade", "Recebimento", "RH", "Segurança do Trabalho", "T.I", "Vendas",
]

# Inventário
TIPOS_EQUIPAMENTO = [
    "Desktop", "Notebook", "TV/Monitor", "Impressora", "Celular", "Tablet", "Telefone IP",
    "Nobreak", "Switch/Roteador", "Servidor", "Periférico", "Outro",
]
TIPOS_COMPUTADOR = {"Desktop", "Notebook", "Servidor"}  # mostram os campos de configuração
SITUACAO_USO, SITUACAO_ESTOQUE, SITUACAO_MANUTENCAO, SITUACAO_DESCARTADO = (
    "Em uso", "Em estoque", "Em manutenção", "Descartado")
SITUACOES = [SITUACAO_USO, SITUACAO_ESTOQUE, SITUACAO_MANUTENCAO, SITUACAO_DESCARTADO]

# Revisão preventiva dos ativos
SETOR_TI = "T.I"                      # quem atende a T.I registra preventivas e recebe os chamados delas
RESULTADO_OK, RESULTADO_CORRIGIDO, RESULTADO_PROBLEMA, RESULTADO_NA = (
    "OK", "Corrigido", "Problema", "Não se aplica")
RESULTADOS_ITEM = [RESULTADO_OK, RESULTADO_CORRIGIDO, RESULTADO_PROBLEMA, RESULTADO_NA]
_ITENS_COMPUTADOR = [
    "Limpeza interna e das saídas de ar", "Pasta térmica (trocar se necessário)", "Windows Update",
    "Antivírus atualizado", "Saúde do disco (SMART) e espaço livre", "Temperatura e ventoinhas",
    "Cabos, conectores e periféricos", "Backup dos dados do usuário",
]
# tipo: (a cada quantos meses, itens do checklist) — o admin ajusta em Preventivas → Planos
PLANOS_PADRAO = {
    "Desktop": (6, _ITENS_COMPUTADOR),
    "Notebook": (6, _ITENS_COMPUTADOR + ["Bateria e carregador", "Teclado, tela e dobradiças"]),
    "Servidor": (3, ["Limpeza interna e ventilação", "Atualizações do sistema", "Saúde dos discos / RAID",
                     "Espaço livre", "Backup executado e testado", "Logs e serviços", "Temperatura"]),
    "TV/Monitor": (12, ["Limpeza da tela e ventilação", "Cabos e conectores", "Imagem sem falhas"]),
    "Impressora": (3, ["Limpeza interna", "Roletes de tração", "Toner / cilindro", "Contador de páginas anotado",
                       "Teste de impressão"]),
    "Celular": (12, ["Atualização do sistema", "Bateria", "Tela e carcaça", "Backup"]),
    "Tablet": (12, ["Atualização do sistema", "Bateria", "Tela e carcaça", "Backup"]),
    "Telefone IP": (12, ["Funcionamento e áudio", "Cabos", "Firmware"]),
    "Nobreak": (12, ["Teste de bateria e autonomia", "Data da última troca de bateria", "Limpeza e ventilação",
                     "Carga ligada dentro da capacidade"]),
    "Switch/Roteador": (12, ["Limpeza e ventilação", "Cabos e portas", "Firmware", "Portas com erro"]),
    "Periférico": (0, []),
    "Outro": (0, []),
}

# Documentos internos (termos, regras...)
CATEGORIA_CONTRATOS = "Contratos"
CATEGORIAS_DOCUMENTO = ["Termos", CATEGORIA_CONTRATOS, "Regras e políticas", "Procedimentos", "Formulários", "Outros"]
AVISO_VENCIMENTO_DIAS = 30              # contrato "vence em breve" nos últimos 30 dias
LEMBRAR_VENCIDO_DIAS = 60               # o e-mail semanal lembra de contrato vencido por até 60 dias


# Quanto tempo a pessoa tem para criar a senha depois que o admin cadastra ou libera
PRAZO_CRIAR_SENHA = timedelta(days=7)


def ordem_natural(texto: str | None) -> str:
    """Texto que ordena números pelo valor: "2" < "10" < "000123" = "123"; letras sem diferenciar caixa."""
    return re.sub(r"\d+", lambda m: m.group().lstrip("0").rjust(15, "0"), (texto or "").lower())[:500]


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
    # Conta cadastrada pelo admin ou nova senha liberada: a pessoa cria a senha ao entrar
    senha_liberada_em: Mapped[datetime | None] = mapped_column(DateTime)
    # Pedido de nova senha feito na tela de login (o CPD recebe um e-mail)
    senha_solicitada_em: Mapped[datetime | None] = mapped_column(DateTime)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    ultimo_acesso: Mapped[datetime | None] = mapped_column(DateTime)

    @property
    def is_admin(self) -> bool:
        return self.papel == PAPEL_ADMIN

    @property
    def is_supervisor(self) -> bool:
        return self.papel == PAPEL_SUPERVISOR

    @property
    def is_atendente(self) -> bool:
        """Atende chamados do seu setor (o administrador atende todos)."""
        return self.is_admin or (self.atende and self.ativo)

    @property
    def ve_setor(self) -> bool:
        """Vê os chamados enviados ao próprio setor: quem atende e o supervisor."""
        return self.is_admin or (self.ativo and (self.atende or self.is_supervisor))

    # Telas liberadas pelo nível de acesso (independe de "Atende chamados")
    @property
    def ve_relatorio(self) -> bool:
        return self.is_admin or self.is_supervisor

    @property
    def ve_documentos(self) -> bool:
        return self.is_admin or self.is_supervisor

    @property
    def papel_nome(self) -> str:
        return PAPEIS.get(self.papel, self.papel)

    @property
    def pode_criar_senha(self) -> bool:
        """Senha liberada pelo admin e ainda no prazo: ao entrar, a pessoa cria a própria senha."""
        return (self.ativo and self.senha_liberada_em is not None
                and agora() - self.senha_liberada_em <= PRAZO_CRIAR_SENHA)

    @property
    def prazo_senha_vencido(self) -> bool:
        return self.senha_liberada_em is not None and not self.pode_criar_senha

    def trabalha_em(self, chamado: "Chamado") -> bool:
        """Pode atender o chamado: assumir, mudar status, encaminhar."""
        return self.is_admin or (self.atende and self.ativo and chamado.setor_destino == self.setor)

    def pode_ver(self, chamado: "Chamado") -> bool:
        return (chamado.solicitante_id == self.id or self.trabalha_em(chamado)
                or (self.ve_setor and chamado.setor_destino == self.setor))

    @property
    def cuida_inventario(self) -> bool:
        """Só administradores acessam o inventário."""
        return self.is_admin

    @property
    def faz_preventiva(self) -> bool:
        """Registra preventivas: administradores e quem atende a T.I."""
        return self.is_admin or (self.ativo and self.atende and self.setor == SETOR_TI)


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
    # Correção feita pelo administrador (o texto mostra "editado por ... em ...")
    editado_em: Mapped[datetime | None] = mapped_column(DateTime)
    editado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))

    chamado: Mapped[Chamado] = relationship(back_populates="comentarios")
    autor: Mapped[Usuario] = relationship(lazy="joined", foreign_keys=[autor_id])
    editado_por: Mapped[Usuario | None] = relationship(lazy="joined", foreign_keys=[editado_por_id])
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



class Equipamento(Base):
    """Ativo de TI. O patrimônio é o número que já vem colado no equipamento."""
    __tablename__ = "equipamentos"
    __table_args__ = (
        Index("ix_equipamentos_setor", "setor"),
        Index("ix_equipamentos_usuario", "usuario_id"),
        Index("ix_equipamentos_situacao", "situacao"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patrimonio: Mapped[str] = mapped_column(String(50), unique=True)
    # chave de ordenação "natural" (2 antes de 10), preenchida sozinha ao gravar o patrimônio
    patrimonio_ordem: Mapped[str] = mapped_column(String(500), default="")
    tipo: Mapped[str] = mapped_column(String(30))
    marca: Mapped[str | None] = mapped_column(String(60))
    modelo: Mapped[str | None] = mapped_column(String(100))
    numero_serie: Mapped[str | None] = mapped_column(String(100))
    situacao: Mapped[str] = mapped_column(String(20), default=SITUACAO_ESTOQUE)
    setor: Mapped[str | None] = mapped_column(String(50))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    # computador
    processador: Mapped[str | None] = mapped_column(String(100))
    memoria: Mapped[str | None] = mapped_column(String(50))
    armazenamento: Mapped[str | None] = mapped_column(String(100))
    sistema_operacional: Mapped[str | None] = mapped_column(String(100))
    licenca_windows: Mapped[str | None] = mapped_column(String(29))  # XXXXX-XXXXX-XXXXX-XXXXX-XXXXX
    # Preventiva: None = usa o plano do tipo; 0 = não faz; N = a cada N meses
    preventiva_meses: Mapped[int | None] = mapped_column(Integer)
    # rede
    hostname: Mapped[str | None] = mapped_column(String(100))
    ip: Mapped[str | None] = mapped_column(String(45))
    mac: Mapped[str | None] = mapped_column(String(17))
    observacoes: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=agora, onupdate=agora)

    usuario: Mapped[Usuario | None] = relationship(lazy="joined")
    historico: Mapped[list["MovimentoEquipamento"]] = relationship(
        back_populates="equipamento", cascade="all, delete-orphan", passive_deletes=True,
        order_by="MovimentoEquipamento.momento.desc(), MovimentoEquipamento.id.desc()")
    preventivas: Mapped[list["Preventiva"]] = relationship(
        back_populates="equipamento", cascade="all, delete-orphan", passive_deletes=True,
        order_by="Preventiva.data.desc(), Preventiva.id.desc()")

    @validates("patrimonio")
    def _ao_gravar_patrimonio(self, _chave, valor):
        self.patrimonio_ordem = ordem_natural(valor)
        return valor

    @property
    def descricao(self) -> str:
        return " ".join(p for p in (self.marca, self.modelo) if p) or self.tipo

    @property
    def e_computador(self) -> bool:
        return self.tipo in TIPOS_COMPUTADOR


class MovimentoEquipamento(Base):
    """Histórico: cadastro, trocas de setor/usuário/situação e edições."""
    __tablename__ = "movimentos_equipamento"
    __table_args__ = (Index("ix_movimentos_equipamento", "equipamento_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipamento_id: Mapped[int] = mapped_column(ForeignKey("equipamentos.id", ondelete="CASCADE"))
    autor_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    momento: Mapped[datetime] = mapped_column(DateTime, default=agora)
    descricao: Mapped[str] = mapped_column(Text)

    equipamento: Mapped[Equipamento] = relationship(back_populates="historico")
    autor: Mapped[Usuario | None] = relationship(lazy="joined")


class Documento(Base):
    """Documento interno (termo, regra, procedimento). O arquivo fica em disco (anexos_pasta)."""
    __tablename__ = "documentos"
    __table_args__ = (Index("ix_documentos_categoria", "categoria"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titulo: Mapped[str] = mapped_column(String(150))
    categoria: Mapped[str] = mapped_column(String(40))
    descricao: Mapped[str | None] = mapped_column(Text)
    vencimento: Mapped[date | None] = mapped_column(Date)  # só para contratos
    nome: Mapped[str] = mapped_column(String(255))       # nome original do arquivo
    tipo: Mapped[str] = mapped_column(String(100))
    tamanho: Mapped[int] = mapped_column(Integer)
    arquivo: Mapped[str] = mapped_column(String(100), unique=True)  # nome em disco (aleatório)
    autor_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=agora, onupdate=agora)

    autor: Mapped[Usuario | None] = relationship(lazy="joined")

    @property
    def dias_para_vencer(self) -> int | None:
        return (self.vencimento - date.today()).days if self.vencimento else None

    @property
    def situacao_vencimento(self) -> str | None:
        """"vencido", "vence" (nos próximos 30 dias), "vigente" ou None (sem data)."""
        dias = self.dias_para_vencer
        if dias is None:
            return None
        return "vencido" if dias < 0 else ("vence" if dias <= AVISO_VENCIMENTO_DIAS else "vigente")


class Diagrama(Base):
    """Diagrama da infraestrutura (mapa da rede, câmeras...): imagem + arquivo editável do draw.io.
    Os arquivos ficam em disco (anexos_pasta), nunca no repositório."""
    __tablename__ = "diagramas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titulo: Mapped[str] = mapped_column(String(150))
    descricao: Mapped[str | None] = mapped_column(Text)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    nome: Mapped[str] = mapped_column(String(255))                   # imagem: nome original
    tamanho: Mapped[int] = mapped_column(Integer)
    arquivo: Mapped[str] = mapped_column(String(100), unique=True)   # imagem: nome em disco
    editavel_nome: Mapped[str | None] = mapped_column(String(255))
    editavel_tamanho: Mapped[int | None] = mapped_column(Integer)
    editavel_arquivo: Mapped[str | None] = mapped_column(String(100), unique=True)
    autor_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=agora, onupdate=agora)

    autor: Mapped[Usuario | None] = relationship(lazy="joined")


class PlanoPreventiva(Base):
    """Plano de preventiva de um tipo de equipamento (sem linha aqui, vale PLANOS_PADRAO)."""
    __tablename__ = "planos_preventiva"

    tipo: Mapped[str] = mapped_column(String(30), primary_key=True)
    meses: Mapped[int] = mapped_column(Integer, default=0)     # 0 = esse tipo não tem preventiva
    itens: Mapped[str] = mapped_column(Text, default="")       # um item do checklist por linha


class Preventiva(Base):
    """Revisão preventiva feita num equipamento, com o checklist preenchido."""
    __tablename__ = "preventivas"
    __table_args__ = (Index("ix_preventivas_equipamento", "equipamento_id"), Index("ix_preventivas_data", "data"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipamento_id: Mapped[int] = mapped_column(ForeignKey("equipamentos.id", ondelete="CASCADE"))
    data: Mapped[date] = mapped_column(Date)
    tecnico_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    resultados: Mapped[str] = mapped_column(Text, default="[]")   # JSON: [[item, resultado, nota], ...]
    pecas: Mapped[str | None] = mapped_column(Text)
    observacoes: Mapped[str | None] = mapped_column(Text)
    chamado_id: Mapped[int | None] = mapped_column(ForeignKey("chamados.id", ondelete="SET NULL"))
    # anexo opcional (ex.: foto), gravado na pasta dos anexos
    anexo_nome: Mapped[str | None] = mapped_column(String(255))
    anexo_arquivo: Mapped[str | None] = mapped_column(String(100), unique=True)
    anexo_tipo: Mapped[str | None] = mapped_column(String(100))
    anexo_tamanho: Mapped[int | None] = mapped_column(Integer)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    equipamento: Mapped[Equipamento] = relationship(back_populates="preventivas")
    tecnico: Mapped[Usuario | None] = relationship(lazy="joined")
    chamado: Mapped[Chamado | None] = relationship()

    @property
    def itens(self) -> list[tuple[str, str, str]]:
        try:
            return [(i[0], i[1], i[2] if len(i) > 2 else "") for i in json.loads(self.resultados or "[]")]
        except (ValueError, TypeError, IndexError):
            return []

    @property
    def problemas(self) -> list[tuple[str, str, str]]:
        return [i for i in self.itens if i[1] == RESULTADO_PROBLEMA]

    def contar(self, resultado: str) -> int:
        return sum(1 for i in self.itens if i[1] == resultado)
