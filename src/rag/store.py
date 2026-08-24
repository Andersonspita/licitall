from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Column, Integer, String, Text, delete, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from src.db import get_engine, get_session_factory
from src.rag.corpus import LegalChunk, load_legal_corpus
from src.rag.embeddings import EmbeddingProvider, cosine_similarity


class LegalEmbedding(SQLModel, table=True):
    __tablename__ = "legal_embeddings"

    id: int | None = Field(default=None, primary_key=True)
    chunk_id: str = Field(index=True, unique=True, max_length=128)
    source: str = Field(max_length=64, index=True)
    titulo: str = Field(max_length=512)
    fundamentacao: str = Field(max_length=512)
    texto: str = Field(sa_column=Column(Text, nullable=False))
    # Vetor serializado em JSON para funcionar sem extensão em memória;
    # quando pgvector estiver disponível, a busca SQL usa operador <=> via raw SQL opcional.
    embedding: list[float] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    dims: int = Field(default=0, sa_column=Column(Integer, nullable=False))


@dataclass
class RetrievedChunk:
    chunk_id: str
    source: str
    titulo: str
    fundamentacao: str
    texto: str
    score: float


@dataclass
class LegalStore:
    embedder: EmbeddingProvider = field(default_factory=EmbeddingProvider)
    _memory: list[dict[str, Any]] = field(default_factory=list)

    async def ensure_schema(self) -> None:
        async with get_engine().begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    async def index_corpus(self, chunks: list[LegalChunk] | None = None) -> int:
        chunks = chunks or load_legal_corpus()
        if not chunks:
            return 0
        vectors = await self.embedder.embed([c.texto for c in chunks])
        rows = []
        for chunk, vector in zip(chunks, vectors):
            rows.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "source": chunk.source,
                    "titulo": chunk.titulo,
                    "fundamentacao": chunk.fundamentacao,
                    "texto": chunk.texto,
                    "embedding": vector,
                    "dims": len(vector),
                }
            )
        self._memory = rows
        try:
            factory = get_session_factory()
            async with factory() as session:
                await self.ensure_schema()
                await session.execute(delete(LegalEmbedding))
                for row in rows:
                    session.add(LegalEmbedding(**row))
                await session.commit()
        except Exception:
            # Postgres indisponível: mantém índice em memória para a sessão.
            pass
        return len(rows)

    async def _load_memory_from_db(self) -> None:
        if self._memory:
            return
        try:
            factory = get_session_factory()
            async with factory() as session:
                result = await session.execute(select(LegalEmbedding))
                entities = result.scalars().all()
                self._memory = [
                    {
                        "chunk_id": e.chunk_id,
                        "source": e.source,
                        "titulo": e.titulo,
                        "fundamentacao": e.fundamentacao,
                        "texto": e.texto,
                        "embedding": e.embedding,
                        "dims": e.dims,
                    }
                    for e in entities
                ]
        except Exception:
            if not self._memory:
                await self.index_corpus()

    async def search(self, query: str, *, top_k: int = 5) -> list[RetrievedChunk]:
        await self._load_memory_from_db()
        if not self._memory:
            await self.index_corpus()
        query_vec = (await self.embedder.embed([query]))[0]
        scored: list[RetrievedChunk] = []
        for row in self._memory:
            score = cosine_similarity(query_vec, row["embedding"])
            scored.append(
                RetrievedChunk(
                    chunk_id=row["chunk_id"],
                    source=row["source"],
                    titulo=row["titulo"],
                    fundamentacao=row["fundamentacao"],
                    texto=row["texto"],
                    score=score,
                )
            )
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]
