from __future__ import annotations

from typing import Any

from src.agents.checklist import DocumentChecklist, build_checklist_from_parsed
from src.agents.extractor import build_tender_from_sources
from src.agents.legal_rag import analyze_legal_risks_from_parsed
from src.ingestion.client import PncpClient
from src.models.schemas import TenderExtractionResult
from src.parser.service import ParserService


class TenderPipeline:
    """Fase 2: parse Docling → extração Pydantic → checklist + triagem Lei 14.133."""

    def __init__(
        self,
        parser_service: ParserService | None = None,
    ) -> None:
        self.parser_service = parser_service or ParserService()

    async def run(
        self,
        id_pncp: str,
        *,
        pncp_payload: dict[str, Any] | None = None,
        fetch_pncp_itens: bool = True,
        persist_parse: bool = True,
    ) -> dict[str, Any]:
        parsed_docs = self.parser_service.parse_tender(id_pncp, persist=persist_parse)
        itens: list[dict[str, Any]] = []
        if fetch_pncp_itens:
            try:
                async with PncpClient() as client:
                    itens = await client.get_itens(id_pncp)
            except Exception:
                itens = []

        extraction: TenderExtractionResult = build_tender_from_sources(
            id_pncp=id_pncp,
            pncp_payload=pncp_payload,
            pncp_itens=itens,
            parsed_docs=parsed_docs,
        )

        checklist: DocumentChecklist = build_checklist_from_parsed(parsed_docs)
        risks = analyze_legal_risks_from_parsed(parsed_docs)

        tender = extraction.tender.model_copy(
            update={
                "documentos_habilitacao": (
                    checklist.habilitacao_juridica
                    + checklist.regularidade_fiscal_social_trabalhista
                    + checklist.qualificacao_economico_financeira
                    + checklist.qualificacao_tecnica
                ),
                "documentos_exigidos": checklist.as_flat_list(),
                "riscos_juridicos": risks,
            }
        )
        extraction = extraction.model_copy(update={"tender": tender})

        return {
            "extraction": extraction.model_dump(mode="json"),
            "parsed": [
                {
                    "file": str(doc.source_path),
                    "engine": doc.engine,
                    "sections": list(doc.sections.keys()),
                    "refs_count": len(doc.refs),
                    "meta": doc.meta,
                }
                for doc in parsed_docs
            ],
            "checklist": checklist.as_flat_list(),
            "riscos_count": len(risks),
            "marco_legal": "Lei Federal nº 14.133/2021",
        }
