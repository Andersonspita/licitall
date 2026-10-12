"""Os testes nunca chamam provedores externos de embeddings, mesmo com chaves no .env do desenvolvedor."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _sem_chaves_de_embeddings(monkeypatch):
    from src.config import get_settings

    for nome in ("OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(nome, "")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "auto")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
