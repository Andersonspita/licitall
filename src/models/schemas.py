from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from src.models.enums import LegalAction, ModalityEnum


class CitedText(BaseModel):
    """Trecho do edital com citação obrigatória (anti-alucinação)."""

    texto: str
    pagina: Optional[int] = None
    paragrafo: Optional[str] = None
    secao: Optional[str] = None


class TenderItem(BaseModel):
    numero_item: int
    descricao: str
    catmat_catser: Optional[str] = None
    quantidade: float = 0
    unidade_medida: str = "UN"
    valor_unitario_estimado: float = 0
    valor_total_estimado: float = 0
    exclusivo_me_epp: bool = False
    pagina_referencia: Optional[int] = None
    paragrafo_referencia: Optional[str] = None


class LegalRiskItem(BaseModel):
    clausula: str
    motivo_risco: str
    fundamentacao_legal: str
    sugestao_acao: LegalAction | str
    pagina_referencia: Optional[int] = None
    paragrafo_referencia: Optional[str] = None


class RequiredDocument(BaseModel):
    """Documento de habilitação somente se constar no edital."""

    categoria: str  # juridica | fiscal | economico_financeira | tecnica
    descricao: str
    pagina: Optional[int] = None
    paragrafo: Optional[str] = None


class MeEppBenefits(BaseModel):
    exclusivo_me_epp: bool = False
    cota_reservada_25: bool = False
    observacao: Optional[str] = None
    fundamentacao: str = "LC 123/2006, Art. 48 c/c Art. 4º da Lei 14.133/2021"
    citacao: Optional[CitedText] = None


class TenderSchema(BaseModel):
    id_pncp: str
    orgao_comprador: str
    cnpj_orgao: str
    uf: str
    municipio: str
    modalidade: ModalityEnum
    objeto_resumido: str
    cnaes_compativeis: list[str] = Field(default_factory=list)
    data_abertura_propostas: Optional[datetime] = None
    data_sessao_disputa: Optional[datetime] = None
    limite_impugnacao: Optional[datetime] = None
    limite_impugnacao_fonte: Optional[str] = Field(
        default=None,
        description="edital | calculado_art_164 — nunca inventar prazo sem base",
    )
    valor_total_estimado: float = 0
    itens: list[TenderItem] = Field(default_factory=list)
    riscos_juridicos: list[LegalRiskItem] = Field(default_factory=list)
    documentos_exigidos: list[str] = Field(default_factory=list)
    documentos_habilitacao: list[RequiredDocument] = Field(default_factory=list)
    beneficios_me_epp: Optional[MeEppBenefits] = None
    objeto_citacao: Optional[CitedText] = None
    marco_legal: str = "Lei Federal nº 14.133/2021"
    avisos: list[str] = Field(default_factory=list)


class DocumentRef(BaseModel):
    """Trecho extraído pelo Docling com citação obrigatória de página/parágrafo."""

    pagina: int
    paragrafo: str
    texto: str
    secao: Optional[str] = None


class TenderExtractionResult(BaseModel):
    """Resultado da Fase 2: schema + lacunas explícitas (sem inventar)."""

    tender: TenderSchema
    missing_fields: list[str] = Field(default_factory=list)
    sections_found: list[str] = Field(default_factory=list)
    engine: str = "heuristic"
    source_files: list[str] = Field(default_factory=list)
