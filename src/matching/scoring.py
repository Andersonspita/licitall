"""Score explicável 0–100 com recomendação BID / REVIEW / SKIP.

Componentes (máx. 100):
  CNAE 35 · Geografia 20 · Porte/LC 123 15 · Fit econômico 15 · Prazo/Art. 164 15
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Literal

from src.compliance.lei_14133 import (
    LC123_VALOR_EXCLUSIVO_ME_EPP,
    is_business_day,
    prazo_impugnacao_art_164,
)
from src.matching.client import PORTE_MAP
from src.models.enums import CompanySize

Recommendation = Literal["BID", "REVIEW", "SKIP"]

WEIGHT_CNAE = 35.0
WEIGHT_GEO = 20.0
WEIGHT_PORTE = 15.0
WEIGHT_ECONOMIC = 15.0
WEIGHT_DEADLINE = 15.0

BID_THRESHOLD = 70.0
REVIEW_THRESHOLD = 40.0


@dataclass
class ScoreBreakdown:
    cnae: float = 0.0
    geography: float = 0.0
    porte: float = 0.0
    economic: float = 0.0
    deadline: float = 0.0
    total: float = 0.0
    explanations: list[str] = field(default_factory=list)
    recommendation: Recommendation = "SKIP"

    def as_factors(self) -> dict[str, float]:
        return {
            "cnae": round(self.cnae, 1),
            "geography": round(self.geography, 1),
            "porte": round(self.porte, 1),
            "economic": round(self.economic, 1),
            "deadline": round(self.deadline, 1),
        }


def recommend(score: float, *, hard_fail: bool = False) -> Recommendation:
    if hard_fail or score < REVIEW_THRESHOLD:
        return "SKIP"
    if score >= BID_THRESHOLD:
        return "BID"
    return "REVIEW"


def score_match(
    *,
    tender: dict[str, Any],
    company: dict[str, Any],
    require_proximity: bool = False,
    hard_fail: bool = False,
    today: date | None = None,
) -> ScoreBreakdown:
    """Calcula breakdown explicável. `hard_fail` aplica teto pós-elegibilidade."""
    today = today or datetime.now(timezone.utc).date()
    explanations: list[str] = []

    cnae_pts, cnae_notes = _score_cnae(tender, company)
    explanations.extend(cnae_notes)

    geo_pts, geo_notes, uf_ok = _score_geography(tender, company, require_proximity)
    explanations.extend(geo_notes)
    if require_proximity and not uf_ok:
        breakdown = ScoreBreakdown(
            cnae=cnae_pts,
            geography=0.0,
            total=0.0,
            explanations=explanations + ["Proximidade obrigatória: UF incompatível → score 0"],
            recommendation="SKIP",
        )
        return breakdown

    porte_pts, porte_notes = _score_porte(tender, company)
    explanations.extend(porte_notes)

    economic_pts, economic_notes = _score_economic(tender, company)
    explanations.extend(economic_notes)

    deadline_pts, deadline_notes = _score_deadline(tender, today=today)
    explanations.extend(deadline_notes)

    total = cnae_pts + geo_pts + porte_pts + economic_pts + deadline_pts

    exclusivo = _is_exclusivo(tender)
    porte = PORTE_MAP.get(str(company.get("porte") or "").upper(), CompanySize.NAO_INFORMADO)
    if exclusivo and porte not in {CompanySize.ME, CompanySize.EPP}:
        # Mantém compatibilidade com penalização forte de Demais em lote exclusivo
        total = min(total * 0.3, 35.0)
        explanations.append(
            f"Penalização: porte {porte.value} em lote exclusivo ME/EPP (LC 123) → teto {total:.1f}"
        )
        hard_fail = True

    if hard_fail and total >= REVIEW_THRESHOLD:
        total = min(total * 0.25, 35.0)
        explanations.append(f"Elegibilidade hard-fail → score ajustado para {total:.1f}")

    total = min(round(total, 1), 100.0)
    rec = recommend(total, hard_fail=hard_fail)
    explanations.append(f"Recomendação {rec} (score {total:.1f})")

    return ScoreBreakdown(
        cnae=cnae_pts,
        geography=geo_pts,
        porte=porte_pts,
        economic=economic_pts,
        deadline=deadline_pts,
        total=total,
        explanations=explanations,
        recommendation=rec,
    )


def matching_score(
    *,
    tender: dict[str, Any],
    company: dict[str, Any],
    require_proximity: bool = False,
) -> float:
    """Compat: retorna apenas o total 0–100."""
    return score_match(
        tender=tender,
        company=company,
        require_proximity=require_proximity,
    ).total


def _company_cnaes(company: dict[str, Any]) -> set[str]:
    codes = {str(company.get("cnae_fiscal") or "")}
    for extra in company.get("cnaes_secundarios") or []:
        codes.add(str(extra.get("codigo") or extra))
    return {code for code in codes if code and code != "None"}


def _norm(value: Any) -> str:
    return str(value or "").strip().upper()


def _is_exclusivo(tender: dict[str, Any]) -> bool:
    if tender.get("exclusivo_me_epp"):
        return True
    beneficios = tender.get("beneficios_me_epp") or {}
    return bool(isinstance(beneficios, dict) and beneficios.get("exclusivo_me_epp"))


def _score_cnae(tender: dict[str, Any], company: dict[str, Any]) -> tuple[float, list[str]]:
    tender_cnaes = {str(code) for code in tender.get("cnaes_compativeis") or []}
    company_cnaes = _company_cnaes(company)
    if tender_cnaes and company_cnaes & tender_cnaes:
        overlap = sorted(company_cnaes & tender_cnaes)
        return WEIGHT_CNAE, [f"CNAE compatível (+{WEIGHT_CNAE:.0f}): {', '.join(overlap[:4])}"]
    if not tender_cnaes:
        pts = 12.0
        return pts, [f"Sem CNAE no edital — pontuação parcial (+{pts:.0f})"]
    return 0.0, ["Sem sobreposição de CNAE (+0)"]


def _score_geography(
    tender: dict[str, Any],
    company: dict[str, Any],
    require_proximity: bool,
) -> tuple[float, list[str], bool]:
    notes: list[str] = []
    tender_uf = _norm(tender.get("uf"))
    company_uf = _norm(company.get("uf"))
    uf_ok = bool(tender_uf and tender_uf == company_uf)
    if not tender_uf:
        return 8.0, ["UF do órgão ausente — geo parcial (+8)"], True
    if not uf_ok:
        if require_proximity:
            return 0.0, [f"UF incompatível ({company_uf} ≠ {tender_uf})"], False
        return 0.0, [f"UF diferente ({company_uf} ≠ {tender_uf}) (+0)"], False

    pts = 12.0
    notes.append(f"Mesma UF {company_uf} (+12)")
    if _norm(tender.get("municipio")) and _norm(tender.get("municipio")) == _norm(company.get("municipio")):
        pts += 8.0
        notes.append(f"Mesmo município (+8)")
    else:
        notes.append("Município diferente ou ausente (+0 município)")
    return pts, notes, True


def _score_porte(tender: dict[str, Any], company: dict[str, Any]) -> tuple[float, list[str]]:
    porte = PORTE_MAP.get(str(company.get("porte") or "").upper(), CompanySize.NAO_INFORMADO)
    exclusivo = _is_exclusivo(tender)
    beneficios = tender.get("beneficios_me_epp") or {}
    if exclusivo:
        if porte in {CompanySize.ME, CompanySize.EPP}:
            return WEIGHT_PORTE, [f"Porte {porte.value} compatível com exclusividade LC 123 (+{WEIGHT_PORTE:.0f})"]
        return 0.0, [f"Porte {porte.value} incompatível com lote exclusivo ME/EPP (+0)"]

    pts = 10.0
    notes = [f"Lote não exclusivo — base porte (+10)"]
    if isinstance(beneficios, dict) and beneficios.get("cota_reservada_25"):
        if porte in {CompanySize.ME, CompanySize.EPP}:
            pts += 5.0
            notes.append("Cota reservada 25% + ME/EPP (+5)")
    return pts, notes


def _score_economic(tender: dict[str, Any], company: dict[str, Any]) -> tuple[float, list[str]]:
    porte = PORTE_MAP.get(str(company.get("porte") or "").upper(), CompanySize.NAO_INFORMADO)
    valor = float(tender.get("valor_total_estimado") or 0)
    if valor <= 0:
        return 8.0, ["Valor estimado ausente — fit econômico neutro (+8)"]

    if valor <= LC123_VALOR_EXCLUSIVO_ME_EPP:
        if porte in {CompanySize.ME, CompanySize.EPP}:
            return WEIGHT_ECONOMIC, [
                f"Valor R$ {valor:,.0f} na faixa LC 123 e porte ME/EPP (+{WEIGHT_ECONOMIC:.0f})"
            ]
        return 5.0, [f"Valor na faixa LC 123 mas porte {porte.value} (+5)"]

    # Contratações maiores: ME/EPP ainda podem participar (salvo exclusividade já tratada)
    if porte in {CompanySize.ME, CompanySize.EPP}:
        return 12.0, [f"Valor R$ {valor:,.0f} acima da faixa exclusiva — ME/EPP viável (+12)"]
    return 13.0, [f"Valor R$ {valor:,.0f} compatível com porte {porte.value} (+13)"]


def _as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _score_deadline(tender: dict[str, Any], *, today: date) -> tuple[float, list[str]]:
    abertura = _as_date(tender.get("data_abertura_propostas") or tender.get("data_abertura_certame"))
    encerramento = _as_date(tender.get("data_encerramento_propostas"))

    if encerramento and encerramento < today:
        return 0.0, [f"Prazo de propostas encerrado em {encerramento.isoformat()} (+0)"]

    ref = encerramento or abertura
    if ref is None:
        return 10.0, ["Datas de prazo ausentes — deadline neutro (+10)"]

    days = (ref - today).days
    if days < 0:
        return 3.0, [f"Referência de prazo {ref.isoformat()} no passado (+3)"]

    notes: list[str] = []
    if abertura:
        limite_164 = prazo_impugnacao_art_164(abertura)
        if today <= limite_164 and is_business_day(today):
            notes.append(f"Dentro da janela Art. 164 (limite {limite_164.isoformat()})")
        elif today > limite_164:
            notes.append(f"Janela Art. 164 encerrada (limite era {limite_164.isoformat()})")

    if days >= 7:
        pts = WEIGHT_DEADLINE
        notes.append(f"{days} dias até o prazo — folga adequada (+{pts:.0f})")
        return pts, notes
    if days >= 3:
        pts = 11.0
        notes.append(f"{days} dias até o prazo (+{pts:.0f})")
        return pts, notes
    if days >= 1:
        pts = 7.0
        notes.append(f"Prazo apertado ({days} dia(s)) (+{pts:.0f})")
        return pts, notes
    pts = 4.0
    notes.append("Prazo no mesmo dia (+4)")
    return pts, notes
