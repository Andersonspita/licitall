from __future__ import annotations

from typing import Any

from src.models.enums import CompanySize
from src.matching.client import PORTE_MAP

ME_EPP_LOT_LIMIT = 80_000.0


def matching_score(
    *,
    tender: dict[str, Any],
    company: dict[str, Any],
    require_proximity: bool = False,
) -> float:
    """Pontuação 0–100 entre edital estruturado e empresa da Receita.

    CNAE (60) + UF/município (25) + porte compatível com ME/EPP (15).
    """
    score = 0.0
    tender_cnaes = {str(code) for code in tender.get("cnaes_compativeis") or []}
    company_cnaes = _company_cnaes(company)
    if tender_cnaes and company_cnaes & tender_cnaes:
        score += 60.0
    elif not tender_cnaes:
        score += 20.0

    tender_uf = str(tender.get("uf") or "").upper()
    company_uf = str(company.get("uf") or "").upper()
    if tender_uf and tender_uf == company_uf:
        score += 15.0
        municipio_tender = _norm(tender.get("municipio"))
        municipio_company = _norm(company.get("municipio"))
        if municipio_tender and municipio_tender == municipio_company:
            score += 10.0
    elif require_proximity:
        return 0.0

    exclusivo = bool(tender.get("exclusivo_me_epp")) or float(tender.get("valor_total_estimado") or 0) <= ME_EPP_LOT_LIMIT
    porte = PORTE_MAP.get(str(company.get("porte") or "").upper(), CompanySize.NAO_INFORMADO)
    if exclusivo and porte in {CompanySize.ME, CompanySize.EPP}:
        score += 15.0
    elif not exclusivo:
        score += 10.0
    return min(score, 100.0)


def _company_cnaes(company: dict[str, Any]) -> set[str]:
    codes = {str(company.get("cnae_fiscal") or "")}
    for extra in company.get("cnaes_secundarios") or []:
        codes.add(str(extra.get("codigo") or extra))
    return {code for code in codes if code and code != "None"}


def _norm(value: Any) -> str:
    return str(value or "").strip().upper()
