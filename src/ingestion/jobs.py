"""Jobs assíncronos de sync PNCP com progresso e retry por página."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Awaitable

import httpx

from src.config import get_settings
from src.db import get_session_factory
from src.ingestion.client import PncpClient, PncpError
from src.ingestion.service import is_open_for_proposals, map_pncp_item, upsert_tender
from src.models.enums import DEFAULT_INGESTION_MODALITIES, ModalityEnum

logger = logging.getLogger("licitall.ingestion.jobs")

ProgressCb = Callable[[dict[str, Any]], Awaitable[None]] | None

# Sync nacional: uma UF por vez (API PNCP sem UF estoura timeout).
BRASIL_UFS: tuple[str, ...] = (
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA",
    "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
    "RO", "RR", "RS", "SC", "SE", "SP", "TO",
)

_JOB_TTL_SECONDS = 60 * 60 * 24
_REDIS_PREFIX = "licitall:pncp_sync:"
_memory_jobs: dict[str, "SyncJob"] = {}
_running_tasks: dict[str, asyncio.Task[None]] = {}


@dataclass
class SyncJob:
    id: str
    status: str  # queued | running | succeeded | partial | failed
    uf: str  # "BR" = todas as UFs; senão sigla
    data_inicial: str
    data_final: str
    only_open: bool = True
    modalidades: list[str] = field(default_factory=list)
    ingested: int = 0
    pages_done: int = 0
    pages_estimated: int = 0
    ufs_done: int = 0
    ufs_total: int = 0
    current_uf: str | None = None
    attempts: int = 0
    error: str | None = None
    message: str = "Na fila"
    log: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_ufs(uf: str | None) -> list[str]:
    """BR / ALL / vazio → todas as UFs; senão uma UF."""
    raw = (uf or "BR").strip().upper()
    if raw in {"BR", "ALL", "*", "BRASIL", "NACIONAL"}:
        return list(BRASIL_UFS)
    if len(raw) != 2:
        raise ValueError(f"UF inválida: {uf!r}. Use sigla (SP) ou BR para Brasil.")
    return [raw]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_log(job: SyncJob, line: str, *, keep: int = 40) -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    job.log.append(f"[{stamp}] {line}")
    if len(job.log) > keep:
        job.log = job.log[-keep:]
    job.updated_at = _now()


async def _redis():
    settings = get_settings()
    try:
        import redis.asyncio as redis

        client = redis.from_url(settings.redis_url, decode_responses=True)
        await client.ping()
        return client
    except Exception:
        return None


async def save_job(job: SyncJob) -> None:
    job.updated_at = _now()
    _memory_jobs[job.id] = job
    client = await _redis()
    if client is None:
        return
    try:
        await client.set(_REDIS_PREFIX + job.id, json.dumps(job.to_dict()), ex=_JOB_TTL_SECONDS)
    except Exception as exc:
        logger.warning("Falha ao persistir job no Redis: %s", exc)
    finally:
        await client.aclose()


async def get_job(job_id: str) -> SyncJob | None:
    client = await _redis()
    if client is not None:
        try:
            raw = await client.get(_REDIS_PREFIX + job_id)
            if raw:
                data = json.loads(raw)
                return SyncJob(**data)
        except Exception as exc:
            logger.warning("Falha ao ler job no Redis: %s", exc)
        finally:
            await client.aclose()
    return _memory_jobs.get(job_id)


async def create_sync_job(
    *,
    uf: str | None = "BR",
    data_inicial: date,
    data_final: date,
    only_open: bool = True,
    modalidades: list[ModalityEnum] | None = None,
) -> SyncJob:
    mods = modalidades or list(DEFAULT_INGESTION_MODALITIES)
    ufs = resolve_ufs(uf)
    scope = "BR" if len(ufs) > 1 else ufs[0]
    job = SyncJob(
        id=str(uuid.uuid4()),
        status="queued",
        uf=scope,
        data_inicial=data_inicial.isoformat(),
        data_final=data_final.isoformat(),
        only_open=only_open,
        modalidades=[m.value if isinstance(m, ModalityEnum) else str(m) for m in mods],
        ufs_total=len(ufs),
        message=f"Job enfileirado · {'Brasil (' + str(len(ufs)) + ' UFs)' if scope == 'BR' else scope}",
    )
    _append_log(
        job,
        f"Criado sync {scope} {job.data_inicial}→{job.data_final} ({len(ufs)} UF(s))",
    )
    await save_job(job)
    return job


async def _fetch_page_with_retry(
    client: PncpClient,
    *,
    data_inicial: date,
    data_final: date,
    modalidade: ModalityEnum,
    uf: str,
    pagina: int,
    max_attempts: int = 4,
    on_retry: Callable[[int, str, float], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Retry por página: timeout e 429 com backoff (não abandona o job inteiro numa falha)."""
    settings = get_settings()
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await client.list_publicacoes(
                data_inicial=data_inicial,
                data_final=data_final,
                modalidade=modalidade,
                uf=uf,
                pagina=pagina,
                tamanho_pagina=min(50, settings.pncp_page_size),
            )
        except httpx.TimeoutException as exc:
            last_exc = exc
            wait = min(2 ** attempt, 30)
            if on_retry:
                await on_retry(attempt, f"timeout p.{pagina}", wait)
            await asyncio.sleep(wait)
        except PncpError as exc:
            last_exc = exc
            text = str(exc)
            if "429" in text or "rate" in text.lower():
                wait = min(15 * attempt, 90)
                if on_retry:
                    await on_retry(attempt, "HTTP 429", wait)
                await asyncio.sleep(wait)
                continue
            if "50" in text[:20]:  # 500/502/503
                wait = min(2 ** attempt, 20)
                if on_retry:
                    await on_retry(attempt, "HTTP 5xx", wait)
                await asyncio.sleep(wait)
                continue
            raise
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if exc.response is not None and exc.response.status_code == 429:
                retry_after = exc.response.headers.get("Retry-After")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else min(20 * attempt, 120)
                if on_retry:
                    await on_retry(attempt, "HTTP 429", wait)
                await asyncio.sleep(wait)
                continue
            if exc.response is not None and exc.response.status_code >= 500:
                wait = min(2 ** attempt, 20)
                if on_retry:
                    await on_retry(attempt, f"HTTP {exc.response.status_code}", wait)
                await asyncio.sleep(wait)
                continue
            raise
        except httpx.TransportError as exc:
            last_exc = exc
            wait = min(2 ** attempt, 20)
            if on_retry:
                await on_retry(attempt, "transporte", wait)
            await asyncio.sleep(wait)
    assert last_exc is not None
    raise last_exc


