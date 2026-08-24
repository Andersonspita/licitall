from __future__ import annotations

from typing import Any

from src.models.enums import PNCP_CODE_TO_MODALITY, ModalityEnum
from src.models.schemas import TenderItem


def _exclusive_me_epp(item: dict[str, Any]) -> bool:
    raw = " ".join(
        str(item.get(key) or "")
        for key in ("beneficioMpeNome", "tipoBeneficioNome", "beneficio")
    ).lower()
    return "exclusiv" in raw or "me/epp" in raw or "me epp" in raw


def items_from_pncp(raw_items: list[dict[str, Any]]) -> list[TenderItem]:
    mapped: list[TenderItem] = []
    for raw in raw_items:
        numero = int(raw.get("numeroItem") or raw.get("numero") or 0)
        mapped.append(
            TenderItem(
                numero_item=numero,
                descricao=str(raw.get("descricao") or raw.get("descricaoDetalhada") or ""),
                catmat_catser=raw.get("catalogo")
                or raw.get("codigoCatalogo")
                or raw.get("materialOuServico"),
                quantidade=float(raw.get("quantidade") or 0),
                unidade_medida=str(raw.get("unidadeMedida") or raw.get("unidade") or "UN"),
                valor_unitario_estimado=float(raw.get("valorUnitarioEstimado") or 0),
                valor_total_estimado=float(raw.get("valorTotal") or raw.get("valorTotalEstimado") or 0),
                exclusivo_me_epp=_exclusive_me_epp(raw),
            )
        )
    return mapped


def extract_from_markdown(_markdown: str) -> dict[str, Any]:
    """Stub da Fase 3: extração LLM + Pydantic a partir do Markdown do Docling."""
    raise NotImplementedError(
        "TenderExtractionAgent será implementado na Fase 3 (LangGraph + schema Pydantic)."
    )


def modality_from_pncp(item: dict[str, Any]) -> ModalityEnum:
    code = item.get("modalidadeId") or item.get("codigoModalidadeContratacao")
    if isinstance(code, int) and code in PNCP_CODE_TO_MODALITY:
        return PNCP_CODE_TO_MODALITY[code]
    name = str(item.get("modalidadeNome") or "").lower()
    if "pregão" in name or "pregao" in name:
        return ModalityEnum.PREGAO_ELETRONICO
    if "concorr" in name:
        return ModalityEnum.CONCORRENCIA
    if "dispensa" in name:
        return ModalityEnum.DISPENSA_ELETRONICA
    return ModalityEnum.PREGAO_ELETRONICO


# Reexport para o grafo futuro
TenderExtractionAgent = extract_from_markdown
