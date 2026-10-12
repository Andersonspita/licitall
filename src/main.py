from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
import httpx

from pathlib import Path
from src import __version__
from src.agents.pipeline import TenderPipeline
from src.auth.deps import current_user, guard
from src.config.production import assert_production_ready
from src.habilitacao.routes import atestados_router, certidoes_router
from src.auth.routes import router as auth_router
from src.config import get_settings
from src.db import get_session, get_session_factory, init_db
from src.ingestion.client import PncpClient, PncpError
from src.ingestion.service import (
    download_tender_documents,
    hydrate_attachments,
    hydrate_items,
    ingest_publicacoes,
)
from src.ingestion.jobs import (
    create_sync_job,
    default_date_window,
    enqueue_sync_job,
    get_job,
)
from src.ingestion.storage import DocumentStorage
from src.models.enums import DEFAULT_INGESTION_MODALITIES, ModalityEnum
from src.matching.service import MatchmakingService
from src.matching import profiles as profile_svc
from src.matching.digest import build_digest_text, evolution_sender, group_matches, load_new_matches
from src.matching.digest import send_digest as send_digest_core
from src.matching.digest import mark_sent as mark_matches_sent
from src.matching.scheduler import BRT, next_run, passed_today, normalize_phone, parse_horario, run_due_digests, scheduler_loop
from src.matching.feedback import add_keyword, apply_feedback
from src.matching.opportunities import MATCH_STATUSES, list_opportunities
from src.matching.reverse import run_reverse_match
from src.models.tables import (
    DigestSchedule,
    InterestProfile,
    MatchItem,
    TenderAttachment,
    TenderIngest,
    Usuario,
)
from src.rag.embeddings import EmbeddingError, EmbeddingProvider
from src.advisory import CompanyContext, build_document_kit, persist_kit
from src.outreach import DigestItem, DigestPayload, OutreachPayload, OutreachService
from src.parser.service import ParserService
from src.infra.health import check_dependencies
from src.pipeline.orchestrator import run_full_pipeline
from src.rag.corpus import load_legal_corpus
from src.rag.retriever import ensure_legal_index, get_legal_store, retrieve_legal_context
from src.tenders import get_tender, list_tenders, tender_stats

logger = logging.getLogger("licitall")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    assert_production_ready(get_settings())
    try:
        await init_db()
    except Exception as exc:
        logger.warning("PostgreSQL indisponível na inicialização: %s", exc)
    settings = get_settings()
    task = None
    if settings.digest_scheduler_enabled:
        task = asyncio.create_task(
            scheduler_loop(get_session_factory(), evolution_sender, settings.digest_scheduler_interval_seconds),
            name="digest-scheduler",
        )
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title="LicitAll",
    description=(
        "Plataforma B2G de ingestão e assessoria pré-certame. "
        "Marco legal: Lei Federal nº 14.133/2021 (nova lei de licitações) e LC 123/2006."
    ),
    version=__version__,
    lifespan=lifespan,
    # Toda rota exige login, salvo as públicas listadas em src/auth/security.py.
    dependencies=[Depends(guard)],
    # A documentação interativa lista todas as rotas: só no modo de desenvolvimento (DEBUG=true).
    docs_url="/docs" if get_settings().debug else None,
    redoc_url=None,
    openapi_url="/openapi.json" if get_settings().debug else None,
)
app.include_router(auth_router)
app.include_router(certidoes_router)
app.include_router(atestados_router)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.url.path.startswith("/auth"):
        response.headers["Cache-Control"] = "no-store"
    return response

