"""Digest de oportunidades agrupado por edital (evita uma notificação por item)."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.tables import InterestProfile, MatchItem, TenderIngest, TenderItemRow


def group_matches(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agrupa matches por contratação; editais com melhor score primeiro."""
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        g = groups.setdefault(
            row["id_pncp"],
            {
                "id_pncp": row["id_pncp"],
                "orgao": row.get("orgao"),
                "uf": row.get("uf"),
                "objeto": row.get("objeto"),
                "itens": [],
            },
        )
        g["itens"].append(
            {
                "numero_item": row["numero_item"],
                "descricao": row.get("descricao") or "",
                "score_total": row["score_total"],
            }
        )
    result = []
    for g in groups.values():
        g["itens"].sort(key=lambda i: (-i["score_total"], i["numero_item"]))
        g["qtd_itens"] = len(g["itens"])
        g["melhor_score"] = g["itens"][0]["score_total"]
        result.append(g)
    result.sort(key=lambda g: (-g["melhor_score"], -g["qtd_itens"], g["id_pncp"]))
    return result


def _clip(text: str | None, size: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= size else text[: size - 3] + "..."


def build_digest_text(profile_name: str, groups: list[dict[str, Any]], top_n: int = 5) -> str:
    lines = ["LicitAll — novas oportunidades", "", f"Perfil: {profile_name}", ""]
    shown = groups[:top_n]
    if not shown:
        lines.append("Nenhuma oportunidade nova acima do limiar neste ciclo.")
    for idx, g in enumerate(shown, start=1):
        plural = "item compatível" if g["qtd_itens"] == 1 else "itens compatíveis"
        lines.append(f"{idx}. {g.get('orgao') or 'Órgão n/d'} ({g.get('uf') or 'UF?'}) — {g['qtd_itens']} {plural}")
        lines.append(f"   {_clip(g.get('objeto'), 110) or 'objeto n/d'}")
        for it in g["itens"][:3]:
            lines.append(f"   • item {it['numero_item']}: {_clip(it['descricao'], 70)} (score {it['score_total']:.0f})")
        if g["qtd_itens"] > 3:
            lines.append(f"   • … e mais {g['qtd_itens'] - 3}")
        lines.append(f"   PNCP {g['id_pncp']}")
        lines.append("")
    if len(groups) > top_n:
        lines.append(f"(+{len(groups) - top_n} edital(is) não exibido(s))")
        lines.append("")
    lines.append("Minutas de IA exigem revisão humana (Lei 8.906/1994). Marco: Lei 14.133/2021.")
    return "\n".join(lines).rstrip() + "\n"


async def load_new_matches(session: AsyncSession, profile: InterestProfile) -> list[dict[str, Any]]:
    """Matches com status NOVO e alerta, já com dados do edital e do item."""
    stmt = (
        select(MatchItem, TenderIngest, TenderItemRow)
        .join(TenderIngest, TenderIngest.id_pncp == MatchItem.id_pncp)
        .join(
            TenderItemRow,
            (TenderItemRow.id_pncp == MatchItem.id_pncp)
            & (TenderItemRow.numero_item == MatchItem.numero_item),
        )
        .where(MatchItem.perfil_id == profile.id, MatchItem.status == "NOVO", MatchItem.alerta == True)  # noqa: E712
    )
    rows = (await session.exec(stmt)).all()
    return [
        {
            "id_pncp": m.id_pncp,
            "orgao": t.orgao_comprador,
            "uf": t.uf,
            "objeto": t.objeto_resumido,
            "numero_item": m.numero_item,
            "descricao": it.descricao,
            "score_total": m.score_total,
        }
        for m, t, it in rows
    ]


async def mark_sent(session: AsyncSession, profile: InterestProfile, id_pncps: list[str]) -> int:
    if not id_pncps:
        return 0
    rows = (
        await session.exec(
            select(MatchItem).where(
                MatchItem.perfil_id == profile.id,
                MatchItem.status == "NOVO",
                MatchItem.id_pncp.in_(id_pncps),
            )
        )
    ).all()
    for row in rows:
        row.status = "ENVIADO"
        session.add(row)
    await session.commit()
    return len(rows)


Sender = Callable[[str, str, str | None], Awaitable[None]]


async def evolution_sender(phone: str, text: str, instance: str | None) -> None:
    """Envio real via Evolution API (levanta exceção em caso de falha)."""
    from src.outreach import OutreachService

    service = OutreachService()
    try:
        await service.client.send_text(phone, text, instance=instance)
    finally:
        await service.aclose()


async def send_digest(
    session: AsyncSession,
    profile: InterestProfile,
    *,
    phone: str,
    top_n: int,
    instance: str | None,
    sender: Sender,
) -> dict[str, Any]:
    """Monta e envia o digest; só marca ENVIADO depois do envio bem-sucedido."""
    groups = group_matches(await load_new_matches(session, profile))
    if not groups:
        return {"sent": False, "motivo": "Nenhum match novo com alerta para este perfil"}
    shown = groups[:top_n]
    text = build_digest_text(profile.nome_perfil, groups, top_n=top_n)
    await sender(phone, text, instance)
    marked = await mark_sent(session, profile, [g["id_pncp"] for g in shown])
    return {"sent": True, "editais_enviados": len(shown), "itens_marcados": marked, "preview": text[:800]}
