from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.compliance.lei_14133 import LC123_REF, LC123_VALOR_EXCLUSIVO_ME_EPP, is_exclusive_me_epp_value
from src.matching.client import MinhaReceitaClient, SITUACAO_ATIVA
from src.matching.cnae_map import infer_cnaes_from_text, merge_cnaes
from src.matching.eligibility import EligibilityVerdict, evaluate_eligibility
from src.matching.scoring import REVIEW_THRESHOLD, ScoreBreakdown, recommend, score_match
from src.models.enums import CompanySize
from src.ingestion.service import open_tenders_clause
from src.models.tables import TenderIngest, TenderItemRow


class ScoreFactors(BaseModel):
    cnae: float = 0.0
    geography: float = 0.0
    porte: float = 0.0
    economic: float = 0.0
    deadline: float = 0.0


class CompanyMatch(BaseModel):
    cnpj: str
    razao_social: str
    nome_fantasia: str | None = None
    uf: str | None = None
    municipio: str | None = None
    porte: str | None = None
    cnae_fiscal: str | None = None
    situacao: str | None = None
    score: float
    recommendation: str = "SKIP"
    factors: ScoreFactors = Field(default_factory=ScoreFactors)
    motivos: list[str] = Field(default_factory=list)
    eligibility_ok: bool = True
    eligibility_warnings: list[str] = Field(default_factory=list)
    eligibility_failures: list[str] = Field(default_factory=list)


class MatchmakingResult(BaseModel):
    id_pncp: str | None = None
    cnaes_busca: list[str] = Field(default_factory=list)
    uf: str | None = None
    municipio: str | None = None
    exclusivo_me_epp: bool = False
    require_proximity: bool = False
    total_candidatos: int = 0
    matches: list[CompanyMatch] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    thresholds: dict[str, float] = Field(
        default_factory=lambda: {"bid": 70.0, "review": REVIEW_THRESHOLD}
    )
    marco_legal: str = f"Lei 14.133/2021 c/c {LC123_REF}"


class OpportunityMatch(BaseModel):
    id_pncp: str
    orgao_comprador: str | None = None
    objeto_resumido: str | None = None
    uf: str | None = None
    municipio: str | None = None
    valor_total_estimado: float | None = None
    data_abertura_propostas: str | None = None
    data_encerramento_propostas: str | None = None
    score: float
    recommendation: str = "SKIP"
    factors: ScoreFactors = Field(default_factory=ScoreFactors)
    motivos: list[str] = Field(default_factory=list)
    eligibility_ok: bool = True
    eligibility_warnings: list[str] = Field(default_factory=list)
    eligibility_failures: list[str] = Field(default_factory=list)
    ramo_semantico: dict[str, Any] | None = None  # quando o ramo veio da similaridade de significado


class CompanyOpportunityResult(BaseModel):
    cnpj: str
    razao_social: str | None = None
    porte: str | None = None
    uf: str | None = None
    municipio: str | None = None
    cnaes_empresa: list[str] = Field(default_factory=list)
    total_avaliados: int = 0
    opportunities: list[OpportunityMatch] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    thresholds: dict[str, float] = Field(
        default_factory=lambda: {"bid": 70.0, "review": REVIEW_THRESHOLD}
    )
    marco_legal: str = f"Lei 14.133/2021 c/c {LC123_REF}"


async def _aplicar_ramo_semantico(
    session: AsyncSession,
    views: list[dict[str, Any]],
    company: dict[str, Any],
    avisos: list[str],
    embedder: Any | None,
    limiares: tuple[float, float] | None,
) -> None:
    """Marca `ramo_semantico` nos editais sem CNAE inferido. Falha do provedor vira aviso, nunca erro."""
    from src.matching import ramo_semantico as rs
    from src.matching.embedding_cache import vectors_with_cache

    sem_ramo = [v for v in views if not v.get("cnaes_compativeis") and rs.texto_objeto(v)]
    descricoes = rs.descricoes_cnae(company)
    if not sem_ramo or not descricoes:
        return
    if embedder is None:
        from src.rag.embeddings import EmbeddingProvider

        embedder = EmbeddingProvider(dimensions=512, request_dimensions=True)
    limiares = limiares or rs.LIMIARES_RAMO.get(embedder.backend)
    if limiares is None:
        if embedder.backend == "hash":
            avisos.append(
                f"{len(sem_ramo)} editais sem ramo identificado ficaram para revisão: configure GEMINI_API_KEY para "
                "compará-los por significado com os CNAEs da empresa."
            )
        else:
            avisos.append(f"Provedor {embedder.backend} sem limiares de ramo calibrados: comparação por significado desligada.")
        return
    try:
        res = await vectors_with_cache(session, embedder, descricoes + [rs.texto_objeto(v) for v in sem_ramo], parcial=True)
    except Exception as exc:  # noqa: BLE001 (banco/cache; o provedor já é tratado no modo parcial)
        await session.rollback()
        avisos.append(f"Comparação por significado indisponível ({exc}); editais sem ramo ficam para revisão.")
        return
    avaliados = rs.avaliar(sem_ramo, descricoes, res.vectors, limiares)
    for id_pncp, ramo in avaliados.items():
        next(v for v in sem_ramo if v["id_pncp"] == id_pncp)["ramo_semantico"] = ramo.as_dict()
    if res.erro is not None:
        avisos.append(
            f"Comparação por significado parcial: {len(avaliados)} de {len(sem_ramo)} editais sem ramo comparados; "
            f"o resto fica para revisão ({res.erro}). O que foi calculado ficou no cache: rode de novo depois para completar."
        )


