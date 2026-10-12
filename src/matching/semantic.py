"""Camada 3 do funil: similaridade semântica com cache de embeddings endereçável por conteúdo.

O mesmo texto normalizado nunca é enviado duas vezes ao provedor: o vetor é indexado pelo
SHA-256 do texto. A lógica de cache/lote é pura (opera sobre dicts) para ser testável sem banco.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.matching.hard_filters import normalize_text
from src.matching.lexical import MAX_LEXICAL

MAX_SEMANTIC = 25.0
MAX_TEXT_CHARS = 500
BATCH_SIZE = 100
ALERT_THRESHOLD = 65.0

_NOISE_TO_END = re.compile(
    r"\b(conforme|processo|valor\s+estimado|marca\s+de\s+refer[eê]ncia)\b.*",
    re.IGNORECASE | re.DOTALL,
)
_ITEM_PREFIX = re.compile(r"\b(item|lote|c[oó]digo)\s*:?\s*\d+\s*[-:.]*", re.IGNORECASE)
_LEADING_VERB = re.compile(r"^(aquisi[cç][aã]o|contrata[cç][aã]o|fornecimento)\s+de\s+", re.IGNORECASE)


def sanitize_item_text(text: str | None) -> str:
    """Remove numeração e referências burocráticas, normaliza e limita a ~500 caracteres."""
    cleaned = _ITEM_PREFIX.sub(" ", str(text or ""))
    cleaned = _NOISE_TO_END.sub(" ", cleaned)
    cleaned = re.sub(r"[,;:()\"]", " ", cleaned)
    cleaned = _LEADING_VERB.sub("", normalize_text(cleaned).lstrip(" -"))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .-")
    return cleaned[:MAX_TEXT_CHARS].strip()


def content_hash(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass
class CacheResolution:
    vectors: dict[str, list[float]] = field(default_factory=dict)  # hash → vetor (todos)
    new_entries: dict[str, tuple[str, list[float]]] = field(default_factory=dict)  # hash → (texto, vetor)
    api_texts_sent: int = 0
    api_calls: int = 0


async def resolve_vectors(
    texts: list[str],
    cached: dict[str, list[float]],
    embedder: Embedder,
    *,
    batch_size: int = BATCH_SIZE,
) -> CacheResolution:
    """Devolve o vetor de cada texto, chamando o provedor só para textos inéditos (em lotes)."""
    result = CacheResolution()
    pending: dict[str, str] = {}
    for text in texts:
        h = content_hash(text)
        if h in cached:
            result.vectors[h] = cached[h]
        elif text:
            pending.setdefault(h, text)
    hashes = list(pending)
    for start in range(0, len(hashes), batch_size):
        chunk = hashes[start : start + batch_size]
        vectors = await embedder.embed([pending[h] for h in chunk])
        result.api_calls += 1
        result.api_texts_sent += len(chunk)
        for h, vec in zip(chunk, vectors):
            result.vectors[h] = vec
            result.new_entries[h] = (pending[h], vec)
    return result


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


# (piso, teto) do cosseno por provedor. Modelos densos dão cosseno alto até para textos sem relação, então o cosseno
# bruto inflaria todo item. `gemini`: medido em 240 itens reais (out/2026, 5 perfis; ver docs/fase/STATUS.md): sem relação
# mediana 0,76 e p95 0,80; relacionados mediana 0,79 e p90 0,84. `hash` (local) já parte de ~0. `openai`: NÃO medido.
CALIBRACAO: dict[str, tuple[float, float]] = {"gemini": (0.76, 0.86)}


def semantic_score(similarity: float, backend: str = "hash") -> float:
    """0–25 pontos; abaixo do piso do provedor não pontua (similaridade negativa também não penaliza)."""
    piso, teto = CALIBRACAO.get(backend, (0.0, 1.0))
    return round(MAX_SEMANTIC * max(0.0, min((similarity - piso) / (teto - piso), 1.0)), 2)


def profile_description(nome: str, obrigatorias: list[str], positivas: list[str], override: str | None = None) -> str:
    """Texto sintético do perfil: o informado pelo cliente ou nome + termos de interesse."""
    if override and override.strip():
        return sanitize_item_text(override)
    return sanitize_item_text(" ".join([nome, *obrigatorias, *positivas]))


def final_score(catmat: float, lexico: float, semantico: float, catalogo_aplicavel: bool = True) -> dict[str, Any]:
    """Soma das camadas. Sem CATMAT comparável (perfil sem códigos ou item sem código) a camada de catálogo não pode
    pontuar nem contar contra o item: o restante (léxico + semântico, máx. 60) é reescalado para 0–100."""
    if catalogo_aplicavel:
        total = round(min(catmat + lexico + semantico, 100.0), 2)
    else:
        total = round(min((lexico + semantico) / (MAX_LEXICAL + MAX_SEMANTIC) * 100.0, 100.0), 2)
    return {"score_total": total, "alerta": total >= ALERT_THRESHOLD}
