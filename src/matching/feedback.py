"""Feedback do cliente sobre oportunidades (relevante / irrelevante) e sugestão de termos negativos."""

from __future__ import annotations

import re
import uuid
from typing import Any, Iterable

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.matching.hard_filters import normalize_text
from src.matching.lexical import STOPWORDS, stem
from src.models.tables import (
    InterestProfile,
    MatchItem,
    ProfileKeywordRule,
    TenderItemRow,
)

KEYWORD_TYPES = ("OBRIGATORIA", "POSITIVA", "NEGATIVA")
_WORD = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)


def _stems(text: str | None) -> set[str]:
    return {stem(w) for w in re.findall(r"[a-z0-9]+", normalize_text(text))}


def suggest_negative_terms(
    descricao: str,
    *,
    known_terms: Iterable[str],
    favorite_descriptions: Iterable[str] = (),
    limit: int = 5,
) -> list[str]:
    """Palavras da descrição que podem ir para a lista negativa.

    Exclui: palavras já conhecidas do perfil (interesse, obrigatórias, negativas), palavras
    que aparecem em itens que o cliente marcou como relevantes, números, termos curtos e
    stopwords. Mantém a ordem de aparição e a grafia original (em minúsculas).
    """
    blocked = set().union(*[_stems(t) for t in known_terms]) if known_terms else set()
    for fav in favorite_descriptions:
        blocked |= _stems(fav)
    out: list[str] = []
    seen: set[str] = set()
    for word in _WORD.findall(descricao or ""):
        norm = normalize_text(word)
        key = stem(norm)
        if (
            len(norm) < 4
            or norm.isdigit()
            or any(ch.isdigit() for ch in norm)
            or norm in STOPWORDS
            or key in blocked
            or key in seen
        ):
            continue
        seen.add(key)
        out.append(word.lower())
        if len(out) >= limit:
            break
    return out


async def apply_feedback(
    session: AsyncSession, match: MatchItem, *, relevante: bool
) -> dict[str, Any]:
    """Relevante → FAVORITO. Irrelevante → DESCARTADO + sugestões de termos negativos."""
    match.status = "FAVORITO" if relevante else "DESCARTADO"
    session.add(match)
    await session.commit()
    result: dict[str, Any] = {"match_id": str(match.id), "status": match.status, "sugestoes_negativas": []}
    if relevante:
        return result

    item = (
        await session.exec(
            select(TenderItemRow).where(
                TenderItemRow.id_pncp == match.id_pncp, TenderItemRow.numero_item == match.numero_item
            )
        )
    ).first()
    rules = (
        await session.exec(select(ProfileKeywordRule).where(ProfileKeywordRule.perfil_id == match.perfil_id))
    ).all()
    favs = (
        await session.exec(
            select(TenderItemRow.descricao)
            .join(
                MatchItem,
                (MatchItem.id_pncp == TenderItemRow.id_pncp)
                & (MatchItem.numero_item == TenderItemRow.numero_item),
            )
            .where(MatchItem.perfil_id == match.perfil_id, MatchItem.status == "FAVORITO")
        )
    ).all()
    result["sugestoes_negativas"] = suggest_negative_terms(
        item.descricao if item else "",
        known_terms=[r.termo for r in rules],
        favorite_descriptions=list(favs),
    )
    return result


async def add_keyword(
    session: AsyncSession, profile: InterestProfile, tipo: str, termo: str
) -> bool:
    """Acrescenta um termo ao perfil. False se já existia (comparação sem acento/caixa)."""
    if tipo not in KEYWORD_TYPES:
        raise ValueError(f"tipo inválido: {tipo}")
    termo = termo.strip()
    if not termo:
        raise ValueError("termo vazio")
    existing = (
        await session.exec(
            select(ProfileKeywordRule).where(
                ProfileKeywordRule.perfil_id == profile.id, ProfileKeywordRule.tipo == tipo
            )
        )
    ).all()
    if any(normalize_text(r.termo) == normalize_text(termo) for r in existing):
        return False
    session.add(ProfileKeywordRule(id=uuid.uuid4(), perfil_id=profile.id, tipo=tipo, termo=termo[:100]))
    await session.commit()
    return True
