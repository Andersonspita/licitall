"""Motor de elegibilidade declarativo (YAML) — hard fail vs soft warning."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from src.compliance.lei_14133 import prazo_impugnacao_art_164
from src.matching.client import PORTE_MAP, SITUACAO_ATIVA
from src.matching.scoring import BID_THRESHOLD, REVIEW_THRESHOLD
from src.models.enums import CompanySize

_RULES_PATH = Path(__file__).with_name("eligibility_rules.yaml")


@dataclass
class EligibilityVerdict:
    eligible: bool = True
    hard_failures: list[str] = field(default_factory=list)
    soft_warnings: list[str] = field(default_factory=list)
    rules_applied: list[str] = field(default_factory=list)
    thresholds: dict[str, float] = field(
        default_factory=lambda: {"bid": BID_THRESHOLD, "review": REVIEW_THRESHOLD}
    )


@lru_cache(maxsize=1)
def load_eligibility_config(path: str | None = None) -> dict[str, Any]:
    rules_file = Path(path) if path else _RULES_PATH
    with rules_file.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        return {}
    return data


def evaluate_eligibility(
    *,
    tender: dict[str, Any],
    company: dict[str, Any],
    require_proximity: bool = False,
    today: date | None = None,
    config: dict[str, Any] | None = None,
) -> EligibilityVerdict:
    """Avalia regras YAML. Hard failures → inelegível; soft → avisos."""
    cfg = config if config is not None else load_eligibility_config()
    today = today or datetime.now(timezone.utc).date()
    thresholds = dict(cfg.get("thresholds") or {})
    thresholds.setdefault("bid", BID_THRESHOLD)
    thresholds.setdefault("review", REVIEW_THRESHOLD)

    verdict = EligibilityVerdict(thresholds={k: float(v) for k, v in thresholds.items()})
    rules = cfg.get("rules") or []
    rule_index = {str(rule.get("id")): rule for rule in rules if isinstance(rule, dict)}

    def _apply(rule_id: str, *, failed: bool, detail: str) -> None:
        rule = rule_index.get(rule_id) or {"id": rule_id, "severity": "soft"}
        severity = str(rule.get("severity") or "soft").lower()
        verdict.rules_applied.append(rule_id)
        if not failed:
            return
        description = str(rule.get("description") or rule_id)
        message = f"{description} — {detail}"
        if severity == "hard":
            verdict.eligible = False
            verdict.hard_failures.append(message)
        else:
            verdict.soft_warnings.append(message)

    # empresa_ativa
    active = (
        company.get("situacao_cadastral") == SITUACAO_ATIVA
        or str(company.get("descricao_situacao_cadastral") or "").upper() == "ATIVA"
    )
    _apply(
        "empresa_ativa",
        failed=not active,
        detail=str(company.get("descricao_situacao_cadastral") or company.get("situacao_cadastral") or "desconhecida"),
    )

    # lote_exclusivo_me_epp
    exclusivo = bool(tender.get("exclusivo_me_epp"))
    beneficios = tender.get("beneficios_me_epp") or {}
    if isinstance(beneficios, dict) and beneficios.get("exclusivo_me_epp"):
        exclusivo = True
    porte = PORTE_MAP.get(str(company.get("porte") or "").upper(), CompanySize.NAO_INFORMADO)
    if exclusivo:
        _apply(
            "lote_exclusivo_me_epp",
            failed=porte not in {CompanySize.ME, CompanySize.EPP},
            detail=f"porte={porte.value}",
        )

    # proximidade_obrigatoria
    if require_proximity:
        tender_uf = str(tender.get("uf") or "").upper()
        company_uf = str(company.get("uf") or "").upper()
        _apply(
            "proximidade_obrigatoria",
            failed=bool(tender_uf) and tender_uf != company_uf,
            detail=f"{company_uf or '?'} ≠ {tender_uf or '?'}",
        )

    abertura = _as_date(tender.get("data_abertura_propostas") or tender.get("data_abertura_certame"))
    encerramento = _as_date(tender.get("data_encerramento_propostas"))

    # prazo_propostas_aberto
    if encerramento is not None:
        _apply(
            "prazo_propostas_aberto",
            failed=encerramento < today,
            detail=f"encerrado em {encerramento.isoformat()}",
        )

    # art_164_janela
    if abertura is not None:
        limite = prazo_impugnacao_art_164(abertura)
        _apply(
            "art_164_janela",
            failed=today > limite,
            detail=f"limite Art. 164 era {limite.isoformat()} (abertura {abertura.isoformat()})",
        )

    # lead_minimo_dias
    lead_rule = rule_index.get("lead_minimo_dias") or {}
    min_days = int((lead_rule.get("params") or {}).get("min_calendar_days") or 2)
    ref = encerramento or abertura
    if ref is not None:
        remaining = (ref - today).days
        _apply(
            "lead_minimo_dias",
            failed=remaining < min_days,
            detail=f"{remaining} dia(s) restantes (mínimo {min_days})",
        )

    return verdict


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