async def execute_sync_job(job_id: str) -> None:
    job = await get_job(job_id)
    if not job:
        return
    job.status = "running"
    job.message = "Consultando PNCP…"
    job.attempts += 1
    _append_log(job, f"Início tentativa #{job.attempts}")
    await save_job(job)

    data_inicial = date.fromisoformat(job.data_inicial)
    data_final = date.fromisoformat(job.data_final)
    modalidades = [ModalityEnum(m) for m in job.modalidades]
    ufs = resolve_ufs(job.uf)
    job.ufs_total = len(ufs)
    errors: list[str] = []
    ingested = 0
    ufs_ok = 0

    factory = get_session_factory()
    try:
        async with PncpClient() as client:
            async with factory() as session:
                for uf_idx, uf in enumerate(ufs, start=1):
                    job.current_uf = uf
                    job.ufs_done = uf_idx - 1
                    uf_ingested_before = ingested
                    _append_log(job, f"UF {uf} ({uf_idx}/{len(ufs)})")
                    await save_job(job)
                    uf_had_error = False

                    for modalidade in modalidades:
                        job.message = (
                            f"Brasil {uf} ({uf_idx}/{len(ufs)}) · {modalidade.value} · "
                            f"{ingested} no banco"
                        )
                        await save_job(job)
                        pagina = 1
                        total_paginas = 1
                        try:
                            while pagina <= total_paginas:
                                async def _on_retry(attempt: int, reason: str, wait: float) -> None:
                                    job.message = (
                                        f"{uf}/{modalidade.value} p.{pagina} retry {attempt} "
                                        f"({reason}, {wait:.0f}s) · {ingested} no banco"
                                    )
                                    _append_log(job, job.message)
                                    await save_job(job)

                                payload = await _fetch_page_with_retry(
                                    client,
                                    data_inicial=data_inicial,
                                    data_final=data_final,
                                    modalidade=modalidade,
                                    uf=uf,
                                    pagina=pagina,
                                    max_attempts=max(1, get_settings().pncp_page_retries),
                                    on_retry=_on_retry,
                                )
                                total_paginas = max(1, int(payload.get("totalPaginas") or 1))
                                # estimativa: páginas × modalidades × UFs restantes (grosseira)
                                job.pages_estimated = max(
                                    job.pages_estimated,
                                    total_paginas * len(modalidades) * len(ufs),
                                )
                                rows = payload.get("data") or []
                                page_count = 0
                                for item in rows:
                                    if job.only_open and not is_open_for_proposals(item):
                                        continue
                                    await upsert_tender(session, map_pncp_item(item))
                                    page_count += 1
                                    ingested += 1
                                # Commit imediato → lista /tenders já reflete o progresso
                                await session.commit()
                                job.ingested = ingested
                                job.pages_done += 1
                                job.message = (
                                    f"{uf}/{modalidade.value} p.{pagina}/{total_paginas} · "
                                    f"{ingested} no banco"
                                )
                                if page_count:
                                    _append_log(
                                        job,
                                        f"{uf} {modalidade.value} p.{pagina}/{total_paginas} "
                                        f"(+{page_count})",
                                    )
                                await save_job(job)
                                if payload.get("empty") or pagina >= total_paginas:
                                    break
                                pagina += 1
                        except Exception as exc:
                            uf_had_error = True
                            msg = f"{uf}/{modalidade.value}: {type(exc).__name__}: {exc}"
                            errors.append(msg)
                            _append_log(job, f"ERRO {msg}")
                            await save_job(job)
                            logger.warning("Sync job %s falhou em %s: %s", job_id, uf, msg)
                            continue

                    job.ufs_done = uf_idx
                    if not uf_had_error or ingested > uf_ingested_before:
                        ufs_ok += 1
                    job.message = (
                        f"UF {uf} ok · {ingested} editais no banco "
                        f"({uf_idx}/{len(ufs)} UFs)"
                    )
                    await save_job(job)

        job.ingested = ingested
        job.current_uf = None
        if errors and ingested == 0:
            job.status = "failed"
            job.error = "; ".join(errors)[:800]
            job.message = "Falhou — PNCP sem dados úteis"
        elif errors:
            job.status = "partial"
            job.error = "; ".join(errors)[:800]
            job.message = (
                f"Parcial Brasil · {ingested} ingeridos · "
                f"{ufs_ok}/{len(ufs)} UFs com dados · algumas falhas"
            )
        else:
            job.status = "succeeded"
            job.error = None
            job.message = f"Concluído Brasil · {ingested} editais · {len(ufs)} UFs"
        _append_log(job, job.message)
        await save_job(job)
    except Exception as exc:
        job.status = "failed"
        job.error = f"{type(exc).__name__}: {exc}"
        job.message = "Falhou"
        _append_log(job, job.error)
        await save_job(job)
        logger.exception("Sync job %s falhou", job_id)
    finally:
        _running_tasks.pop(job_id, None)


def enqueue_sync_job(job_id: str) -> None:
    """Agenda execução em background no event loop atual."""
    if job_id in _running_tasks and not _running_tasks[job_id].done():
        return
    task = asyncio.create_task(execute_sync_job(job_id), name=f"pncp-sync-{job_id}")
    _running_tasks[job_id] = task


def default_date_window() -> tuple[date, date]:
    today = date.today()
    return today - timedelta(days=1), today
