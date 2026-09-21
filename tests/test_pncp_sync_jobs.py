"""Testes do job async de sync PNCP (retry por página + progresso)."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.ingestion.jobs import SyncJob, _fetch_page_with_retry, create_sync_job, execute_sync_job, get_job
from src.models.enums import ModalityEnum


@pytest.mark.asyncio
async def test_fetch_page_retries_timeout_then_ok():
    client = MagicMock()
    client.list_publicacoes = AsyncMock(
        side_effect=[
            httpx.ReadTimeout("slow"),
            {"data": [{"numeroControlePNCP": "x"}], "totalPaginas": 1},
        ]
    )
    with patch("src.ingestion.jobs.asyncio.sleep", new_callable=AsyncMock):
        payload = await _fetch_page_with_retry(
            client,
            data_inicial=date(2026, 9, 20),
            data_final=date(2026, 9, 21),
            modalidade=ModalityEnum.PREGAO_ELETRONICO,
            uf="SP",
            pagina=1,
            max_attempts=3,
        )
    assert payload["totalPaginas"] == 1
    assert client.list_publicacoes.await_count == 2


@pytest.mark.asyncio
async def test_create_and_get_job_memory():
    job = await create_sync_job(
        uf="BR",
        data_inicial=date(2026, 9, 20),
        data_final=date(2026, 9, 21),
    )
    assert job.status == "queued"
    assert job.uf == "BR"
    assert job.ufs_total == 27
    loaded = await get_job(job.id)
    assert loaded is not None
    assert loaded.id == job.id


def test_resolve_ufs_brasil():
    from src.ingestion.jobs import resolve_ufs

    assert len(resolve_ufs("BR")) == 27
    assert resolve_ufs("sp") == ["SP"]


@pytest.mark.asyncio
async def test_execute_sync_job_partial_on_modality_failure():
    job = await create_sync_job(
        uf="SP",
        data_inicial=date(2026, 9, 20),
        data_final=date(2026, 9, 21),
        modalidades=[ModalityEnum.PREGAO_ELETRONICO],
    )

    async def boom(*_a, **_k):
        raise httpx.ReadTimeout("still down")

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.commit = AsyncMock()
    factory = MagicMock(return_value=session)

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("src.ingestion.jobs.get_session_factory", return_value=factory),
        patch("src.ingestion.jobs.PncpClient", return_value=client),
        patch("src.ingestion.jobs._fetch_page_with_retry", side_effect=boom),
        patch("src.ingestion.jobs.asyncio.sleep", new_callable=AsyncMock),
    ):
        await execute_sync_job(job.id)

    done = await get_job(job.id)
    assert done is not None
    assert done.status == "failed"
    assert done.ingested == 0
    assert done.error
