"""Testes Fase 3 — corpus Lei 14.133 e RAG em memória."""

from __future__ import annotations

import pytest

from src.rag.corpus import load_legal_corpus
from src.rag.store import LegalStore


def test_corpus_contains_art_164_and_art_69():
    chunks = load_legal_corpus()
    assert len(chunks) >= 5
    titles = " ".join(c.titulo for c in chunks).lower()
    texts = " ".join(c.texto for c in chunks).lower()
    assert "164" in titles or "164" in texts
    assert "69" in titles or "habilitação econômico" in texts or "economico" in texts


@pytest.mark.asyncio
async def test_rag_memory_search_marca():
    store = LegalStore()
    indexed = await store.index_corpus()
    assert indexed > 0
    hits = await store.search("indicação de marca sem justificativa técnica", top_k=3)
    assert hits
    assert hits[0].score > 0
    blob = (hits[0].titulo + hits[0].texto + hits[0].fundamentacao).lower()
    assert "marca" in blob or "41" in blob or "competitiv" in blob


@pytest.mark.asyncio
async def test_legal_rag_enrichment():
    from src.agents.legal_rag import analyze_legal_risks_with_rag
    from src.parser.docling_parser import ParsedDocument
    from pathlib import Path

    doc = ParsedDocument(
        source_path=Path("edital.md"),
        markdown="O fornecimento será somente da marca ACME, sem similar.",
        sections={},
        refs=[],
        engine="test",
    )
    from src.parser.docling_parser import refs_from_markdown, split_sections

    doc.sections = split_sections(doc.markdown)
    doc.refs = refs_from_markdown(doc.markdown)
    risks = await analyze_legal_risks_with_rag([doc])
    assert risks
    assert "RAG:" in risks[0].fundamentacao_legal or "14.133" in risks[0].fundamentacao_legal
