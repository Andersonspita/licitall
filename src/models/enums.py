from enum import Enum


class ModalityEnum(str, Enum):
    PREGAO_ELETRONICO = "PREGAO_ELETRONICO"
    CONCORRENCIA = "CONCORRENCIA"
    DISPENSA_ELETRONICA = "DISPENSA_ELETRONICA"


class TenderStatus(str, Enum):
    INGESTED = "INGESTED"
    DOCUMENTS_DOWNLOADED = "DOCUMENTS_DOWNLOADED"
    PARSED = "PARSED"
    EXTRACTED = "EXTRACTED"
    ANALYZED = "ANALYZED"
    MATCHED = "MATCHED"
    NOTIFIED = "NOTIFIED"
    FAILED = "FAILED"


class LegalAction(str, Enum):
    IMPUGNACAO = "IMPUGNACAO"
    PEDIDO_ESCLARECIMENTO = "PEDIDO_ESCLARECIMENTO"
    REGULAR = "REGULAR"


class CompanySize(str, Enum):
    ME = "ME"
    EPP = "EPP"
    DEMAIS = "DEMAIS"
    NAO_INFORMADO = "NAO_INFORMADO"


# Códigos oficiais da tabela de domínio do PNCP (manual da API de Consultas).
PNCP_MODALITY_CODES: dict[ModalityEnum, int] = {
    ModalityEnum.CONCORRENCIA: 4,  # Concorrência Eletrônica
    ModalityEnum.PREGAO_ELETRONICO: 6,
    ModalityEnum.DISPENSA_ELETRONICA: 8,  # Dispensa de Licitação
}

PNCP_CODE_TO_MODALITY: dict[int, ModalityEnum] = {
    code: modality for modality, code in PNCP_MODALITY_CODES.items()
}

DEFAULT_INGESTION_MODALITIES: tuple[ModalityEnum, ...] = (
    ModalityEnum.PREGAO_ELETRONICO,
    ModalityEnum.CONCORRENCIA,
    ModalityEnum.DISPENSA_ELETRONICA,
)
