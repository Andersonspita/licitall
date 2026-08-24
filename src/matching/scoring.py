from __future__ import annotations

from typing import Any

from src.models.enums import CompanySize
from src.matching.client import PORTE_MAP
from src.compliance.lei_14133 import LC123_VALOR_EXCLUSIVO_ME_EPP

ME_EPP_LOT_LIMIT = LC123_VALOR_EXCLUSIVO_ME_EPP


def matching_score(
    *,
    tender: dict[str, Any],
    company: dict[str, Any],
    require_proximity: bool = False,
) -> float:
    """Pontuação 0–100: CNAE (60) + UF/município (25) + porte LC 123 (15).

    Apenas empresas ATIVAS devem ser passadas pelo caller.
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
        if _norm(tender.get("municipio")) and _norm(tender.get("municipio")) == _norm(company.get("municipio")):
            score += 10.0
    elif require_proximity:
        return 0.0

    exclusivo = bool(tender.get("exclusivo_me_epp"))
    beneficios = tender.get("beneficios_me_epp") or {}
    if isinstance(beneficios, dict) and beneficios.get("exclusivo_me_epp"):
        exclusivo = True

    porte = PORTE_MAP.get(str(company.get("porte") or "").upper(), CompanySize.NAO_INFORMADO)
    if exclusivo:
        if porte in {CompanySize.ME, CompanySize.EPP}:
            score += 15.0
        else:
            return min(score * 0.3, 35.0)  # penaliza demais em lote exclusivo
    else:
        score += 10.0
        if isinstance(beneficios, dict) and beneficios.get("cota_reservada_25"):
            if porte in {CompanySize.ME, CompanySize.EPP}:
                score += 5.0
    return min(score, 100.0)


def _company_cnaes(company: dict[str, Any]) -> set[str]:
    codes = {str(company.get("cnae_fiscal") or "")}
    for extra in company.get("cnaes_secundarios") or []:
        codes.add(str(extra.get("codigo") or extra))
    return {code for code in codes if code and code != "None"}


def _norm(value: Any) -> str:
    return str(value or "").strip().upper()
