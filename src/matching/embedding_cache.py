"""Vetores com cache no banco (`embeddings_cache`): o mesmo texto nunca vai duas vezes ao provedor."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.matching.semantic import BATCH_SIZE, CacheResolution, content_hash, resolve_vectors
from src.models.tables import EmbeddingCacheRow


async def vectors_with_cache(
    session: AsyncSession, embedder: Any, texts: list[str], *, parcial: bool = False, batch_size: int = BATCH_SIZE
) -> CacheResolution:
    """Lê do cache o que já existe e pede ao provedor só os inéditos, em lotes, gravando cada lote assim que chega.

    Assim uma falha no meio (ex.: cota esgotada) não perde o que já foi calculado: a próxima execução continua de onde
    parou. Com `parcial`, a falha fica em `resolution.erro` em vez de subir.
    """
    hashes = {content_hash(t) for t in texts if t}
    backend = embedder.cache_key
    cached_rows = []
    if hashes:
        cached_rows = (
            await session.exec(
                select(EmbeddingCacheRow).where(
                    EmbeddingCacheRow.backend == backend,
                    EmbeddingCacheRow.content_hash.in_(hashes),
                )
            )
        ).all()
    cached = {r.content_hash: r.embedding for r in cached_rows}

    async def gravar(lote: dict[str, tuple[str, list[float]]]) -> None:
        for h, (text, vec) in lote.items():
            await session.execute(
                pg_insert(EmbeddingCacheRow)
                .values(content_hash=h, backend=backend, texto_base=text, embedding=vec, created_at=datetime.now(timezone.utc))
                .on_conflict_do_nothing()
            )
        await session.commit()

    return await resolve_vectors(
        [t for t in texts if t], cached, embedder, batch_size=batch_size, on_batch=gravar, parcial=parcial
    )