_UI_DIR = Path(__file__).resolve().parents[1] / "app" / "web"
if _UI_DIR.is_dir():
    app.mount("/ui", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")


@app.get("/")
async def root_redirect() -> RedirectResponse:
    """UI operacional em /ui (login → dashboard)."""
    return RedirectResponse(url="/ui/login.html", status_code=307)


@app.get("/app")
async def app_alias() -> RedirectResponse:
    return RedirectResponse(url="/ui/", status_code=307)


class IngestRequest(BaseModel):
    data_inicial: date | None = None
    data_final: date | None = None
    uf: str | None = Field(default=None, min_length=2, max_length=2)
    only_open: bool = True
    modalidades: list[ModalityEnum] = Field(default_factory=lambda: list(DEFAULT_INGESTION_MODALITIES))


class IngestAsyncRequest(BaseModel):
    """Sync assíncrono. uf=BR (padrão) varre todas as UFs; commit página a página."""

    data_inicial: date | None = None
    data_final: date | None = None
    uf: str | None = Field(
        default="BR",
        min_length=2,
        max_length=8,
        description="BR = Brasil (todas UFs) ou sigla (SP, RJ…)",
    )
    only_open: bool = True
    modalidades: list[ModalityEnum] = Field(default_factory=lambda: list(DEFAULT_INGESTION_MODALITIES))


class IngestResponse(BaseModel):
    ingested: int
    uf: str | None
    data_inicial: date
    data_final: date


class IngestJobResponse(BaseModel):
    job_id: str
    status: str
    message: str
    poll_url: str


class DownloadResponse(BaseModel):
    id_pncp: str
    files: list[str]


class ParseResponse(BaseModel):
    id_pncp: str
    documents: list[dict[str, Any]]


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "version": __version__}


@app.get("/health/detail")
async def health_detail() -> dict[str, Any]:
    settings = get_settings()
    parser = ParserService().parser
    return {
        "status": "ok",
        "version": __version__,
        "marco_legal": "Lei Federal nº 14.133/2021",
        "docling_available": parser.docling_available,
        "legal_chunks": len(load_legal_corpus()),
        "raw_docs_dir": str(settings.raw_docs_path),
        "minha_receita": settings.minha_receita_base_url,
        "evolution_api": settings.evolution_api_url,
        "evolution_instance": settings.evolution_instance,
    }


@app.get("/health/deps")
async def health_deps() -> dict[str, Any]:
    """Ping Postgres, Redis, Minha Receita e Evolution API."""
    return await check_dependencies()


