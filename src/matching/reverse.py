"""Busca reversa (percolation): para cada edital novo, quais perfis ativos casam com seus itens."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.ingestion.service import hydrate_attachments, hydrate_items
from src.matching.profiles import match_full
from src.models.tables import InterestProfile, MatchItem, TenderIngest, TenderItemRow

logger = logging.getLogger("licitall.matching.reverse")

MIN_STORE_SCORE = 40.0  # abaixo disso o item não vale ser guardado


def accepts_uf(profile_ufs: list[str] | tuple[str, ...], uf: str | None) -> bool:
    """Perfil sem UFs aceita o Brasil inteiro."""
    ufs = {u.upper() for u in profile_ufs if u}
    return not ufs or (uf or "").upper() in ufs


async def _save_matches(session: AsyncSession, profile_id: Any, id_pncp: str, candidates: list[dict[str, Any]]) -> int:
    saved = 0
    for c in candidates:
        if c["score_total"] < MIN_STORE_SCORE:
            continue
        values = {
            "perfil_id": profile_id,
            "id_pncp": id_pncp,
            "numero_item": c["numero_item"],
            "score_catmat": c["score_catmat"],
            "score_lexico": c["score_lexico"],
            "score_semantico": c["score_semantico"],
            "score_total": c["score_total"],
            "alerta": c["alerta"],
            "status": "NOVO",
            "created_at": datetime.now(timezone.utc),
        }
        stmt = pg_insert(MatchItem).values(**values)
        # Reprocessar atualiza as notas, mas nunca desfaz ENVIADO/DESCARTADO/FAVORITO.
        update = {k: getattr(stmt.excluded, k) for k in ("score_catmat", "score_lexico", "score_semantico", "score_total", "alerta")}
        await session.execute(stmt.on_conflict_do_update(constraint="unq_match_perfil_item", set_=update))
        saved += 1
    await session.commit()
    return saved


async def run_reverse_match(
    session: AsyncSession,
    *,
    id_pncps: list[str],
    client: Any,
    embedder: Any,
    max_tenders: int = 200,
    delay: float = 0.0,
) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "editais_recebidos": len(id_pncps),
        "editais_avaliados": 0,
        "ignorados_por_uf": 0,
        "falhas_hidratacao": 0,
        "editais_com_anexos": 0,
        "matches_gravados": 0,
        "sem_perfis_ativos": False,
        "truncado": len(id_pncps) > max_tenders,
    }
    async def load_profiles() -> list[InterestProfile]:
        return list((await session.exec(select(InterestProfile).where(InterestProfile.ativo == True))).all())  # noqa: E712

    profiles = await load_profiles()
    if not profiles:
        stats["sem_perfis_ativos"] = True
        return stats

    for id_pncp in id_pncps[:max_tenders]:
        tender = (await session.exec(select(TenderIngest).where(TenderIngest.id_pncp == id_pncp))).first()
        if tender is None:
            continue
        eligible = [p for p in profiles if accepts_uf(p.ufs_permitidas, tender.uf)]
        if not eligible:
            stats["ignorados_por_uf"] += 1
            continue
        has_items = (
            await session.exec(select(TenderItemRow.id).where(TenderItemRow.id_pncp == id_pncp).limit(1))
        ).first()
        if has_items is None:
            try:
                await hydrate_items(session, client, id_pncp)
            except Exception as exc:  # um edital com erro não pode parar os demais
                await session.rollback()
                profiles = await load_profiles()  # rollback expira os objetos carregados
                stats["falhas_hidratacao"] += 1
                logger.warning("Itens de %s indisponíveis: %s", id_pncp, exc)
                continue
            if delay:
                await asyncio.sleep(delay)
        stats["editais_avaliados"] += 1
        saved_here = 0
        for profile in eligible:
            result = await match_full(session, profile, id_pncp, embedder)
            if result and result["itens_total"]:
                saved_here += await _save_matches(session, profile.id, id_pncp, result["candidatos"])
        stats["matches_gravados"] += saved_here
        if saved_here:
            # Os links dos documentos só interessam para editais que renderam oportunidade.
            try:
                if await hydrate_attachments(session, client, id_pncp):
                    stats["editais_com_anexos"] += 1
            except Exception as exc:
                await session.rollback()
                profiles = await load_profiles()
                logger.warning("Anexos de %s indisponíveis: %s", id_pncp, exc)
    return stats
