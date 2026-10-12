import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy import String
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TenderIngest(SQLModel, table=True):
    """Registro bruto da contratação minerada no PNCP, antes da extração semântica."""

    __tablename__ = "tender_ingest"

    id: Optional[int] = Field(default=None, primary_key=True)
    id_pncp: str = Field(index=True, unique=True, max_length=64)
    orgao_comprador: Optional[str] = Field(default=None, max_length=512)
    cnpj_orgao: Optional[str] = Field(default=None, max_length=14, index=True)
    uf: Optional[str] = Field(default=None, max_length=2, index=True)
    municipio: Optional[str] = Field(default=None, max_length=128)
    modalidade: Optional[str] = Field(default=None, max_length=64)
    objeto_resumido: Optional[str] = Field(default=None, sa_column=Column(Text))
    valor_total_estimado: Optional[float] = None
    situacao: Optional[str] = Field(default=None, max_length=128)
    data_publicacao: Optional[datetime] = None
    data_abertura_propostas: Optional[datetime] = None
    data_encerramento_propostas: Optional[datetime] = None
    status: str = Field(default="INGESTED", max_length=32, index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class TenderItemRow(SQLModel, table=True):
    """Item de uma contratação (PNCP /itens), base para o matching por item."""

    __tablename__ = "itens_contratacao"
    __table_args__ = (UniqueConstraint("id_pncp", "numero_item", name="unq_item_contratacao"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    id_pncp: str = Field(index=True, max_length=64)
    numero_item: int
    descricao: str = Field(default="", sa_column=Column(Text, nullable=False))
    tipo: Optional[str] = Field(default=None, max_length=1)  # M material / S serviço
    codigo_catmat_catser: Optional[int] = Field(default=None, index=True)
    quantidade: Optional[float] = None
    unidade_medida: Optional[str] = Field(default=None, max_length=30)
    valor_unitario_estimado: Optional[float] = None
    valor_total_estimado: Optional[float] = None
    exclusivo_me_epp: bool = False
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class InterestProfile(SQLModel, table=True):
    """Perfil de busca de um cliente; uma empresa pode ter vários."""

    __tablename__ = "perfis_interesse"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    empresa_id: str = Field(index=True, max_length=64)
    nome_perfil: str = Field(max_length=100)
    ufs_permitidas: list[str] = Field(
        default_factory=list, sa_column=Column(ARRAY(String(2)), nullable=False)
    )
    valor_minimo_item: float = 0.0
    valor_maximo_item: Optional[float] = None
    apenas_me_epp: bool = False
    ativo: bool = True
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ProfileKeywordRule(SQLModel, table=True):
    """Palavra-chave do perfil: OBRIGATORIA, POSITIVA ou NEGATIVA."""

    __tablename__ = "regras_palavras_chave"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    perfil_id: uuid.UUID = Field(foreign_key="perfis_interesse.id", index=True, ondelete="CASCADE")
    tipo: str = Field(max_length=15)
    termo: str = Field(max_length=100, index=True)


class ProfileCatalogRule(SQLModel, table=True):
    """Código CATMAT/CATSER de interesse do perfil."""

    __tablename__ = "regras_catalogo"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    perfil_id: uuid.UUID = Field(foreign_key="perfis_interesse.id", index=True, ondelete="CASCADE")
    codigo_item: int
    peso: float = 1.0


class EmbeddingCacheRow(SQLModel, table=True):
    """Cache de embeddings endereçável por conteúdo (SHA-256 do texto normalizado)."""

    __tablename__ = "embeddings_cache"

    content_hash: str = Field(primary_key=True, max_length=64)
    backend: str = Field(primary_key=True, max_length=32)  # ex.: "openai:512", "hash:512"
    texto_base: str = Field(sa_column=Column(Text, nullable=False))
    embedding: list[float] = Field(sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ProfileDescription(SQLModel, table=True):
    """Descrição sintética informada pelo cliente para o vetor semântico do perfil."""

    __tablename__ = "perfis_descricao"

    perfil_id: uuid.UUID = Field(foreign_key="perfis_interesse.id", primary_key=True, ondelete="CASCADE")
    descricao: str = Field(sa_column=Column(Text, nullable=False))


class MatchItem(SQLModel, table=True):
    """Resultado do matching de um item contra um perfil (busca reversa)."""

    __tablename__ = "matches_itens"
    __table_args__ = (UniqueConstraint("perfil_id", "id_pncp", "numero_item", name="unq_match_perfil_item"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    perfil_id: uuid.UUID = Field(foreign_key="perfis_interesse.id", index=True, ondelete="CASCADE")
    id_pncp: str = Field(index=True, max_length=64)
    numero_item: int
    score_catmat: float = 0.0
    score_lexico: float = 0.0
    score_semantico: float = 0.0
    score_total: float
    alerta: bool = False
    status: str = Field(default="NOVO", max_length=20, index=True)  # NOVO, ENVIADO, DESCARTADO, FAVORITO
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class DigestSchedule(SQLModel, table=True):
    """Envio diário agendado do digest de um perfil (um por perfil)."""

    __tablename__ = "digest_agendamentos"

    perfil_id: uuid.UUID = Field(foreign_key="perfis_interesse.id", primary_key=True, ondelete="CASCADE")
    telefone: str = Field(max_length=15)
    horario: str = Field(max_length=5)  # HH:MM em horário de Brasília
    top_n: int = 5
    instance: Optional[str] = Field(default=None, max_length=64)
    ativo: bool = True
    ultimo_envio_dia: Optional[date] = None
    ultima_tentativa: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    ultimo_status: Optional[str] = Field(default=None, max_length=300)


class TenderAttachment(SQLModel, table=True):
    """Arquivo do edital publicado no PNCP (guarda só a URL; o binário não vai para o banco)."""

    __tablename__ = "anexos_contratacao"
    __table_args__ = (UniqueConstraint("id_pncp", "url_download", name="unq_anexo_contratacao"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    id_pncp: str = Field(index=True, max_length=64)
    tipo_documento: Optional[str] = Field(default=None, max_length=100)
    titulo: Optional[str] = Field(default=None, sa_column=Column(Text))
    url_download: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class Empresa(SQLModel, table=True):
    """Cliente (tenant). Todos os perfis e resultados pertencem a uma empresa."""

    __tablename__ = "empresas"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    nome: str = Field(max_length=200)
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class Usuario(SQLModel, table=True):
    __tablename__ = "usuarios"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    empresa_id: uuid.UUID = Field(foreign_key="empresas.id", index=True)
    email: str = Field(max_length=254, unique=True, index=True)
    nome: str = Field(max_length=120)
    senha_hash: str = Field(max_length=300)
    is_admin: bool = False  # operador da plataforma (captação, pipeline, envios globais)
    ativo: bool = True
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    ultimo_login: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class Sessao(SQLModel, table=True):
    """Sessão de login. Guarda só o SHA-256 do token (o token em si vive no cookie)."""

    __tablename__ = "sessoes"

    token_hash: str = Field(primary_key=True, max_length=64)
    usuario_id: uuid.UUID = Field(foreign_key="usuarios.id", index=True, ondelete="CASCADE")
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, index=True))


class Certidao(SQLModel, table=True):
    """Documento de regularidade da empresa (CND, FGTS, CNDT...) com a data de validade."""

    __tablename__ = "certidoes"
    __table_args__ = (UniqueConstraint("empresa_id", "nome", name="unq_certidao_empresa_nome"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    empresa_id: uuid.UUID = Field(foreign_key="empresas.id", index=True, ondelete="CASCADE")
    nome: str = Field(max_length=200)
    validade: Optional[date] = None
    observacao: Optional[str] = Field(default=None, max_length=500)
    padrao: bool = False  # item da lista oficial; não pode ser removido
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class Atestado(SQLModel, table=True):
    """Atestado de capacidade técnica; a quantidade permite conferir exigências de editais."""

    __tablename__ = "atestados"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    empresa_id: uuid.UUID = Field(foreign_key="empresas.id", index=True, ondelete="CASCADE")
    objeto: str = Field(max_length=300)
    contratante: str = Field(max_length=200)
    data_emissao: Optional[date] = None
    quantidade: Optional[float] = None
    unidade: Optional[str] = Field(default=None, max_length=20)
    registro: Optional[str] = Field(default=None, max_length=120)  # nº da CAT / conselho
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
