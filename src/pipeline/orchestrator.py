"""Orquestração ponta a ponta de uma licitação (Fase 6 — integração operacional)."""

from __future__ import annotations

from typing import Any

from src.advisory import CompanyContext, build_document_kit, persist_kit
from src.advisory.kit import DocumentKit
from src.agents.pipeline import TenderPipeline
from src.ingestion.client import PncpClient
from src.ingestion.service import download_tender_documents
from src.ingestion.storage import DocumentStorage
from src.matching.service import MatchmakingResult, MatchmakingService
from src.outreach.service import OutreachPayload, OutreachService
from src.rag.retriever import ensure_legal_index


class FullPipelineResult:
    def __init__(
        self,
        *,
        id_pncp: str,
        downloaded: list[str],
        extraction: dict[str, Any],
        matching: MatchmakingResult | None,
        kit: DocumentKit,
        kit_files: list[str],
        whatsapp_preview: str | None,
        avisos: list[str],
    ) -> None:
        self.id_pncp = id_pncp
        self.downloaded = downloaded
        self.extraction = extraction
        self.matching = matching
        self.kit = kit
        self.kit_files = kit_files
        self.whatsapp_preview = whatsapp_preview
        self.avisos = avisos

    def to_dict(self) -> dict[str, Any]:
        return {
            "id_pncp": self.id_pncp,
            "marco_legal": "Lei Federal nº 14.133/2021",
            "fase": 6,
            "downloaded_files": self.downloaded,
            "extraction": self.extraction,
            "matching": self.matching.model_dump(mode="json") if self.matching else None,
            "kit": {
                "minutas": list(self.kit.minutas.keys()),
                "avisos": self.kit.avisos,
                "saved_files": self.kit_files,
            },
            "whatsapp_preview": self.whatsapp_preview,
            "avisos": self.avisos,
        }


async def run_full_pipeline(
    id_pncp: str,
    *,
    company: CompanyContext | None = None,
    download_if_missing: bool = True,
    persist_kit: bool = True,
    run_matching: bool = True,
    whatsapp_phone: str | None = None,
    send_whatsapp: bool = False,
    pncp_payload: dict[str, Any] | None = None,
) -> FullPipelineResult:
    """Fluxo: index RAG → download → parse/extract → match → kit → preview/envio WhatsApp."""
    avisos: list[str] = []
    await ensure_legal_index()

    storage = DocumentStorage()
    downloaded: list[str] = []
    existing = storage.list_files(id_pncp)
    parseable = [p for p in existing if p.suffix.lower() in {".pdf", ".docx", ".md", ".txt"}]

    if download_if_missing and not parseable:
        async with PncpClient() as client:
            downloaded = await download_tender_documents(client, storage, id_pncp)
        if not downloaded:
            avisos.append("Nenhum anexo baixado do PNCP para esta contratação.")
    else:
        avisos.append(f"Usando {len(parseable)} arquivo(s) já presentes em data/raw.")

    pipeline = TenderPipeline(use_rag=True)
    extracted = await pipeline.run(id_pncp, pncp_payload=pncp_payload, persist_parse=True)
    tender = (extracted.get("extraction") or {}).get("tender") or {}
    tender["id_pncp"] = id_pncp

    matching: MatchmakingResult | None = None
    if run_matching:
        matcher = MatchmakingService()
        try:
            matching = await matcher.match_tender(tender, limit=20)
            avisos.extend(matching.avisos)
        finally:
            await matcher.aclose()

    kit = build_document_kit(tender, company)
    kit_files: list[str] = []
    if persist_kit:
        try:
            kit_files = persist_kit(kit)
        except ValueError as exc:
            avisos.append(str(exc))

    preview: str | None = None
    outreach = OutreachService()
    try:
        payload = OutreachPayload(
            phone=whatsapp_phone or "5511000000000",
            orgao=str(tender.get("orgao_comprador") or "Órgão"),
            objeto=str(tender.get("objeto_resumido") or "")[:500],
            valor_total=float(tender.get("valor_total_estimado") or 0),
            id_pncp=id_pncp,
            checklist_resumo=(extracted.get("checklist") or [])[:6],
        )
        preview = outreach.build_message(payload)
        if send_whatsapp and whatsapp_phone:
            await outreach.notify_opportunity(payload)
            avisos.append("WhatsApp enviado via Evolution API.")
        elif send_whatsapp:
            avisos.append("send_whatsapp=true mas whatsapp_phone não informado.")
    finally:
        await outreach.aclose()

    avisos.extend(kit.avisos)
    return FullPipelineResult(
        id_pncp=id_pncp,
        downloaded=downloaded,
        extraction=extracted,
        matching=matching,
        kit=kit,
        kit_files=kit_files,
        whatsapp_preview=preview,
        avisos=avisos,
    )
