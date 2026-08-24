from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

from src.config import get_settings

_TOKEN_RE = re.compile(r"[a-záàâãéêíóôõúç0-9]{3,}", re.I)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


class EmbeddingProvider:
    """OpenAI quando houver chave; senão embedding lexical determinístico (dev/testes)."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions
        self.settings = get_settings()

    @property
    def backend(self) -> str:
        return "openai" if self.settings.openai_api_key else "hash"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.settings.openai_api_key:
            return await self._embed_openai(texts)
        return [self._embed_hash(text) for text in texts]

    async def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        response = await client.embeddings.create(
            model=self.settings.embedding_model,
            input=texts,
        )
        vectors = [list(item.embedding) for item in response.data]
        self.dimensions = len(vectors[0]) if vectors else self.dimensions
        return vectors

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
