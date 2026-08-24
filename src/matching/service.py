from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.compliance.lei_14133 import LC123_REF, LC123_VALOR_EXCLUSIVO_ME_EPP, is_exclusive_me_epp_value
from src.matching.client import MinhaReceitaClient, PORTE_MAP, SITUACAO_ATIVA
from src.matching.cnae_map import infer_cnaes_from_text, merge_cnaes
from src.matching.scoring import matching_score
from src.models.enums import CompanySize


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
    motivos: list[str] = Field(default_factory=list)


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
    marco_legal: str = f"Lei 14.133/2021 c/c {LC123_REF}"


def _is_active(company: dict[str, Any]) -> bool:
    return (
        company.get("situacao_cadastral") == SITUACAO_ATIVA
        or str(company.get("descricao_situacao_cadastral") or "").upper() == "ATIVA"
    )


def _motivos(tender: dict[str, Any], company: dict[str, Any], score: float) -> list[str]:
    reasons: list[str] = []
    tender_cnaes = {str(c) for c in tender.get("cnaes_compativeis") or []}
    company_cnaes = set()
    company_cnaes.add(str(company.get("cnae_fiscal") or ""))
    for extra in company.get("cnaes_secundarios") or []:
        company_cnaes.add(str(extra.get("codigo") or extra))
    if tender_cnaes & company_cnaes:
        reasons.append("CNAE compatível com o objeto")
    if str(tender.get("uf") or "").upper() == str(company.get("uf") or "").upper():
        reasons.append(f"Mesma UF ({company.get('uf')})")
    if str(tender.get("municipio") or "").strip().upper() == str(company.get("municipio") or "").strip().upper():
        reasons.append("Mesmo município")
    porte = PORTE_MAP.get(str(company.get("porte") or "").upper(), CompanySize.NAO_INFORMADO)
    if tender.get("exclusivo_me_epp") and porte in {CompanySize.ME, CompanySize.EPP}:
        reasons.append("Porte ME/EPP compatível com exclusividade (LC 123/2006)")
    reasons.append(f"Score {score:.1f}")
    return reasons


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
    valor = float(tender.get("valor_total_estimado") or 0)
    itens = tender.get("itens") or []
    if any(isinstance(i, dict) and i.get("exclusivo_me_epp") for i in itens):
        return True
    # Não assume exclusividade só pelo valor; só sinaliza faixa LC 123
    return False


class MatchmakingService:
    """Cruza edital estruturado com empresas ATIVAS da Minha Receita."""

    def __init__(self, client: MinhaReceitaClient | None = None) -> None:
        self.client = client or MinhaReceitaClient()

    async def aclose(self) -> None:
        await self.client.aclose()

    async def match_tender(
        self,
        tender: dict[str, Any],
        *,
        limit: int = 30,
        min_score: float = 40.0,
        require_proximity: bool = False,
        allow_demais_when_exclusive: bool = False,
    ) -> MatchmakingResult:
        id_pncp = tender.get("id_pncp")
        uf = (tender.get("uf") or None) and str(tender.get("uf")).upper()
        municipio = tender.get("municipio")
        cnaes = resolve_cnaes(tender)
        exclusivo = resolve_exclusivo_me_epp(tender)
        avisos: list[str] = []

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
                municipio=None,  # filtro fino no score; IBGE code varia na API
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
            )

        ranked: list[CompanyMatch] = []
        for company in companies:
            if not _is_active(company):
                continue
            score = matching_score(
                tender=tender_view,
                company=company,
                require_proximity=require_proximity,
            )
            if score < min_score:
                continue
            ranked.append(
                CompanyMatch(
                    cnpj=str(company.get("cnpj") or ""),
                    razao_social=str(company.get("razao_social") or ""),
                    nome_fantasia=company.get("nome_fantasia"),
                    uf=company.get("uf"),
                    municipio=company.get("municipio"),
                    porte=company.get("porte"),
                    cnae_fiscal=str(company.get("cnae_fiscal") or "") or None,
                    situacao=str(company.get("descricao_situacao_cadastral") or "ATIVA"),
                    score=score,
                    motivos=_motivos(tender_view, company, score),
                )
            )

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
        )
