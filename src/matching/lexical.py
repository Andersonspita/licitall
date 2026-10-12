"""Camada 2 do funil: pontuação estruturada (CATMAT/CATSER) e léxica (termos do perfil).

Implementação em Python puro, sem banco: serve de referência testável e roda sobre os
poucos itens que passaram na Camada 1. A similaridade de trigramas segue a definição do
pg_trgm (conjuntos de trigramas com 2 espaços à esquerda e 1 à direita, razão de Jaccard),
de modo que uma futura versão com índices GIN no PostgreSQL dê resultados equivalentes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from src.matching.hard_filters import normalize_text

MAX_CATALOG = 40.0
MAX_LEXICAL = 35.0
TRIGRAM_THRESHOLD = 0.6
# As palavras do perfil são alternativas ("papel", "caneta", "toner"): achar uma já indica relevância. A 1ª vale 60% do
# léxico e cada outra +20% (3 palavras = 100%). Medido em ~550 itens reais (docs/fase/STATUS.md); calibrado num perfil só.
CREDITO_PRIMEIRO_TERMO = 0.6
CREDITO_POR_TERMO_EXTRA = 0.2

_COMMON_STOPWORDS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
    "para", "por", "com", "sem", "e", "ou", "um", "uma", "ao", "aos", "se", "que",
}
# Termos do ecossistema licitatório que causam correspondência artificial.
LICITATORY_STOPWORDS = {
    "srp", "ata", "pregao", "edital", "registro", "precos", "preco", "menor",
    "termo", "referencia", "aquisicao", "contratacao", "item", "lote",
}
STOPWORDS = _COMMON_STOPWORDS | LICITATORY_STOPWORDS


def stem(word: str) -> str:
    """Remoção simples de plural; suficiente para variações comuns em descrições de itens."""
    if len(word) > 4 and word.endswith("es"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word


def tokenize(text: str | None) -> list[str]:
    words = re.findall(r"[a-z0-9]+", normalize_text(text))
    return [stem(w) for w in words if w not in STOPWORDS and len(w) > 1]


def trigrams(word: str) -> set[str]:
    padded = f"  {word} "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


def trigram_similarity(a: str, b: str) -> float:
    ta, tb = trigrams(a), trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _candidates(tokens: list[str]) -> list[str]:
    """Tokens isolados e junções de vizinhos ('micro computado' ~ 'microcomputador')."""
    joined = [tokens[i] + tokens[i + 1] for i in range(len(tokens) - 1)]
    return tokens + joined


def term_present(term: str, tokens: list[str]) -> bool:
    """Todas as palavras do termo precisam aparecer (exatas ou com tolerância a erro de digitação)."""
    words = tokenize(term)
    if not words:
        return False
    pool = _candidates(tokens)
    for word in words:
        if word in tokens:
            continue
        if len(word) >= 5 and any(trigram_similarity(word, c) >= TRIGRAM_THRESHOLD for c in pool):
            continue
        return False
    return True


def credito_lexico(achados: int, total: int) -> float:
    """Fração (0–1) do léxico: o maior entre a curva de alternativas e a proporção simples (perfil de 1 palavra = 100%)."""
    if achados <= 0 or total <= 0:
        return 0.0
    curva = CREDITO_PRIMEIRO_TERMO + CREDITO_POR_TERMO_EXTRA * (achados - 1)
    return min(1.0, max(curva, achados / total))


@dataclass
class Layer2Result:
    score_catmat: float = 0.0
    score_lexico: float = 0.0
    termos_encontrados: list[str] = field(default_factory=list)
    obrigatorias_ausentes: list[str] = field(default_factory=list)
    candidato: bool = False

    @property
    def score_parcial(self) -> float:
        return round(self.score_catmat + self.score_lexico, 2)


def score_layer2(
    item: dict[str, Any],
    *,
    obrigatorias: Iterable[str] = (),
    positivas: Iterable[str] = (),
    catalogo: dict[int, float] | None = None,
    extra_text: str | None = None,
) -> Layer2Result:
    """Pontua um item. `catalogo` mapeia código CATMAT/CATSER → peso (0 a 1).

    CATMAT: 40 pts se o código for idêntico. A regra de 20 pts para "mesmo grupo/classe" não é
    aplicada porque o projeto não possui a hierarquia do catálogo federal.
    Léxico: até 35 pts; a 1ª palavra (obrigatória ou positiva) presente vale 60%, cada outra +20% (`credito_lexico`).
    Obrigatória ausente: o item deixa de ser candidato.
    """
    result = Layer2Result()
    code = item.get("codigo_catmat_catser")
    if code is not None and catalogo and int(code) in catalogo:
        result.score_catmat = round(MAX_CATALOG * max(0.0, min(float(catalogo[int(code)]), 1.0)), 2)

    tokens = tokenize(f"{item.get('descricao') or ''} {extra_text or ''}")
    mandatory = [t for t in obrigatorias if t and t.strip()]
    positive = [t for t in positivas if t and t.strip()]
    all_terms = mandatory + positive
    for term in all_terms:
        if term_present(term, tokens):
            result.termos_encontrados.append(term)
    result.obrigatorias_ausentes = [t for t in mandatory if t not in result.termos_encontrados]
    if all_terms:
        result.score_lexico = round(MAX_LEXICAL * credito_lexico(len(result.termos_encontrados), len(all_terms)), 2)

    result.candidato = not result.obrigatorias_ausentes and (
        result.score_catmat > 0 or result.score_lexico > 0
    )
    return result
