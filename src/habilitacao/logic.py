"""Regras puras de habilitação: situação das certidões e validação de dados."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

BRT = timezone(timedelta(hours=-3), "BRT")
AVISO_PADRAO = 15
MAX_CERTIDOES = 200
MAX_ATESTADOS = 2000

CERTIDOES_PADRAO = (
    "SICAF — cadastro e regularidade",
    "CND Federal (Receita/PGFN)",
    "CND Estadual",
    "CND Municipal",
    "CRF — FGTS",
    "CNDT — Débitos Trabalhistas",
    "Certidão negativa de falência / recuperação judicial",
)


def hoje_brt(now: datetime | None = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(BRT).date()


def situacao_certidao(validade: date | None, hoje: date, aviso_dias: int = AVISO_PADRAO) -> dict[str, Any]:
    """`situacao`: sem_data | vencida | vence_em_breve | valida. `dias`: dias até o vencimento (negativo = vencida)."""
    if validade is None:
        return {"situacao": "sem_data", "dias": None}
    dias = (validade - hoje).days
    if dias < 0:
        return {"situacao": "vencida", "dias": dias}
    if dias <= max(1, aviso_dias):
        return {"situacao": "vence_em_breve", "dias": dias}
    return {"situacao": "valida", "dias": dias}


def validar_validade(validade: date | None, hoje: date) -> None:
    if validade is None:
        return
    if validade < date(1990, 1, 1) or validade > hoje + timedelta(days=366 * 20):
        raise ValueError("Data de validade fora do intervalo plausível.")


def validar_data_emissao(emissao: date | None, hoje: date) -> None:
    if emissao is None:
        return
    if emissao < date(1950, 1, 1) or emissao > hoje + timedelta(days=1):
        raise ValueError("Data de emissão inválida.")


def validar_quantidade(q: float | None) -> None:
    if q is None:
        return
    if not math.isfinite(q) or q < 0 or q > 1e12:
        raise ValueError("Quantidade inválida.")


def limpar(texto: str | None) -> str | None:
    """Remove espaços das pontas; vazio vira None."""
    t = " ".join((texto or "").split())
    return t or None
