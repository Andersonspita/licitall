"""Vetores com cache no banco (`embeddings_cache`): o mesmo texto nunca vai duas vezes ao provedor."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.matching.semantic import CacheResolution, content_hash, resolve_vectors
from src.models.tables import EmbeddingCacheRow


async def vectors_with_cache(session: AsyncSession, embedder: Any, texts: list[str]) -> CacheResolution:
    """Lê do cache o que já existe, pede ao provedor só os inéditos (em lotes) e grava os novos. Faz commit."""
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
    resolution = await resolve_vectors([t for t in texts if t], cached, embedder)
    for h, (text, vec) in resolution.new_entries.items():
        await session.execute(
            pg_insert(EmbeddingCacheRow)
            .values(content_hash=h, backend=backend, texto_base=text, embedding=vec, created_at=datetime.now(timezone.utc))
            .on_conflict_do_nothing()
        )
    await session.commit()
    return resolution