@app.get("/tenders/stats")
async def tenders_stats(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """KPIs do dashboard a partir de `tender_ingest` (dados reais)."""
    try:
        return await tender_stats(session)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Postgres indisponível: {exc}") from exc


@app.get("/tenders")
async def tenders_list(
    uf: str | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Lista editais ingeridos do PNCP com filtros (uf, status, busca textual)."""
    try:
        return await list_tenders(
            session, uf=uf, status=status, q=q, limit=limit, offset=offset
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Postgres indisponível: {exc}") from exc


@app.get("/tenders/{id_pncp:path}")
async def tenders_detail(
    id_pncp: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Detalhe de um edital + hints de arquivos em data/raw."""
    try:
        row = await get_tender(session, id_pncp)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(status_code=503, detail=f"Banco ou disco indisponível: {exc}") from exc
    if not row:
        raise HTTPException(status_code=404, detail=f"Edital não encontrado: {id_pncp}")
    return row


class PipelineRunRequest(BaseModel):
    company: CompanyContext | None = None
    download_if_missing: bool = True
    persist_kit: bool = True
    run_matching: bool = True
    whatsapp_phone: str | None = None
    send_whatsapp: bool = False


@app.post("/pipeline/{id_pncp:path}/run")
async def pipeline_run(id_pncp: str, body: PipelineRunRequest | None = None) -> dict[str, Any]:
    """Orquestra download → parse/extract → match → kit → preview WhatsApp."""
    body = body or PipelineRunRequest()
    try:
        result = await run_full_pipeline(
            id_pncp,
            company=body.company,
            download_if_missing=body.download_if_missing,
            save_kit=body.persist_kit,
            run_matching=body.run_matching,
            whatsapp_phone=body.whatsapp_phone,
            send_whatsapp=body.send_whatsapp,
        )
        return result.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Pipeline falhou: {exc}") from exc


@app.post("/ingestion/pncp/sync", response_model=IngestResponse)
async def sync_pncp(
    body: IngestRequest,
    session: AsyncSession = Depends(get_session),
) -> IngestResponse:
    """Sync síncrono (legado, 1 UF). Prefira POST /ingestion/pncp/sync/async com uf=BR."""
    if not body.uf:
        raise HTTPException(
            status_code=422,
            detail="No sync síncrono informe uf (ex.: SP). Para Brasil use POST /ingestion/pncp/sync/async com uf=BR.",
        )
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
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail=(
                "PNCP não respondeu a tempo (timeout). Use POST /ingestion/pncp/sync/async "
                "(retry por página + progresso)."
            ),
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Falha de rede no PNCP: {exc}") from exc
    return IngestResponse(
        ingested=ingested,
        uf=body.uf,
        data_inicial=data_inicial,
        data_final=data_final,
    )


@app.post("/ingestion/pncp/sync/async", response_model=IngestJobResponse)
async def sync_pncp_async(body: IngestAsyncRequest) -> IngestJobResponse:
    """Enfileira sync PNCP (Brasil=UF a UF). Commit por página → lista cresce ao vivo."""
    data_inicial, data_final = default_date_window()
    if body.data_final:
        data_final = body.data_final
    if body.data_inicial:
        data_inicial = body.data_inicial
    else:
        data_inicial = data_final - timedelta(days=1)
    if data_inicial > data_final:
        raise HTTPException(status_code=422, detail="data_inicial não pode ser posterior a data_final.")
    if (data_final - data_inicial).days > 7:
        raise HTTPException(
            status_code=422,
            detail="Janela máxima de 7 dias no sync async (reduz timeout no PNCP).",
        )
    try:
        job = await create_sync_job(
            uf=body.uf or "BR",
            data_inicial=data_inicial,
            data_final=data_final,
            only_open=body.only_open,
            modalidades=body.modalidades,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    enqueue_sync_job(job.id)
    return IngestJobResponse(
        job_id=job.id,
        status=job.status,
        message=job.message,
        poll_url=f"/ingestion/pncp/sync/jobs/{job.id}",
    )


@app.get("/ingestion/pncp/sync/jobs/{job_id}")
async def sync_pncp_job_status(job_id: str) -> dict[str, Any]:
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job não encontrado: {job_id}")
    return job.to_dict()


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


@app.post("/ingestion/pncp/{id_pncp:path}/itens/hydrate")
async def hydrate_tender_items(
    id_pncp: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Busca os itens no PNCP e grava em itens_contratacao (UPSERT idempotente)."""
    try:
        async with PncpClient() as client:
            count = await hydrate_items(session, client, id_pncp)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PncpError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"id_pncp": id_pncp, "itens_gravados": count}


@app.post("/ingestion/pncp/{id_pncp:path}/anexos/hydrate")
async def hydrate_tender_attachments(
    id_pncp: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Busca no PNCP os links dos arquivos do edital e grava em anexos_contratacao (idempotente)."""
    try:
        async with PncpClient() as client:
            count = await hydrate_attachments(session, client, id_pncp)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PncpError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"id_pncp": id_pncp, "anexos_gravados": count}


@app.get("/ingestion/pncp/{id_pncp:path}/anexos")
async def list_tender_attachments(
    id_pncp: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Lista os anexos já gravados (sem consultar o PNCP)."""
    rows = (
        await session.exec(
            select(TenderAttachment).where(TenderAttachment.id_pncp == id_pncp).order_by(TenderAttachment.id)
        )
    ).all()
    return {
        "id_pncp": id_pncp,
        "anexos": [{"titulo": a.titulo, "tipo": a.tipo_documento, "url": a.url_download} for a in rows],
    }


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


class CompanyMatchRequest(BaseModel):
    """Match inverso: CNPJ → oportunidades (lista inline ou tender_ingest)."""

    cnpj: str
    tenders: list[dict[str, Any]] | None = None
    limit: int = Field(default=20, ge=1, le=100)
    min_score: float = Field(default=40.0, ge=0, le=100)
    require_proximity: bool = False
    uf: str | None = None
    company: dict[str, Any] | None = None


class DigestFromCompanyRequest(BaseModel):
    """Monta (e opcionalmente envia) digest WhatsApp a partir do match inverso."""

    phone: str
    cnpj: str
    tenders: list[dict[str, Any]] | None = None
    top_n: int = Field(default=5, ge=1, le=15)
    min_score: float = Field(default=40.0, ge=0, le=100)
    require_proximity: bool = False
    uf: str | None = None
    company: dict[str, Any] | None = None
    send: bool = False
    instance: str | None = None


async def owned_profile(session: AsyncSession, user: Usuario, profile_id: uuid.UUID) -> InterestProfile:
    """Perfil da empresa do usuário. De outra empresa responde 404 (não revela que existe)."""
    profile = await profile_svc.get_profile(session, profile_id)
    if profile is None or profile.empresa_id != str(user.empresa_id):
        raise HTTPException(status_code=404, detail="Perfil não encontrado")
    return profile


class ProfileCreateRequest(BaseModel):
    empresa_id: str | None = Field(default=None, description="Ignorado: vem da sessão.")
    nome_perfil: str = Field(min_length=1, max_length=100)
    ufs_permitidas: list[str] = Field(
        default_factory=list, description="Vazio = Brasil inteiro. Siglas de 2 letras."
    )
    valor_minimo_item: float = Field(default=0.0, ge=0)
    valor_maximo_item: float | None = Field(default=None, ge=0)
    apenas_me_epp: bool = False
    palavras_obrigatorias: list[str] = Field(default_factory=list)
    palavras_positivas: list[str] = Field(default_factory=list)
    palavras_negativas: list[str] = Field(default_factory=list)
    codigos_catalogo: list[int] = Field(default_factory=list, description="CATMAT/CATSER")
    descricao_sintetica: str | None = Field(
        default=None, description="Texto livre do que o cliente fornece (vira o vetor semântico do perfil)"
    )


class ProfileFilterRequest(BaseModel):
    id_pncp: str


@app.post("/matching/profiles", status_code=201)
async def create_interest_profile(
    body: ProfileCreateRequest,
    session: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> dict[str, Any]:
    if any(len(u.strip()) != 2 for u in body.ufs_permitidas):
        raise HTTPException(status_code=422, detail="ufs_permitidas deve conter siglas de 2 letras")
    if body.valor_maximo_item is not None and body.valor_maximo_item < body.valor_minimo_item:
        raise HTTPException(status_code=422, detail="valor_maximo_item menor que valor_minimo_item")
    profile = await profile_svc.create_profile(
        session,
        empresa_id=str(user.empresa_id),
        nome_perfil=body.nome_perfil,
        ufs_permitidas=[u.strip() for u in body.ufs_permitidas],
        valor_minimo_item=body.valor_minimo_item,
        valor_maximo_item=body.valor_maximo_item,
        apenas_me_epp=body.apenas_me_epp,
        palavras={
            "OBRIGATORIA": body.palavras_obrigatorias,
            "POSITIVA": body.palavras_positivas,
            "NEGATIVA": body.palavras_negativas,
        },
        codigos_catalogo=body.codigos_catalogo,
        descricao_sintetica=body.descricao_sintetica,
    )
    return await profile_svc.load_profile_view(session, profile)


@app.get("/matching/profiles")
async def list_interest_profiles(
    session: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> dict[str, Any]:
    items = [
        await profile_svc.load_profile_view(session, p)
        for p in await profile_svc.list_profiles(session, str(user.empresa_id))
    ]
    return {"perfis": items}


@app.delete("/matching/profiles/{profile_id}", status_code=204, response_class=Response)
async def delete_interest_profile(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> Response:
    profile = await owned_profile(session, user, profile_id)
    await profile_svc.delete_profile(session, profile)
    return Response(status_code=204)


@app.post("/matching/profiles/{profile_id}/filter")
async def filter_items_by_profile(
    profile_id: uuid.UUID,
    body: ProfileFilterRequest,
    session: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> dict[str, Any]:
    """Camada 1 (filtros rígidos): separa itens aprovados e descartados (com motivo)."""
    profile = await owned_profile(session, user, profile_id)
    result = await profile_svc.apply_hard_filters(session, profile, body.id_pncp)
    if result is None:
        raise HTTPException(status_code=404, detail="Contratação não encontrada em tender_ingest")
    if result["itens_total"] == 0:
        raise HTTPException(
            status_code=409,
            detail="Contratação sem itens gravados; chame POST /ingestion/pncp/{id}/itens/hydrate",
        )
    return result


@app.post("/matching/profiles/{profile_id}/candidates")
async def candidates_by_profile(
    profile_id: uuid.UUID,
    body: ProfileFilterRequest,
    session: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> dict[str, Any]:
    """Camadas 1+2: filtros rígidos e pontuação CATMAT/léxica (parcial, máx. 75). Camada 3 pendente."""
    profile = await owned_profile(session, user, profile_id)
    result = await profile_svc.match_candidates(session, profile, body.id_pncp)
    if result is None:
        raise HTTPException(status_code=404, detail="Contratação não encontrada em tender_ingest")
    if result["itens_total"] == 0:
        raise HTTPException(
            status_code=409,
            detail="Contratação sem itens gravados; chame POST /ingestion/pncp/{id}/itens/hydrate",
        )
    return result


@app.post("/matching/profiles/{profile_id}/match")
async def match_by_profile(
    profile_id: uuid.UUID,
    body: ProfileFilterRequest,
    session: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> dict[str, Any]:
    """Funil completo (Camadas 1–3): score 0–100; `alerta` verdadeiro a partir de 65."""
    profile = await owned_profile(session, user, profile_id)
    embedder = EmbeddingProvider(dimensions=512, request_dimensions=True)
    try:
        result = await profile_svc.match_full(session, profile, body.id_pncp, embedder)
    except Exception as exc:
        if isinstance(exc, EmbeddingError) or exc.__class__.__module__.startswith("openai"):
            raise HTTPException(status_code=502, detail=f"Falha no provedor de embeddings: {exc}") from exc
        raise
    if result is None:
        raise HTTPException(status_code=404, detail="Contratação não encontrada em tender_ingest")
    if result["itens_total"] == 0:
        raise HTTPException(
            status_code=409,
            detail="Contratação sem itens gravados; chame POST /ingestion/pncp/{id}/itens/hydrate",
        )
    return result


class ReverseRunRequest(BaseModel):
    id_pncps: list[str] | None = Field(default=None, description="Editais a avaliar; vazio = os ingeridos nas últimas `since_hours`")
    since_hours: int = Field(default=24, ge=1, le=720)


class DigestSendRequest(BaseModel):
    phone: str = Field(..., description="Número com DDI, ex.: 5511999999999")
    top_n: int = Field(default=5, ge=1, le=15)
    instance: str | None = None


@app.post("/matching/reverse/run")
async def run_reverse(
    body: ReverseRunRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Busca reversa: avalia editais contra todos os perfis ativos e grava em matches_itens."""
    settings = get_settings()
    ids = body.id_pncps
    if not ids:
        since = datetime.now(timezone.utc) - timedelta(hours=body.since_hours)
        rows = await session.exec(select(TenderIngest.id_pncp).where(TenderIngest.created_at >= since))
        ids = list(rows.all())
    try:
        async with PncpClient() as client:
            return await run_reverse_match(
                session,
                id_pncps=ids,
                client=client,
                embedder=EmbeddingProvider(dimensions=512, request_dimensions=True),
                max_tenders=settings.reverse_match_max_tenders,
                delay=settings.reverse_match_delay_seconds,
            )
    except PncpError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class FeedbackRequest(BaseModel):
    relevante: bool


class KeywordRequest(BaseModel):
    tipo: str = Field(default="NEGATIVA", description="OBRIGATORIA, POSITIVA ou NEGATIVA")
    termo: str = Field(min_length=1, max_length=100)


@app.post("/matching/matches/{match_id}/feedback")
async def match_feedback(
    match_id: uuid.UUID,
    body: FeedbackRequest,
    session: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> dict[str, Any]:
    """Relevante → FAVORITO. Irrelevante → DESCARTADO e devolve termos sugeridos para a lista negativa."""
    match = await session.get(MatchItem, match_id)
    owner = await session.get(InterestProfile, match.perfil_id) if match else None
    if match is None or owner is None or owner.empresa_id != str(user.empresa_id):
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")
    return await apply_feedback(session, match, relevante=body.relevante)


@app.post("/matching/profiles/{profile_id}/palavras")
async def add_profile_keyword(
    profile_id: uuid.UUID,
    body: KeywordRequest,
    session: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> dict[str, Any]:
    """Acrescenta uma palavra ao perfil (padrão: negativa). Vale para os próximos matches."""
    profile = await owned_profile(session, user, profile_id)
    try:
        added = await add_keyword(session, profile, body.tipo.upper(), body.termo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"adicionada": added, "tipo": body.tipo.upper(), "termo": body.termo.strip()}


class ScheduleRequest(BaseModel):
    telefone: str = Field(..., description="Com DDI, ex.: 5571999999999")
    horario: str = Field(default="08:00", description="HH:MM, horário de Brasília")
    top_n: int = Field(default=5, ge=1, le=15)
    ativo: bool = True
    instance: str | None = None


def _schedule_view(sch: DigestSchedule | None) -> dict[str, Any]:
    if sch is None:
        return {"configurado": False}
    prox = next_run(sch.horario, datetime.now(timezone.utc), sch.ultimo_envio_dia)
    return {
        "configurado": True,
        "telefone": sch.telefone,
        "horario": sch.horario,
        "top_n": sch.top_n,
        "ativo": sch.ativo,
        "ultimo_envio_dia": sch.ultimo_envio_dia.isoformat() if sch.ultimo_envio_dia else None,
        "ultimo_status": sch.ultimo_status,
        "proxima_execucao": prox.isoformat() if sch.ativo else None,
    }


@app.put("/matching/profiles/{profile_id}/agendamento")
async def upsert_digest_schedule(
    profile_id: uuid.UUID,
    body: ScheduleRequest,
    session: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> dict[str, Any]:
    """Agenda o envio diário do digest por WhatsApp (horário de Brasília)."""
    profile = await owned_profile(session, user, profile_id)
    try:
        parse_horario(body.horario)
        phone = normalize_phone(body.telefone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    sch = await session.get(DigestSchedule, profile_id)
    now = datetime.now(timezone.utc)
    if sch is None or sch.horario != body.horario:
        # Novo horário: se o de hoje já passou, o primeiro envio é amanhã (sem mensagem imediata).
        today = now.astimezone(BRT).date()
        skip = passed_today(body.horario, now)
        if sch is None:
            sch = DigestSchedule(perfil_id=profile_id, telefone=phone, horario=body.horario)
        sch.ultimo_envio_dia = today if skip else None
    sch.telefone, sch.horario, sch.top_n = phone, body.horario, body.top_n
    sch.ativo, sch.instance = body.ativo, body.instance
    session.add(sch)
    await session.commit()
    await session.refresh(sch)
    return _schedule_view(sch)


@app.get("/matching/profiles/{profile_id}/agendamento")
async def get_digest_schedule(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> dict[str, Any]:
    await owned_profile(session, user, profile_id)
    return _schedule_view(await session.get(DigestSchedule, profile_id))


@app.delete("/matching/profiles/{profile_id}/agendamento", status_code=204, response_class=Response)
async def delete_digest_schedule(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> Response:
    await owned_profile(session, user, profile_id)
    sch = await session.get(DigestSchedule, profile_id)
    if sch is not None:
        await session.delete(sch)
        await session.commit()
    return Response(status_code=204)


@app.post("/matching/digest/run-due")
async def run_due_now() -> dict[str, Any]:
    """Executa agora os envios vencidos (o agendador já faz isso a cada minuto)."""
    results = await run_due_digests(get_session_factory(), sender=evolution_sender)
    return {"processados": len(results), "resultados": results}


@app.get("/matching/profiles/{profile_id}/oportunidades")
async def profile_opportunities(
    profile_id: uuid.UUID,
    pagina: int = 1,
    tamanho: int = 20,
    status: str | None = None,
    apenas_alerta: bool = False,
    desde: date | None = None,
    uf: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> dict[str, Any]:
    """Oportunidades gravadas do perfil, da maior para a menor nota (máx. 100 por página)."""
    profile = await owned_profile(session, user, profile_id)
    if status is not None and status not in MATCH_STATUSES:
        raise HTTPException(status_code=422, detail=f"status deve ser um de: {', '.join(MATCH_STATUSES)}")
    return await list_opportunities(
        session, profile, pagina=pagina, tamanho=tamanho, status=status,
        apenas_alerta=apenas_alerta, desde=desde, uf=uf,
    )


@app.get("/matching/profiles/{profile_id}/digest")
async def preview_profile_digest(
    profile_id: uuid.UUID,
    top_n: int = 5,
    session: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> dict[str, Any]:
    """Prévia do digest: matches NOVOS com alerta, agrupados por edital."""
    profile = await owned_profile(session, user, profile_id)
    groups = group_matches(await load_new_matches(session, profile))
    return {
        "perfil_id": str(profile.id),
        "editais": len(groups),
        "grupos": groups,
        "mensagem": build_digest_text(profile.nome_perfil, groups, top_n=max(1, min(top_n, 15))),
    }


@app.post("/matching/profiles/{profile_id}/digest/send")
async def send_profile_digest(
    profile_id: uuid.UUID,
    body: DigestSendRequest,
    session: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> dict[str, Any]:
    """Envia o digest por WhatsApp (Evolution) e só então marca os itens enviados como ENVIADO."""
    profile = await owned_profile(session, user, profile_id)
    try:
        return await send_digest_core(
            session, profile, phone=body.phone, top_n=body.top_n, instance=body.instance, sender=evolution_sender
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Falha no envio WhatsApp: {exc}") from exc


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


@app.post("/matching/company")
async def matching_for_company(
    body: CompanyMatchRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Match inverso: empresa ATIVA (CNPJ) → editais ranqueados com BID/REVIEW/SKIP."""
    service = MatchmakingService()
    try:
        result = await service.match_company(
            body.cnpj,
            tenders=body.tenders,
            session=None if body.tenders is not None else session,
            limit=body.limit,
            min_score=body.min_score,
            require_proximity=body.require_proximity,
            uf_filter=body.uf,
            company=body.company,
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


@app.post("/outreach/whatsapp/digest/preview")
async def outreach_digest_preview(body: DigestPayload) -> dict[str, Any]:
    """Monta digest top-N sem enviar."""
    service = OutreachService()
    try:
        text = service.build_digest_message(body)
        return {"preview": text, "chars": len(text), "items": min(len(body.opportunities), body.top_n)}
    finally:
        await service.aclose()


@app.post("/outreach/whatsapp/digest")
async def outreach_digest(body: DigestPayload) -> dict[str, Any]:
    """Envia digest WhatsApp (top-N oportunidades) via Evolution API."""
    service = OutreachService()
    try:
        return await service.notify_digest(body)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao enviar digest via Evolution API: {exc}",
        ) from exc
    finally:
        await service.aclose()


@app.post("/outreach/whatsapp/digest/from-company")
async def outreach_digest_from_company(
    body: DigestFromCompanyRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Match inverso + digest WhatsApp (preview ou envio)."""
    matcher = MatchmakingService()
    outreach = OutreachService()
    try:
        result = await matcher.match_company(
            body.cnpj,
            tenders=body.tenders,
            session=None if body.tenders is not None else session,
            limit=body.top_n,
            min_score=body.min_score,
            require_proximity=body.require_proximity,
            uf_filter=body.uf,
            company=body.company,
        )
        digest = DigestPayload(
            phone=body.phone,
            company_name=result.razao_social or body.cnpj,
            cnpj=result.cnpj,
            top_n=body.top_n,
            instance=body.instance,
            opportunities=[
                DigestItem(
                    id_pncp=op.id_pncp,
                    orgao=op.orgao_comprador,
                    objeto=op.objeto_resumido,
                    valor_total=op.valor_total_estimado,
                    score=op.score,
                    recommendation=op.recommendation,
                    uf=op.uf,
                )
                for op in result.opportunities
            ],
        )
        preview = outreach.build_digest_message(digest)
        payload: dict[str, Any] = {
            "matching": result.model_dump(mode="json"),
            "preview": preview,
            "chars": len(preview),
            "sent": False,
        }
        if body.send:
            sent = await outreach.notify_digest(digest)
            payload["sent"] = True
            payload["evolution"] = sent.get("evolution")
        return payload
    except Exception as exc:
        if body.send:
            raise HTTPException(
                status_code=502,
                detail=f"Falha no digest from-company: {exc}",
            ) from exc
        raise
    finally:
        await matcher.aclose()
        await outreach.aclose()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("src.main:app", host=settings.licitall_host, port=settings.licitall_port, reload=True)
