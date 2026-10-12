from __future__ import annotations

import asyncio
import hashlib
import math
import re
from collections import Counter

import httpx

from src.config import get_settings

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"
GEMINI_LOTE = 100  # limite da API por requisição
GEMINI_TENTATIVAS = 5
GEMINI_ESPERA_MAX = 70  # s; a cota gratuita (100 textos/min) se renova em até 1 minuto


def _retry_delay(r: httpx.Response) -> float:
    """Segundos pedidos pela API em `error.details[].retryDelay` (ex.: "21s"); 0 se ausente."""
    try:
        for d in r.json()["error"].get("details", []):
            m = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(d.get("retryDelay", "")))
            if m:
                return float(m.group(1)) + 1
    except (ValueError, KeyError, AttributeError):
        pass
    return 0.0


class EmbeddingError(RuntimeError):
    """Falha no provedor externo de embeddings (chave ausente, cota, rede)."""

_TOKEN_RE = re.compile(r"[a-záàâãéêíóôõúç0-9]{3,}", re.I)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


class EmbeddingProvider:
    """OpenAI (ou compatível), Gemini ou, sem chave, embedding lexical determinístico (dev/testes)."""

    def __init__(self, dimensions: int = 384, request_dimensions: bool = False) -> None:
        self.dimensions = dimensions
        self.request_dimensions = request_dimensions
        self.settings = get_settings()

    @property
    def backend(self) -> str:
        s = self.settings
        escolhido = (s.embedding_provider or "auto").strip().lower()
        if escolhido == "auto":
            return "openai" if s.openai_api_key else "gemini" if s.gemini_api_key else "hash"
        if escolhido not in ("openai", "gemini", "hash"):
            raise EmbeddingError(f"EMBEDDING_PROVIDER inválido: {escolhido!r} (use auto, openai, gemini ou hash).")
        return escolhido

    @property
    def cache_key(self) -> str:
        # O modelo entra na chave: vetores de modelos diferentes não podem se misturar no cache.
        if self.backend == "gemini":
            return f"gemini:{self.settings.gemini_embedding_model}:{self.dimensions}"[:32]
        return f"{self.backend}:{self.dimensions}"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        backend = self.backend
        if backend == "openai":
            return await self._embed_openai(texts)
        if backend == "gemini":
            return await self._embed_gemini(texts)
        return [self._embed_hash(text) for text in texts]

    async def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        from openai import AsyncOpenAI

        if not self.settings.openai_api_key:
            raise EmbeddingError("OPENAI_API_KEY não configurada.")
        client = AsyncOpenAI(api_key=self.settings.openai_api_key, base_url=self.settings.embedding_base_url or None)
        kwargs = {"dimensions": self.dimensions} if self.request_dimensions else {}
        response = await client.embeddings.create(
            model=self.settings.embedding_model,
            input=texts,
            **kwargs,
        )
        vectors = [list(item.embedding) for item in response.data]
        self.dimensions = len(vectors[0]) if vectors else self.dimensions
        return vectors

    async def _embed_gemini(self, texts: list[str]) -> list[list[float]]:
        if not self.settings.gemini_api_key:
            raise EmbeddingError("GEMINI_API_KEY não configurada.")
        model = self.settings.gemini_embedding_model
        url = GEMINI_URL.format(model=model)
        vectors: list[list[float]] = []
        async with httpx.AsyncClient(timeout=60, headers={"x-goog-api-key": self.settings.gemini_api_key}) as http:
            for i in range(0, len(texts), GEMINI_LOTE):
                corpo = {
                    "requests": [
                        {
                            "model": f"models/{model}",
                            "content": {"parts": [{"text": t}]},
                            "taskType": "SEMANTIC_SIMILARITY",
                            "outputDimensionality": self.dimensions,
                        }
                        for t in texts[i : i + GEMINI_LOTE]
                    ]
                }
                dados = await self._post_gemini(http, url, corpo)
                lote = [e.get("values") or [] for e in dados.get("embeddings", [])]
                if len(lote) != len(corpo["requests"]) or not all(lote):
                    raise EmbeddingError("Resposta do Gemini sem todos os vetores esperados.")
                vectors.extend(self._normalizar(v) for v in lote)
        return vectors

    @staticmethod
    async def _post_gemini(http: httpx.AsyncClient, url: str, corpo: dict) -> dict:
        # Plano gratuito tem cota por minuto: 429/5xx são tentados de novo, respeitando o `retryDelay` informado pela API.
        for tentativa in range(1, GEMINI_TENTATIVAS + 1):
            espera = 2**tentativa
            try:
                r = await http.post(url, json=corpo)
            except httpx.HTTPError as exc:
                if tentativa == GEMINI_TENTATIVAS:
                    raise EmbeddingError(f"Falha de rede ao chamar o Gemini: {exc}") from exc
            else:
                if r.status_code == 200:
                    return r.json()
                if r.status_code not in (429, 500, 502, 503, 504) or tentativa == GEMINI_TENTATIVAS:
                    raise EmbeddingError(f"Gemini respondeu {r.status_code}: {r.text[:200]}")
                espera = max(espera, _retry_delay(r))
            await asyncio.sleep(min(espera, GEMINI_ESPERA_MAX))
        raise EmbeddingError("Gemini indisponível.")  # inalcançável; satisfaz o tipo

    @staticmethod
    def _normalizar(v: list[float]) -> list[float]:
        # Com dimensão reduzida a API não devolve vetor unitário; o cosseno do projeto é produto escalar.
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def _embed_hash(self, text: str) -> list[float]:
        tokens = tokenize(text)
        counts = Counter(tokens)
        vec = [0.0] * self.dimensions
        if not counts:
            return vec
        for token, freq in counts.items():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign * (1.0 + math.log(1 + freq))
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))
