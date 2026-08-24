from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from src.models.enums import LegalAction, ModalityEnum


class TenderItem(BaseModel):
    numero_item: int
    descricao: str
    catmat_catser: Optional[str] = None
    quantidade: float
    unidade_medida: str
    valor_unitario_estimado: float
    valor_total_estimado: float
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


class TenderSchema(BaseModel):
    id_pncp: str
    orgao_comprador: str
    cnpj_orgao: str
    uf: str
    municipio: str
    modalidade: ModalityEnum
    objeto_resumido: str
    cnaes_compativeis: list[str] = Field(default_factory=list)
    data_abertura_propostas: datetime
    data_sessao_disputa: datetime
    limite_impugnacao: datetime
    valor_total_estimado: float
    itens: list[TenderItem] = Field(default_factory=list)
    riscos_juridicos: list[LegalRiskItem] = Field(default_factory=list)
    documentos_exigidos: list[str] = Field(default_factory=list)


class DocumentRef(BaseModel):
    """Trecho extraído pelo Docling com citação obrigatória de página/parágrafo."""

    pagina: int
    paragrafo: str
    texto: str
    secao: Optional[str] = None
