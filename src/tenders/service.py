"""Listagem e detalhe de editais reais (Postgres `tender_ingest` + filesystem)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.compliance.lei_14133 import is_business_day, prazo_impugnacao_art_164
from src.config import get_settings
from src.ingestion.storage import DocumentStorage
from src.models.tables import TenderIngest


def _as_date(value: date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def _iso(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value.isoformat()


def dias_uteis_restantes(limite: date, *, hoje: date | None = None) -> int:
    """Dias úteis restantes até `limite` (inclusive). Negativo se já passou."""
    ref = hoje or date.today()
    if ref > limite:
        delta = 0
        current = limite
        while current < ref:
            current += timedelta(days=1)
            if is_business_day(current):
                delta -= 1
        return delta
    count = 0
    current = ref
    while current <= limite:
        if is_business_day(current):
            count += 1
        current += timedelta(days=1)
    return count


def art164_meta(row: TenderIngest) -> dict[str, Any]:
    abertura = _as_date(row.data_abertura_propostas)
    if not abertura:
        return {
            "tem_abertura": False,
            "limite_impugnacao": None,
            "dias_uteis_restantes": None,
            "critico": False,
            "fonte": None,
        }
    limite = prazo_impugnacao_art_164(abertura)
    restantes = dias_uteis_restantes(limite)
    return {
        "tem_abertura": True,
        "data_abertura": abertura.isoformat(),
        "limite_impugnacao": limite.isoformat(),
        "dias_uteis_restantes": restantes,
        "critico": 0 < restantes <= 3,
        "vencido": restantes <= 0,
        "fonte": "calculado_art_164",
    }


def filesystem_hints(id_pncp: str) -> dict[str, Any]:
    settings = get_settings()
    storage = DocumentStorage(settings.raw_docs_path)
    try:
        files = [p.name for p in storage.list_files(id_pncp)]
    except Exception:
        files = []
    tender_dir = storage.tender_dir(id_pncp)
    parsed_dir = tender_dir / "_parsed"
    kit_dir = tender_dir / "_kit"
    return {
        "has_docs": bool(files),
        "doc_count": len(files),
        "files": files[:50],
        "has_parsed": parsed_dir.is_dir() and any(parsed_dir.iterdir()) if parsed_dir.exists() else False,
        "has_kit": kit_dir.is_dir() and any(kit_dir.iterdir()) if kit_dir.exists() else False,
    }


def serialize_tender(row: TenderIngest, *, include_fs: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": row.id,
        "id_pncp": row.id_pncp,
        "orgao_comprador": row.orgao_comprador,
        "cnpj_orgao": row.cnpj_orgao,
        "uf": row.uf,
        "municipio": row.municipio,
        "modalidade": row.modalidade,
        "objeto_resumido": row.objeto_resumido,
        "valor_total_estimado": row.valor_total_estimado,
        "situacao": row.situacao,
        "data_publicacao": _iso(row.data_publicacao),
        "data_abertura_propostas": _iso(row.data_abertura_propostas),
        "data_encerramento_propostas": _iso(row.data_encerramento_propostas),
        "status": row.status,
        "updated_at": _iso(row.updated_at),
        "created_at": _iso(row.created_at),
        "art164": art164_meta(row),
    }
    if include_fs:
        data["filesystem"] = filesystem_hints(row.id_pncp)
    return data


def _apply_filters(
    stmt: Any,
    *,
    uf: str | None,
    status: str | None,
    q: str | None,
) -> Any:
    if uf:
        stmt = stmt.where(TenderIngest.uf == uf.upper())
    if status:
        stmt = stmt.where(TenderIngest.status == status.upper())
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                TenderIngest.id_pncp.ilike(term),
                TenderIngest.orgao_comprador.ilike(term),
                TenderIngest.objeto_resumido.ilike(term),
                TenderIngest.municipio.ilike(term),
                TenderIngest.modalidade.ilike(term),
            )
        )
    return stmt


async def list_tenders(
    session: AsyncSession,
    *,
    uf: str | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    count_stmt = select(func.count()).select_from(TenderIngest)
    count_stmt = _apply_filters(count_stmt, uf=uf, status=status, q=q)
    total = int((await session.execute(count_stmt)).scalar_one() or 0)

    stmt = select(TenderIngest).order_by(TenderIngest.updated_at.desc()).offset(offset).limit(limit)
    stmt = _apply_filters(stmt, uf=uf, status=status, q=q)
    rows = (await session.execute(stmt)).scalars().all()
    items = [serialize_tender(r) for r in rows]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    }


async def get_tender(session: AsyncSession, id_pncp: str) -> dict[str, Any] | None:
    stmt = select(TenderIngest).where(TenderIngest.id_pncp == id_pncp)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if not row:
        return None
    return serialize_tender(row, include_fs=True)


async def tender_stats(session: AsyncSession) -> dict[str, Any]:
    total = int(
        (await session.execute(select(func.count()).select_from(TenderIngest))).scalar_one() or 0
    )
    valor = (
        await session.execute(select(func.coalesce(func.sum(TenderIngest.valor_total_estimado), 0.0)))
    ).scalar_one()
    by_status_rows = (
        await session.execute(
            select(TenderIngest.status, func.count()).group_by(TenderIngest.status)
        )
    ).all()
    by_uf_rows = (
        await session.execute(
            select(TenderIngest.uf, func.count())
            .where(TenderIngest.uf.is_not(None))
            .group_by(TenderIngest.uf)
            .order_by(func.count().desc())
            .limit(12)
        )
    ).all()

    # Criticos Art.164: carrega amostra recente e filtra em Python (datas abertas)
    recent = (
        await session.execute(
            select(TenderIngest)
            .where(TenderIngest.data_abertura_propostas.is_not(None))
            .order_by(TenderIngest.data_abertura_propostas.asc())
            .limit(500)
        )
    ).scalars().all()
    criticos: list[dict[str, Any]] = []
    for row in recent:
        meta = art164_meta(row)
        if meta.get("critico"):
            criticos.append(
                {
                    "id_pncp": row.id_pncp,
                    "orgao_comprador": row.orgao_comprador,
                    "uf": row.uf,
                    "objeto_resumido": (row.objeto_resumido or "")[:160],
                    "art164": meta,
                }
            )
    criticos.sort(key=lambda x: x["art164"].get("dias_uteis_restantes") or 99)

    return {
        "total": total,
        "valor_total_estimado_sum": float(valor or 0),
        "by_status": {str(s or "UNKNOWN"): int(c) for s, c in by_status_rows},
        "by_uf": {str(u): int(c) for u, c in by_uf_rows},
        "prazos_criticos_count": len(criticos),
        "prazos_criticos": criticos[:20],
    }
