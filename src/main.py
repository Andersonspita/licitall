from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from src import __version__
from src.agents.pipeline import TenderPipeline
from src.config import get_settings
from src.db import get_session, init_db
from src.ingestion.client import PncpClient, PncpError
from src.ingestion.service import download_tender_documents, ingest_publicacoes
from src.ingestion.storage import DocumentStorage
from src.models.enums import DEFAULT_INGESTION_MODALITIES, ModalityEnum
from src.matching.service import MatchmakingService
from src.advisory import CompanyContext, build_document_kit, persist_kit
from src.outreach import OutreachPayload, OutreachService
from src.parser.service import ParserService
from src.rag.corpus import load_legal_corpus
from src.rag.retriever import ensure_legal_index, get_legal_store, retrieve_legal_context

logger = logging.getLogger("licitall")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        await init_db()
    except Exception as exc:
        logger.warning("PostgreSQL indisponível na inicialização: %s", exc)
    yield


app = FastAPI(
    title="LicitAll",
    description=(
        "Plataforma B2G de ingestão e assessoria pré-certame. "
        "Marco legal: Lei Federal nº 14.133/2021 (nova lei de licitações) e LC 123/2006."
    ),
    version=__version__,
    lifespan=lifespan,
)


class IngestRequest(BaseModel):
    data_inicial: date | None = None
    data_final: date | None = None
    uf: str | None = Field(default=None, min_length=2, max_length=2)
    only_open: bool = True
    modalidades: list[ModalityEnum] = Field(default_factory=lambda: list(DEFAULT_INGESTION_MODALITIES))


class IngestResponse(BaseModel):
    ingested: int
    uf: str | None
    data_inicial: date
    data_final: date


class DownloadResponse(BaseModel):
    id_pncp: str
    files: list[str]


class ParseResponse(BaseModel):
    id_pncp: str
    documents: list[dict[str, Any]]


@app.get("/health")
async def health() -> dict[str, Any]:
    settings = get_settings()
    parser = ParserService().parser
    return {
        "status": "ok",
        "version": __version__,
        "marco_legal": "Lei Federal nº 14.133/2021",
        "fase": "5-advisory-outreach",
        "docling_available": parser.docling_available,
        "legal_chunks": len(load_legal_corpus()),
        "raw_docs_dir": str(settings.raw_docs_path),
        "minha_receita": settings.minha_receita_base_url,
        "evolution_api": settings.evolution_api_url,
        "evolution_instance": settings.evolution_instance,
    }


@app.post("/ingestion/pncp/sync", response_model=IngestResponse)
async def sync_pncp(
    body: IngestRequest,
    session: AsyncSession = Depends(get_session),
) -> IngestResponse:
    today = date.today()
    data_final = body.data_final or today
    data_inicial = body.data_inicial or (data_final - timedelta(days=1))
    if data_inicial > data_final:
        raise HTTPException(status_code=422, detail="data_inicial não pode ser posterior a data_final.")
    try:
        async with PncpClient() as client:
            ingested = await ingest_publicacoes(
                session,
                client,
                data_inicial=data_inicial,
                data_final=data_final,
                uf=body.uf,
                modalidades=tuple(body.modalidades),
                only_open=body.only_open,
            )
    except PncpError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return IngestResponse(
        ingested=ingested,
        uf=body.uf,
        data_inicial=data_inicial,
        data_final=data_final,
    )


@app.post("/ingestion/pncp/{id_pncp:path}/documents", response_model=DownloadResponse)
async def download_documents(id_pncp: str) -> DownloadResponse:
    storage = DocumentStorage()
    try:
        async with PncpClient() as client:
            files = await download_tender_documents(client, storage, id_pncp)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PncpError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return DownloadResponse(id_pncp=id_pncp, files=files)


@app.get("/ingestion/pncp/{id_pncp:path}/itens")
async def list_itens(id_pncp: str) -> dict[str, Any]:
    try:
        async with PncpClient() as client:
            itens = await client.get_itens(id_pncp)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PncpError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"id_pncp": id_pncp, "itens": itens}


@app.get("/ingestion/modalidades")
async def modalidades() -> dict[str, list[str]]:
    return {"modalidades": [item.value for item in DEFAULT_INGESTION_MODALITIES]}


