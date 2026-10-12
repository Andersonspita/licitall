"""Perfis de interesse do cliente e aplicação dos filtros rígidos sobre itens de uma contratação."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.matching.lexical import score_layer2
from src.matching.semantic import (
    content_hash,
    cosine,
    final_score,
    profile_description,
    resolve_vectors,
    sanitize_item_text,
    semantic_score,
)
from src.matching.hard_filters import ProfileFilters, evaluate_hard_filters, normalize_text
from src.models.tables import (
    EmbeddingCacheRow,
    InterestProfile,
    ProfileDescription,
    ProfileCatalogRule,
    ProfileKeywordRule,
    TenderIngest,
    TenderItemRow,
)

KEYWORD_TYPES = ("OBRIGATORIA", "POSITIVA", "NEGATIVA")


def _clean_terms(terms: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for term in terms:
        key = normalize_text(term)
        if key and key not in seen:
            seen[key] = term.strip()
    return list(seen.values())


async def create_profile(
    session: AsyncSession,
    *,
    empresa_id: uuid.UUID,
    nome_perfil: str,
    ufs_permitidas: list[str],
    valor_minimo_item: float = 0.0,
    valor_maximo_item: float | None = None,
    apenas_me_epp: bool = False,
    palavras: dict[str, list[str]] | None = None,
    codigos_catalogo: list[int] | None = None,
    descricao_sintetica: str | None = None,
) -> InterestProfile:
    profile = InterestProfile(
        empresa_id=empresa_id,
        nome_perfil=nome_perfil.strip(),
        ufs_permitidas=sorted({u.upper() for u in ufs_permitidas if u}),
        valor_minimo_item=valor_minimo_item,
        valor_maximo_item=valor_maximo_item,
        apenas_me_epp=apenas_me_epp,
    )
    session.add(profile)
    await session.flush()
    for tipo, termos in (palavras or {}).items():
        if tipo not in KEYWORD_TYPES:
            raise ValueError(f"tipo de palavra-chave inválido: {tipo}")
        for termo in _clean_terms(termos):
            session.add(ProfileKeywordRule(perfil_id=profile.id, tipo=tipo, termo=termo[:100]))
    for codigo in sorted(set(codigos_catalogo or [])):
        session.add(ProfileCatalogRule(perfil_id=profile.id, codigo_item=codigo))
    if descricao_sintetica and descricao_sintetica.strip():
        session.add(ProfileDescription(perfil_id=profile.id, descricao=descricao_sintetica.strip()))
    await session.commit()
    await session.refresh(profile)
    return profile


async def load_profile_view(session: AsyncSession, profile: InterestProfile) -> dict[str, Any]:
    rules = (
        await session.exec(select(ProfileKeywordRule).where(ProfileKeywordRule.perfil_id == profile.id))
    ).all()
    codes = (
        await session.exec(select(ProfileCatalogRule).where(ProfileCatalogRule.perfil_id == profile.id))
    ).all()
    palavras: dict[str, list[str]] = {t: [] for t in KEYWORD_TYPES}
    for rule in rules:
        palavras[rule.tipo].append(rule.termo)
    return {
        "id": str(profile.id),
        "empresa_id": str(profile.empresa_id),
        "nome_perfil": profile.nome_perfil,
        "ufs_permitidas": list(profile.ufs_permitidas),
        "valor_minimo_item": profile.valor_minimo_item,
        "valor_maximo_item": profile.valor_maximo_item,
        "apenas_me_epp": profile.apenas_me_epp,
        "ativo": profile.ativo,
        "palavras": palavras,
        "codigos_catalogo": sorted(c.codigo_item for c in codes),
    }


async def get_profile(session: AsyncSession, profile_id: uuid.UUID) -> InterestProfile | None:
    return await session.get(InterestProfile, profile_id)


async def list_profiles(session: AsyncSession, empresa_id: uuid.UUID) -> list[InterestProfile]:
    stmt = select(InterestProfile).where(InterestProfile.empresa_id == empresa_id).order_by(
        InterestProfile.created_at
    )
    return list((await session.exec(stmt)).all())


async def delete_profile(session: AsyncSession, profile: InterestProfile) -> None:
    # DELETE direto (sem carregar objetos): evita avisos de contagem do ORM; os demais filhos
    # (matches, agendamento) saem por ON DELETE CASCADE.
    for model in (ProfileKeywordRule, ProfileCatalogRule, ProfileDescription):
        await session.execute(sa_delete(model).where(model.perfil_id == profile.id))
    await session.execute(sa_delete(InterestProfile).where(InterestProfile.id == profile.id))
    await session.commit()


async def filters_for(session: AsyncSession, profile: InterestProfile) -> ProfileFilters:
    negatives = (
        await session.exec(
            select(ProfileKeywordRule).where(
                ProfileKeywordRule.perfil_id == profile.id, ProfileKeywordRule.tipo == "NEGATIVA"
            )
        )
    ).all()
    return ProfileFilters(
        ufs_permitidas=tuple(profile.ufs_permitidas),
        valor_minimo_item=profile.valor_minimo_item or 0.0,
        valor_maximo_item=profile.valor_maximo_item,
        apenas_me_epp=profile.apenas_me_epp,
        termos_negativos=tuple(r.termo for r in negatives),
    )


def _item_dict(row: TenderItemRow) -> dict[str, Any]:
    return {
        "numero_item": row.numero_item,
        "descricao": row.descricao,
        "codigo_catmat_catser": row.codigo_catmat_catser,
        "quantidade": row.quantidade,
        "unidade_medida": row.unidade_medida,
        "valor_unitario_estimado": row.valor_unitario_estimado,
        "valor_total_estimado": row.valor_total_estimado,
        "exclusivo_me_epp": row.exclusivo_me_epp,
    }


async def apply_hard_filters(
    session: AsyncSession, profile: InterestProfile, id_pncp: str
) -> dict[str, Any] | None:
    """Aplica a Camada 1 aos itens já hidratados de uma contratação. None se a contratação não existe."""
    tender = (
        await session.exec(select(TenderIngest).where(TenderIngest.id_pncp == id_pncp))
    ).first()
    if tender is None:
        return None
    rows = (
        await session.exec(
            select(TenderItemRow).where(TenderItemRow.id_pncp == id_pncp).order_by(TenderItemRow.numero_item)
        )
    ).all()
    filters = await filters_for(session, profile)
    approved: list[dict[str, Any]] = []
    discarded: list[dict[str, Any]] = []
    for row in rows:
        item = _item_dict(row)
        result = evaluate_hard_filters(
            item, filters, uf=tender.uf, extra_text=tender.objeto_resumido
        )
        if result.passed:
            approved.append(item)
        else:
            discarded.append({**item, "motivos": result.reasons})
    return {
        "id_pncp": id_pncp,
        "perfil_id": str(profile.id),
        "itens_total": len(rows),
        "aprovados": approved,
        "descartados": discarded,
    }


async def match_candidates(
    session: AsyncSession, profile: InterestProfile, id_pncp: str
) -> dict[str, Any] | None:
    """Camada 1 + Camada 2: candidatos ranqueados por score parcial (máx. 75 de 100)."""
    layer1 = await apply_hard_filters(session, profile, id_pncp)
    if layer1 is None:
        return None
    tender = (
        await session.exec(select(TenderIngest).where(TenderIngest.id_pncp == id_pncp))
    ).first()
    rules = (
        await session.exec(select(ProfileKeywordRule).where(ProfileKeywordRule.perfil_id == profile.id))
    ).all()
    codes = (
        await session.exec(select(ProfileCatalogRule).where(ProfileCatalogRule.perfil_id == profile.id))
    ).all()
    by_type = {t: [r.termo for r in rules if r.tipo == t] for t in KEYWORD_TYPES}
    catalog = {c.codigo_item: c.peso for c in codes}

    candidates: list[dict[str, Any]] = []
    not_candidates = 0
    for item in layer1["aprovados"]:
        result = score_layer2(
            item,
            obrigatorias=by_type["OBRIGATORIA"],
            positivas=by_type["POSITIVA"],
            catalogo=catalog,
            extra_text=tender.objeto_resumido if tender else None,
        )
        if not result.candidato:
            not_candidates += 1
            continue
        candidates.append(
            {
                **item,
                "score_catmat": result.score_catmat,
                "score_lexico": result.score_lexico,
                "score_parcial": result.score_parcial,
                "termos_encontrados": result.termos_encontrados,
            }
        )
    candidates.sort(key=lambda c: (-c["score_parcial"], c["numero_item"]))
    return {
        "id_pncp": id_pncp,
        "perfil_id": layer1["perfil_id"],
        "itens_total": layer1["itens_total"],
        "descartados_camada1": len(layer1["descartados"]),
        "sem_correspondencia_camada2": not_candidates,
        "score_maximo_parcial": 75,
        "candidatos": candidates,
    }


async def match_full(
    session: AsyncSession, profile: InterestProfile, id_pncp: str, embedder: Any
) -> dict[str, Any] | None:
    """Funil completo: Camada 1 → 2 → 3, score 0–100 e alerta (≥ 65).

    O embedding é gerado só para itens aprovados na Camada 1 (lazy) e é reutilizado por hash.
    O vetor do item usa apenas a descrição sanitizada (sem o objeto), para que o mesmo item
    publicado por órgãos diferentes compartilhe o mesmo vetor em cache.
    """
    layer1 = await apply_hard_filters(session, profile, id_pncp)
    if layer1 is None:
        return None
    tender = (
        await session.exec(select(TenderIngest).where(TenderIngest.id_pncp == id_pncp))
    ).first()
    rules = (
        await session.exec(select(ProfileKeywordRule).where(ProfileKeywordRule.perfil_id == profile.id))
    ).all()
    codes = (
        await session.exec(select(ProfileCatalogRule).where(ProfileCatalogRule.perfil_id == profile.id))
    ).all()
    override = await session.get(ProfileDescription, profile.id)
    by_type = {t: [r.termo for r in rules if r.tipo == t] for t in KEYWORD_TYPES}
    catalog = {c.codigo_item: c.peso for c in codes}

    scored: list[tuple[dict[str, Any], Any, str]] = []
    excluded_mandatory = 0
    for item in layer1["aprovados"]:
        l2 = score_layer2(
            item,
            obrigatorias=by_type["OBRIGATORIA"],
            positivas=by_type["POSITIVA"],
            catalogo=catalog,
            extra_text=tender.objeto_resumido if tender else None,
        )
        if l2.obrigatorias_ausentes:
            excluded_mandatory += 1
            continue
        scored.append((item, l2, sanitize_item_text(item["descricao"])))

    profile_text = profile_description(
        profile.nome_perfil,
        by_type["OBRIGATORIA"],
        by_type["POSITIVA"],
        override.descricao if override else None,
    )
    texts = [t for _, _, t in scored if t] + ([profile_text] if profile_text else [])
    hashes = {content_hash(t) for t in texts}
    backend = embedder.cache_key
    cached_rows = []
    if hashes:
        cached_rows = (
            await session.exec(
                select(EmbeddingCacheRow).where(
                    EmbeddingCacheRow.backend == backend,
                    EmbeddingCacheRow.content_hash.in_(hashes),
                )
            )
        ).all()
    cached = {r.content_hash: r.embedding for r in cached_rows}
    resolution = await resolve_vectors(texts, cached, embedder)
    for h, (text, vec) in resolution.new_entries.items():
        await session.execute(
            pg_insert(EmbeddingCacheRow)
            .values(
                content_hash=h,
                backend=backend,
                texto_base=text,
                embedding=vec,
                created_at=datetime.now(timezone.utc),
            )
            .on_conflict_do_nothing()
        )
    await session.commit()

    profile_vec = resolution.vectors.get(content_hash(profile_text)) if profile_text else None
    candidates: list[dict[str, Any]] = []
    for item, l2, text in scored:
        sim = cosine(profile_vec, resolution.vectors[content_hash(text)]) if profile_vec and text else 0.0
        sem = semantic_score(sim, embedder.backend)
        final = final_score(
            l2.score_catmat, l2.score_lexico, sem, catalogo_aplicavel=bool(catalog) and item.get("codigo_catmat_catser") is not None
        )
        if final["score_total"] <= 0:
            continue
        candidates.append(
            {
                **item,
                "score_catmat": l2.score_catmat,
                "score_lexico": l2.score_lexico,
                "score_semantico": sem,
                **final,
                "termos_encontrados": l2.termos_encontrados,
            }
        )
    candidates.sort(key=lambda c: (-c["score_total"], c["numero_item"]))
    return {
        "id_pncp": id_pncp,
        "perfil_id": layer1["perfil_id"],
        "itens_total": layer1["itens_total"],
        "descartados_camada1": len(layer1["descartados"]),
        "excluidos_obrigatoria_ausente": excluded_mandatory,
        "limiar_alerta": 65,
        "embedding": {
            "backend": backend,
            "textos_enviados_a_api": resolution.api_texts_sent,
            "chamadas_a_api": resolution.api_calls,
            "reaproveitados_do_cache": len(cached),
        },
        "candidatos": candidates,
    }
