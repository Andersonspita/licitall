from __future__ import annotations

from src.models.schemas import LegalRiskItem

LEGAL_CORPUS_HINTS = (
    "Lei Federal nº 14.133/2021",
    "Lei Complementar nº 123/2006",
    "Jurisprudência consolidada do TCU",
)

RESTRICTIVE_PATTERNS = (
    "exigência de marca sem justificativa",
    "capital social mínimo acima de 10%",
    "prazo de vistoria técnica incompatível com o Art. 63",
)


def analyze_legal_risks(_markdown: str) -> list[LegalRiskItem]:
    """Stub da Fase 3: RAG jurídico (pgvector + Lei 14.133/2021 + súmulas TCU)."""
    raise NotImplementedError(
        "LegalValidationAgent será implementado na Fase 3 com base vetorial pgvector."
    )
