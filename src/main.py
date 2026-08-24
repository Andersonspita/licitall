from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from src import __version__
from src.config import get_settings
from src.db import get_session, init_db
from src.ingestion.client import PncpClient, PncpError
from src.ingestion.service import download_tender_documents, ingest_publicacoes
from src.ingestion.storage import DocumentStorage
from src.models.enums import DEFAULT_INGESTION_MODALITIES, ModalityEnum

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
    description="Plataforma B2G de ingestão e assessoria pré-certame (Lei 14.133/2021).",
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


@app.get("/health")
async def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "raw_docs_dir": str(settings.raw_docs_path),
        "minha_receita": settings.minha_receita_base_url,
        "evolution_api": settings.evolution_api_url,
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


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("src.main:app", host=settings.licitall_host, port=settings.licitall_port, reload=True)