# Pontuar é barato (Python puro); o teto só protege a memória com bases muito grandes.
MAX_TENDERS_AVALIADOS = 5000


def _is_active(company: dict[str, Any]) -> bool:
    return (
        company.get("situacao_cadastral") == SITUACAO_ATIVA
        or str(company.get("descricao_situacao_cadastral") or "").upper() == "ATIVA"
    )


def _company_cnae_list(company: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    principal = str(company.get("cnae_fiscal") or "").strip()
    if principal and principal != "None":
        codes.append(principal)
    for extra in company.get("cnaes_secundarios") or []:
        code = str(extra.get("codigo") or extra).strip()
        if code and code not in codes:
            codes.append(code)
    return codes


def resolve_cnaes(tender: dict[str, Any]) -> list[str]:
    existing = tender.get("cnaes_compativeis") or []
    objeto = str(tender.get("objeto_resumido") or "")
    inferred = infer_cnaes_from_text(objeto)
    item_blob = " ".join(
        str(item.get("descricao") or item.get("catmat_catser") or "")
        for item in (tender.get("itens") or [])
        if isinstance(item, dict)
    )
    inferred_items = infer_cnaes_from_text(item_blob)
    return merge_cnaes(existing, inferred, inferred_items)


def resolve_exclusivo_me_epp(tender: dict[str, Any]) -> bool:
    beneficios = tender.get("beneficios_me_epp") or {}
    if isinstance(beneficios, dict) and beneficios.get("exclusivo_me_epp"):
        return True
    if tender.get("exclusivo_me_epp"):
        return True
    itens = tender.get("itens") or []
    if any(isinstance(i, dict) and i.get("exclusivo_me_epp") for i in itens):
        return True
    return False


async def _itens_por_edital(session: AsyncSession, ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Só a descrição, para indicar o ramo. A exclusividade ME/EPP é por item: um item exclusivo não
    torna o edital inteiro exclusivo (isso penalizaria empresas "Demais" nos demais itens)."""
    if not ids:
        return {}
    stmt = (
        select(TenderItemRow.id_pncp, TenderItemRow.descricao)
        .where(TenderItemRow.id_pncp.in_(ids))
        .order_by(TenderItemRow.id_pncp, TenderItemRow.numero_item)
    )
    agrupado: dict[str, list[dict[str, Any]]] = {}
    for id_pncp, descricao in (await session.execute(stmt)).all():
        agrupado.setdefault(id_pncp, []).append({"descricao": descricao})
    return agrupado


def tender_from_ingest(row: TenderIngest, itens: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Normaliza linha de `tender_ingest` para o formato de scoring.

    `itens` (de `itens_contratacao`) substitui os itens do payload quando informado.
    """
    payload = row.payload or {}
    mapped = {
        "id_pncp": row.id_pncp,
        "orgao_comprador": row.orgao_comprador,
        "cnpj_orgao": row.cnpj_orgao,
        "uf": row.uf,
        "municipio": row.municipio,
        "modalidade": row.modalidade,
        "objeto_resumido": row.objeto_resumido,
        "valor_total_estimado": row.valor_total_estimado,
        "situacao": row.situacao,
        "data_publicacao": row.data_publicacao.isoformat() if row.data_publicacao else None,
        "data_abertura_propostas": (
            row.data_abertura_propostas.isoformat() if row.data_abertura_propostas else None
        ),
        "data_encerramento_propostas": (
            row.data_encerramento_propostas.isoformat() if row.data_encerramento_propostas else None
        ),
        "cnaes_compativeis": payload.get("cnaes_compativeis") or [],
        "beneficios_me_epp": payload.get("beneficios_me_epp") or {},
        "exclusivo_me_epp": payload.get("exclusivo_me_epp"),
        "itens": itens or payload.get("itens") or [],
    }
    if not mapped["cnaes_compativeis"]:
        mapped["cnaes_compativeis"] = resolve_cnaes(mapped)
    mapped["exclusivo_me_epp"] = resolve_exclusivo_me_epp(mapped)
    return mapped


def _build_company_match(
    company: dict[str, Any],
    breakdown: ScoreBreakdown,
    verdict: EligibilityVerdict,
) -> CompanyMatch:
    return CompanyMatch(
        cnpj=str(company.get("cnpj") or ""),
        razao_social=str(company.get("razao_social") or ""),
        nome_fantasia=company.get("nome_fantasia"),
        uf=company.get("uf"),
        municipio=company.get("municipio"),
        porte=company.get("porte"),
        cnae_fiscal=str(company.get("cnae_fiscal") or "") or None,
        situacao=str(company.get("descricao_situacao_cadastral") or "ATIVA"),
        score=breakdown.total,
        recommendation=breakdown.recommendation,
        factors=ScoreFactors(**breakdown.as_factors()),
        motivos=breakdown.explanations,
        eligibility_ok=verdict.eligible,
        eligibility_warnings=verdict.soft_warnings,
        eligibility_failures=verdict.hard_failures,
    )


def _build_opportunity_match(
    tender: dict[str, Any],
    breakdown: ScoreBreakdown,
    verdict: EligibilityVerdict,
) -> OpportunityMatch:
    return OpportunityMatch(
        id_pncp=str(tender.get("id_pncp") or ""),
        orgao_comprador=tender.get("orgao_comprador"),
        objeto_resumido=tender.get("objeto_resumido"),
        uf=tender.get("uf"),
        municipio=tender.get("municipio"),
        valor_total_estimado=(
            float(tender["valor_total_estimado"])
            if tender.get("valor_total_estimado") is not None
            else None
        ),
        data_abertura_propostas=_iso_or_none(tender.get("data_abertura_propostas")),
        data_encerramento_propostas=_iso_or_none(tender.get("data_encerramento_propostas")),
        score=breakdown.total,
        recommendation=breakdown.recommendation,
        factors=ScoreFactors(**breakdown.as_factors()),
        motivos=breakdown.explanations,
        eligibility_ok=verdict.eligible,
        eligibility_warnings=verdict.soft_warnings,
        eligibility_failures=verdict.hard_failures,
        ramo_semantico=tender.get("ramo_semantico"),
    )


def _iso_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()  # type: ignore[no-any-return]
    return str(value)


def _rank_pair(
    tender: dict[str, Any],
    company: dict[str, Any],
    *,
    require_proximity: bool,
) -> tuple[ScoreBreakdown, EligibilityVerdict]:
    verdict = evaluate_eligibility(
        tender=tender,
        company=company,
        require_proximity=require_proximity,
    )
    breakdown = score_match(
        tender=tender,
        company=company,
        require_proximity=require_proximity,
        hard_fail=not verdict.eligible,
    )
    # Alinha recommendation aos thresholds do YAML quando elegível
    if verdict.eligible:
        breakdown.recommendation = recommend(
            breakdown.total,
            hard_fail=False,
        )
        bid = float(verdict.thresholds.get("bid", 70))
        review = float(verdict.thresholds.get("review", REVIEW_THRESHOLD))
        if breakdown.total >= bid:
            breakdown.recommendation = "BID"
        elif breakdown.total >= review:
            breakdown.recommendation = "REVIEW"
        else:
            breakdown.recommendation = "SKIP"
    else:
        breakdown.recommendation = "SKIP"
    return breakdown, verdict


class MatchmakingService:
    """Cruza edital↔empresa (direção clássica) e empresa→oportunidades (inverso)."""

    def __init__(self, client: MinhaReceitaClient | None = None) -> None:
        self.client = client or MinhaReceitaClient()

    async def aclose(self) -> None:
        await self.client.aclose()

    async def match_tender(
        self,
        tender: dict[str, Any],
        *,
        limit: int = 30,
        min_score: float = REVIEW_THRESHOLD,
        require_proximity: bool = False,
        allow_demais_when_exclusive: bool = False,
    ) -> MatchmakingResult:
        id_pncp = tender.get("id_pncp")
        uf = (tender.get("uf") or None) and str(tender.get("uf")).upper()
        municipio = tender.get("municipio")
        cnaes = resolve_cnaes(tender)
        exclusivo = resolve_exclusivo_me_epp(tender)
        avisos: list[str] = []
        thresholds = {"bid": 70.0, "review": REVIEW_THRESHOLD}

        if not cnaes:
            avisos.append(
                "Nenhum CNAE inferido do objeto/itens. Informe cnaes_compativeis no tender "
                "ou enriqueça o mapa em matching/cnae_map.py."
            )
            return MatchmakingResult(
                id_pncp=id_pncp,
                uf=uf,
                municipio=str(municipio) if municipio else None,
                exclusivo_me_epp=exclusivo,
                require_proximity=require_proximity,
                avisos=avisos,
                thresholds=thresholds,
            )

        tender_view = dict(tender)
        tender_view["cnaes_compativeis"] = cnaes
        tender_view["exclusivo_me_epp"] = exclusivo

        portes: tuple[CompanySize, ...] | None = None
        if exclusivo and not allow_demais_when_exclusive:
            portes = (CompanySize.ME, CompanySize.EPP)
            avisos.append(
                f"Busca restrita a ME/EPP (exclusividade / LC 123; faixa típica até "
                f"R$ {LC123_VALOR_EXCLUSIVO_ME_EPP:,.0f})."
            )
        elif is_exclusive_me_epp_value(float(tender.get("valor_total_estimado") or 0)) and not exclusivo:
            avisos.append(
                "Valor na faixa de possível exclusividade ME/EPP (LC 123), "
                "mas o edital não declarou exclusividade — busca inclui demais portes."
            )

        try:
            companies = await self.client.search_active(
                cnae=cnaes,
                uf=uf if require_proximity or uf else None,
                municipio=None,
                portes=portes,
                limit=min(max(limit * 3, 50), 200),
            )
        except Exception as exc:
            avisos.append(
                f"Minha Receita indisponível ou base vazia: {exc}. "
                "Suba o serviço e carregue o ETL da Receita."
            )
            return MatchmakingResult(
                id_pncp=id_pncp,
                cnaes_busca=cnaes,
                uf=uf,
                municipio=str(municipio) if municipio else None,
                exclusivo_me_epp=exclusivo,
                require_proximity=require_proximity,
                avisos=avisos,
                thresholds=thresholds,
            )

        ranked: list[CompanyMatch] = []
        for company in companies:
            if not _is_active(company):
                continue
            breakdown, verdict = _rank_pair(
                tender_view,
                company,
                require_proximity=require_proximity,
            )
            thresholds = verdict.thresholds
            if breakdown.total < min_score and verdict.eligible:
                continue
            if not verdict.eligible and breakdown.total < min_score:
                continue
            ranked.append(_build_company_match(company, breakdown, verdict))

        ranked.sort(key=lambda m: m.score, reverse=True)
        return MatchmakingResult(
            id_pncp=id_pncp,
            cnaes_busca=cnaes,
            uf=uf,
            municipio=str(municipio) if municipio else None,
            exclusivo_me_epp=exclusivo,
            require_proximity=require_proximity,
            total_candidatos=len(companies),
            matches=ranked[:limit],
            avisos=avisos,
            thresholds=thresholds,
        )

    async def list_open_tenders(
        self,
        session: AsyncSession,
        *,
        uf: str | None = None,
        limit: int = MAX_TENDERS_AVALIADOS,
    ) -> list[dict[str, Any]]:
        """Editais ainda abertos (situação + prazo), os que encerram primeiro antes.

        Junta as descrições de `itens_contratacao` para a inferência de CNAE: sem elas, só o
        objeto do edital indica o ramo.
        """
        stmt = (
            select(TenderIngest)
            .where(open_tenders_clause())
            .order_by(TenderIngest.data_encerramento_propostas.asc().nulls_last(), TenderIngest.id)
            .limit(limit)
        )
        if uf:
            stmt = stmt.where(TenderIngest.uf == uf.upper())
        rows = (await session.execute(stmt)).scalars().all()
        itens = await _itens_por_edital(session, [row.id_pncp for row in rows])
        return [tender_from_ingest(row, itens.get(row.id_pncp)) for row in rows]

    async def match_company(
        self,
        cnpj: str,
        *,
        tenders: list[dict[str, Any]] | None = None,
        session: AsyncSession | None = None,
        limit: int = 20,
        min_score: float = REVIEW_THRESHOLD,
        require_proximity: bool = False,
        uf_filter: str | None = None,
        company: dict[str, Any] | None = None,
        embedder: Any | None = None,
        ramo_limiares: tuple[float, float] | None = None,
    ) -> CompanyOpportunityResult:
        """Match inverso: CNPJ/empresa → oportunidades ranqueadas.

        Com `session`, editais cujo ramo o mapa de palavras-chave não identifica são comparados por significado com
        os CNAEs da empresa (`ramo_semantico`), se o provedor de embeddings tiver limiares calibrados.
        """
        avisos: list[str] = []
        thresholds = {"bid": 70.0, "review": REVIEW_THRESHOLD}

        if company is None:
            try:
                company = await self.client.get_company(cnpj)
            except Exception as exc:
                digits = "".join(ch for ch in cnpj if ch.isalnum())
                return CompanyOpportunityResult(
                    cnpj=digits,
                    avisos=[f"Falha ao consultar CNPJ na Minha Receita: {exc}"],
                    thresholds=thresholds,
                )

        digits = "".join(ch for ch in str(company.get("cnpj") or cnpj) if ch.isalnum())
        if not _is_active(company):
            avisos.append("Empresa não está ATIVA — matching bloqueado pela regra empresa_ativa.")
            return CompanyOpportunityResult(
                cnpj=digits,
                razao_social=company.get("razao_social"),
                porte=company.get("porte"),
                uf=company.get("uf"),
                municipio=company.get("municipio"),
                cnaes_empresa=_company_cnae_list(company),
                avisos=avisos,
                thresholds=thresholds,
            )

        if tenders is None:
            if session is None:
                avisos.append(
                    "Nenhuma lista de editais fornecida e sem sessão DB — "
                    "passe `tenders` ou sincronize PNCP (`POST /ingestion/pncp/sync`)."
                )
                return CompanyOpportunityResult(
                    cnpj=digits,
                    razao_social=company.get("razao_social"),
                    porte=company.get("porte"),
                    uf=company.get("uf"),
                    municipio=company.get("municipio"),
                    cnaes_empresa=_company_cnae_list(company),
                    avisos=avisos,
                    thresholds=thresholds,
                )
            prefer_uf = uf_filter or (company.get("uf") if require_proximity else uf_filter)
            tenders = await self.list_open_tenders(
                session,
                uf=str(prefer_uf).upper() if prefer_uf else None,
            )
            if not tenders:
                avisos.append(
                    "Nenhum edital aberto em tender_ingest. Rode POST /ingestion/pncp/sync antes do match inverso."
                )
            elif len(tenders) >= MAX_TENDERS_AVALIADOS:
                avisos.append(
                    f"Avaliados só os {MAX_TENDERS_AVALIADOS} editais abertos que encerram primeiro; "
                    "filtre por UF para cobrir os demais."
                )

        company_cnaes = set(_company_cnae_list(company))
        views: list[dict[str, Any]] = []
        for raw in tenders:
            tender_view = dict(raw)
            tender_view["cnaes_compativeis"] = resolve_cnaes(tender_view)
            tender_view["exclusivo_me_epp"] = resolve_exclusivo_me_epp(tender_view)
            views.append(tender_view)
        if session is not None:
            await _aplicar_ramo_semantico(session, views, company, avisos, embedder, ramo_limiares)

        ranked: list[OpportunityMatch] = []
        for tender_view in views:

            # Atalho: se há CNAEs na empresa e no edital sem interseção, ainda pontua baixo —
            # mas evita ruído extremo quando ambos existem e não cruzam.
            tender_cnaes = {str(c) for c in tender_view.get("cnaes_compativeis") or []}
            if company_cnaes and tender_cnaes and not (company_cnaes & tender_cnaes):
                if require_proximity:
                    continue

            breakdown, verdict = _rank_pair(
                tender_view,
                company,
                require_proximity=require_proximity,
            )
            thresholds = verdict.thresholds
            if breakdown.total < min_score:
                continue
            ranked.append(_build_opportunity_match(tender_view, breakdown, verdict))

        ranked.sort(key=lambda m: m.score, reverse=True)
        return CompanyOpportunityResult(
            cnpj=digits,
            razao_social=company.get("razao_social"),
            porte=company.get("porte"),
            uf=company.get("uf"),
            municipio=company.get("municipio"),
            cnaes_empresa=_company_cnae_list(company),
            total_avaliados=len(tenders),
            opportunities=ranked[:limit],
            avisos=avisos,
            thresholds=thresholds,
        )
