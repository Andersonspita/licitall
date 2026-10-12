"""Etapa 3 — provedor 512 dim e SQL do cache (compilado; sem Postgres)."""

from __future__ import annotations

import asyncio

from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select

from src.matching.semantic import content_hash, resolve_vectors
from src.models.tables import EmbeddingCacheRow
from src.rag.embeddings import EmbeddingProvider


def test_provedor_hash_respeita_512_dimensoes_e_chave_de_cache(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    from src.config import get_settings

    get_settings.cache_clear()
    p = EmbeddingProvider(dimensions=512, request_dimensions=True)
    vecs = asyncio.run(p.embed(["papel a4 alcalino"]))
    assert len(vecs[0]) == 512
    assert p.cache_key == "hash:512"


def test_vetor_do_provedor_ligado_ao_cache_por_hash():
    p = EmbeddingProvider(dimensions=512)
    texts = ["pneu 175/70 r14 radial"] * 50
    res = asyncio.run(resolve_vectors(texts, {}, p))
    assert res.api_texts_sent == 1
    assert content_hash(texts[0]) in res.vectors


def test_sql_do_cache_compila_para_postgres():
    d = postgresql.dialect()
    ins = pg_insert(EmbeddingCacheRow).values(
        content_hash="a" * 64, backend="hash:512", texto_base="x", embedding=[0.1]
    ).on_conflict_do_nothing()
    assert "ON CONFLICT DO NOTHING" in str(ins.compile(dialect=d))
    sel = select(EmbeddingCacheRow).where(
        EmbeddingCacheRow.backend == "hash:512", EmbeddingCacheRow.content_hash.in_(["a" * 64])
    )
    sql = str(sel.compile(dialect=d))
    assert "embeddings_cache.content_hash IN" in sql and "embeddings_cache.backend =" in sql