@app.post("/parser/{id_pncp:path}", response_model=ParseResponse)
async def parse_tender_documents(id_pncp: str) -> ParseResponse:
    """Converte PDFs em Markdown segmentado (Docling ou fallback)."""
    service = ParserService()
    try:
        docs = service.parse_tender(id_pncp, persist=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not docs:
        raise HTTPException(
            status_code=404,
            detail="Nenhum PDF/DOCX encontrado em data/raw. Baixe anexos antes (POST .../documents).",
        )
    return ParseResponse(
        id_pncp=id_pncp,
        documents=[
            {
                "file": str(doc.source_path),
                "engine": doc.engine,
                "sections": list(doc.sections.keys()),
                "refs_count": len(doc.refs),
                "markdown_chars": len(doc.markdown),
            }
            for doc in docs
        ],
    )


@app.post("/agents/{id_pncp:path}/extract")
async def extract_tender(id_pncp: str) -> dict[str, Any]:
    """Pipeline: parse + TenderSchema + checklist + triagem Lei 14.133 (com RAG)."""
    pipeline = TenderPipeline(use_rag=True)
    try:
        return await pipeline.run(id_pncp)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/rag/index/lei-14133")
async def index_lei_14133() -> dict[str, Any]:
    """Indexa corpus Lei 14.133 + seed TCU (pgvector/JSONB ou memória)."""
    store = get_legal_store()
    count = await store.index_corpus()
    return {
        "indexed": count,
        "backend": store.embedder.backend,
        "sources": ["lei_14133", "tcu"],
        "marco_legal": "Lei Federal nº 14.133/2021",
    }


@app.get("/rag/search")
async def rag_search(q: str, top_k: int = 5) -> dict[str, Any]:
    await ensure_legal_index()
    hits = await retrieve_legal_context(q, top_k=top_k)
    return {
        "query": q,
        "results": [
            {
                "chunk_id": h.chunk_id,
                "source": h.source,
                "titulo": h.titulo,
                "fundamentacao": h.fundamentacao,
                "score": h.score,
                "texto": h.texto[:500],
            }
            for h in hits
        ],
    }


@app.post("/agents/{id_pncp:path}/graph")
async def run_graph(id_pncp: str) -> dict[str, Any]:
    """LangGraph: ingestion → parser → extractor → legal_analyzer → matcher."""
    try:
        from src.agents.graph import run_tender_graph

        return await run_tender_graph(id_pncp)
    except ModuleNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Dependência ausente para o grafo: {exc}. Instale requirements.txt (langgraph).",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class MatchRequest(BaseModel):
    """Busca direta quando o tender já foi extraído (ou payload PNCP enriquecido)."""

    tender: dict[str, Any]
    limit: int = Field(default=30, ge=1, le=100)
    min_score: float = Field(default=40.0, ge=0, le=100)
    require_proximity: bool = False


@app.post("/matching/search")
async def matching_search(body: MatchRequest) -> dict[str, Any]:
    service = MatchmakingService()
    try:
        result = await service.match_tender(
            body.tender,
            limit=body.limit,
            min_score=body.min_score,
            require_proximity=body.require_proximity,
        )
        return result.model_dump(mode="json")
    finally:
        await service.aclose()


@app.post("/matching/{id_pncp:path}")
async def matching_for_tender(
    id_pncp: str,
    require_proximity: bool = False,
    limit: int = 30,
) -> dict[str, Any]:
    """Extrai o edital (pipeline) e cruza com empresas ATIVAS na Minha Receita."""
    pipeline = TenderPipeline(use_rag=False)
    try:
        extracted = await pipeline.run(id_pncp, fetch_pncp_itens=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    tender = (extracted.get("extraction") or {}).get("tender") or {}
    tender["id_pncp"] = id_pncp
    service = MatchmakingService()
    try:
        result = await service.match_tender(
            tender,
            limit=limit,
            require_proximity=require_proximity,
        )
        payload = result.model_dump(mode="json")
        payload["extraction_sections"] = extracted.get("extraction", {}).get("sections_found")
        return payload
    finally:
        await service.aclose()


class AdvisoryRequest(BaseModel):
    tender: dict[str, Any] | None = None
    company: CompanyContext | None = None
    perguntas_esclarecimento: list[str] | None = None
    persist: bool = True


@app.post("/advisory/generate")
async def advisory_generate(body: AdvisoryRequest) -> dict[str, Any]:
    """Gera kit de minutas (proposta, esclarecimento, impugnação, declarações) com disclaimer OAB."""
    if not body.tender:
        raise HTTPException(status_code=422, detail="Campo tender é obrigatório.")
    kit = build_document_kit(
        body.tender,
        body.company,
        perguntas_esclarecimento=body.perguntas_esclarecimento,
    )
    saved: list[str] = []
    if body.persist:
        try:
            saved = persist_kit(kit)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**kit.model_dump(mode="json"), "saved_files": saved}


class KitFromTenderRequest(BaseModel):
    company: CompanyContext | None = None
    persist: bool = True


@app.post("/advisory/{id_pncp:path}/kit")
async def advisory_kit_for_tender(
    id_pncp: str,
    body: KitFromTenderRequest | None = None,
) -> dict[str, Any]:
    """Extrai edital e gera o kit de participação (minutas Lei 14.133 + disclaimer)."""
    body = body or KitFromTenderRequest()
    pipeline = TenderPipeline(use_rag=True)
    try:
        extracted = await pipeline.run(id_pncp)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    tender = (extracted.get("extraction") or {}).get("tender") or {}
    tender["id_pncp"] = id_pncp
    kit = build_document_kit(tender, body.company)
    saved: list[str] = []
    if body.persist:
        saved = persist_kit(kit)
    return {
        **kit.model_dump(mode="json"),
        "saved_files": saved,
        "riscos_count": len(tender.get("riscos_juridicos") or []),
    }


@app.post("/outreach/whatsapp/opportunity")
async def outreach_whatsapp(body: OutreachPayload) -> dict[str, Any]:
    """Dispara alerta WhatsApp via Evolution API (instância configurada)."""
    service = OutreachService()
    try:
        return await service.notify_opportunity(body)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao enviar via Evolution API: {exc}",
        ) from exc
    finally:
        await service.aclose()


@app.post("/outreach/whatsapp/preview")
async def outreach_preview(body: OutreachPayload) -> dict[str, Any]:
    """Monta a mensagem sem enviar (útil para validação)."""
    service = OutreachService()
    try:
        text = service.build_message(body)
        return {"preview": text, "chars": len(text)}
    finally:
        await service.aclose()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("src.main:app", host=settings.licitall_host, port=settings.licitall_port, reload=True)
