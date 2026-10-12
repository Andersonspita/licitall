"""Provedor Gemini de embeddings (resposta simulada; sem rede) e escolha do provedor."""

from __future__ import annotations

import math

import httpx
import pytest

from src.config import get_settings
from src.rag import embeddings as emb
from src.rag.embeddings import EmbeddingError, EmbeddingProvider


_CLIENTE_REAL = httpx.AsyncClient


def _config(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()


def _simular(monkeypatch, handler):
    """Faz o provedor falar com um servidor falso e sem esperas entre tentativas."""
    monkeypatch.setattr(emb.httpx, "AsyncClient", lambda **kw: _CLIENTE_REAL(transport=httpx.MockTransport(handler), **kw))

    async def sem_espera(_):
        return None

    monkeypatch.setattr(emb.asyncio, "sleep", sem_espera)


def test_escolha_do_provedor(monkeypatch):
    assert EmbeddingProvider().backend == "hash"
    _config(monkeypatch, GEMINI_API_KEY="g")
    assert EmbeddingProvider().backend == "gemini"
    _config(monkeypatch, OPENAI_API_KEY="o")
    assert EmbeddingProvider().backend == "openai"  # OpenAI tem prioridade no modo auto
    _config(monkeypatch, EMBEDDING_PROVIDER="gemini")
    assert EmbeddingProvider().backend == "gemini"  # escolha explícita vale mais
    _config(monkeypatch, EMBEDDING_PROVIDER="hash")
    assert EmbeddingProvider().backend == "hash"
    _config(monkeypatch, EMBEDDING_PROVIDER="claude")
    with pytest.raises(EmbeddingError):
        EmbeddingProvider().backend  # noqa: B018


@pytest.mark.asyncio
async def test_gemini_envia_lotes_pede_dimensao_e_normaliza(monkeypatch):
    _config(monkeypatch, GEMINI_API_KEY="chave-falsa")
    chamadas = []

    def handler(req: httpx.Request) -> httpx.Response:
        corpo = req.read().decode()
        import json

        dados = json.loads(corpo)
        chamadas.append((req.headers["x-goog-api-key"], req.url.path, dados))
        n = len(dados["requests"])
        return httpx.Response(200, json={"embeddings": [{"values": [3.0, 4.0, 0.0]} for _ in range(n)]})

    _simular(monkeypatch, handler)
    p = EmbeddingProvider(dimensions=3, request_dimensions=True)
    vetores = await p.embed([f"texto {i}" for i in range(150)])

    assert len(vetores) == 150 and len(chamadas) == 2  # 100 + 50
    assert [len(c[2]["requests"]) for c in chamadas] == [100, 50]
    chave, caminho, corpo = chamadas[0]
    assert chave == "chave-falsa" and caminho.endswith("/gemini-embedding-001:batchEmbedContents")
    pedido = corpo["requests"][0]
    assert pedido["outputDimensionality"] == 3 and pedido["model"] == "models/gemini-embedding-001"
    assert math.isclose(sum(x * x for x in vetores[0]), 1.0)  # normalizado
    assert p.cache_key == "gemini:gemini-embedding-001:3"


@pytest.mark.asyncio
async def test_gemini_repete_em_429_e_depois_funciona(monkeypatch):
    _config(monkeypatch, GEMINI_API_KEY="k")
    respostas = [httpx.Response(429, text="cota"), httpx.Response(503, text="x"),
                 httpx.Response(200, json={"embeddings": [{"values": [1.0, 0.0]}]})]
    _simular(monkeypatch, lambda req: respostas.pop(0))
    assert await EmbeddingProvider(dimensions=2).embed(["a"]) == [[1.0, 0.0]]
    assert respostas == []


@pytest.mark.asyncio
async def test_gemini_erros_viram_embedding_error(monkeypatch):
    _config(monkeypatch, GEMINI_API_KEY="k")
    _simular(monkeypatch, lambda req: httpx.Response(400, text="chave inválida"))
    with pytest.raises(EmbeddingError, match="400"):  # 400 não é repetido
        await EmbeddingProvider(dimensions=2).embed(["a"])

    _simular(monkeypatch, lambda req: httpx.Response(429, text="cota"))
    with pytest.raises(EmbeddingError, match="429"):  # esgota as tentativas
        await EmbeddingProvider(dimensions=2).embed(["a"])

    _simular(monkeypatch, lambda req: httpx.Response(200, json={"embeddings": []}))
    with pytest.raises(EmbeddingError):  # resposta incompleta
        await EmbeddingProvider(dimensions=2).embed(["a"])


@pytest.mark.asyncio
async def test_provedor_explicito_sem_chave_falha_claramente(monkeypatch):
    _config(monkeypatch, EMBEDDING_PROVIDER="gemini")
    with pytest.raises(EmbeddingError, match="GEMINI_API_KEY"):
        await EmbeddingProvider(dimensions=2).embed(["a"])
    _config(monkeypatch, EMBEDDING_PROVIDER="openai")
    with pytest.raises(EmbeddingError, match="OPENAI_API_KEY"):
        await EmbeddingProvider(dimensions=2).embed(["a"])
