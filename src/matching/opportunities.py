"""Consulta paginada das oportunidades (matches) gravadas para um perfil."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.tables import InterestProfile, MatchItem, TenderAttachment, TenderIngest, TenderItemRow

MATCH_STATUSES = ("NOVO", "ENVIADO", "DESCARTADO", "FAVORITO")
MAX_PAGE_SIZE = 100


def clamp_page(pagina: int, tamanho: int) -> tuple[int, int]:
    return max(1, pagina), max(1, min(tamanho, MAX_PAGE_SIZE))


async def list_opportunities(
    session: AsyncSession,
    profile: InterestProfile,
    *,
    pagina: int = 1,
    tamanho: int = 20,
    status: str | None = None,
    apenas_alerta: bool = False,
    desde: date | None = None,
    uf: str | None = None,
) -> dict[str, Any]:
    pagina, tamanho = clamp_page(pagina, tamanho)
    conditions = [MatchItem.perfil_id == profile.id]
    if status:
        conditions.append(MatchItem.status == status)
    if apenas_alerta:
        conditions.append(MatchItem.alerta == True)  # noqa: E712
    if desde:
        conditions.append(MatchItem.created_at >= datetime.combine(desde, time.min, tzinfo=timezone.utc))
    if uf:
        conditions.append(TenderIngest.uf == uf.upper())

    joined = (
        select(MatchItem, TenderIngest, TenderItemRow)
        .join(TenderIngest, TenderIngest.id_pncp == MatchItem.id_pncp)
        .join(
            TenderItemRow,
            (TenderItemRow.id_pncp == MatchItem.id_pncp)
            & (TenderItemRow.numero_item == MatchItem.numero_item),
        )
        .where(*conditions)
    )
    total = (
        await session.exec(
            select(func.count())
            .select_from(MatchItem)
            .join(TenderIngest, TenderIngest.id_pncp == MatchItem.id_pncp)
            .join(
                TenderItemRow,
                (TenderItemRow.id_pncp == MatchItem.id_pncp)
                & (TenderItemRow.numero_item == MatchItem.numero_item),
            )
            .where(*conditions)
        )
    ).one()
    rows = (
        await session.exec(
            joined.order_by(
                MatchItem.score_total.desc(), MatchItem.created_at.desc(), MatchItem.numero_item
            )
            .offset((pagina - 1) * tamanho)
            .limit(tamanho)
        )
    ).all()

    ids = sorted({t.id_pncp for _, t, _ in rows})
    attachments: dict[str, list[dict[str, Any]]] = {}
    if ids:
        for a in (await session.exec(select(TenderAttachment).where(TenderAttachment.id_pncp.in_(ids)))).all():
            attachments.setdefault(a.id_pncp, []).append(
                {"titulo": a.titulo, "tipo": a.tipo_documento, "url": a.url_download}
            )

    items = [
        {
            "match_id": str(m.id),
            "status": m.status,
            "alerta": m.alerta,
            "score_total": m.score_total,
            "score_catmat": m.score_catmat,
            "score_lexico": m.score_lexico,
            "score_semantico": m.score_semantico,
            "encontrado_em": m.created_at.isoformat() if m.created_at else None,
            "edital": {
                "id_pncp": t.id_pncp,
                "orgao": t.orgao_comprador,
                "uf": t.uf,
                "municipio": t.municipio,
                "objeto": t.objeto_resumido,
                "encerramento_propostas": t.data_encerramento_propostas.isoformat()
                if t.data_encerramento_propostas
                else None,
                "anexos": attachments.get(t.id_pncp, []),
            },
            "item": {
                "numero_item": it.numero_item,
                "descricao": it.descricao,
                "quantidade": it.quantidade,
                "unidade_medida": it.unidade_medida,
                "valor_unitario_estimado": it.valor_unitario_estimado,
                "codigo_catmat_catser": it.codigo_catmat_catser,
            },
        }
        for m, t, it in rows
    ]
    return {
        "perfil_id": str(profile.id),
        "total": int(total),
        "pagina": pagina,
        "tamanho": tamanho,
        "paginas": (int(total) + tamanho - 1) // tamanho,
        "itens": items,
    }
