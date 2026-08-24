from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
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
