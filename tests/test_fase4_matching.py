"""Testes Fase 4+ — score explicável, elegibilidade YAML, match inverso."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.matching.cnae_map import infer_cnaes_from_text
from src.matching.eligibility import evaluate_eligibility, load_eligibility_config
from src.matching.scoring import matching_score, recommend, score_match
from src.matching.service import MatchmakingService, resolve_cnaes, resolve_exclusivo_me_epp


def test_infer_cnaes_ti():
    codes = infer_cnaes_from_text("Contratação de desenvolvimento de software e suporte de TI")
    assert "6201501" in codes or "6204000" in codes


def test_score_cnae_uf_me_epp():
    tender = {
        "cnaes_compativeis": ["6204000"],
        "uf": "DF",
        "municipio": "BRASILIA",
        "exclusivo_me_epp": True,
        "valor_total_estimado": 50000,
        "data_encerramento_propostas": (date.today() + timedelta(days=10)).isoformat(),
    }
    company = {
        "cnae_fiscal": 6204000,
        "cnaes_secundarios": [],
        "uf": "DF",
        "municipio": "BRASILIA",
        "porte": "MICRO EMPRESA",
        "situacao_cadastral": 2,
        "descricao_situacao_cadastral": "ATIVA",
    }
    breakdown = score_match(tender=tender, company=company)
    assert breakdown.total >= 85
    assert breakdown.recommendation == "BID"
    assert breakdown.as_factors()["cnae"] == 35.0


def test_score_penalizes_demais_on_exclusive_lot():
    tender = {
        "cnaes_compativeis": ["6204000"],
        "uf": "DF",
        "exclusivo_me_epp": True,
    }
    company = {
        "cnae_fiscal": 6204000,
        "uf": "DF",
        "porte": "DEMAIS",
        "situacao_cadastral": 2,
        "descricao_situacao_cadastral": "ATIVA",
    }
    score = matching_score(tender=tender, company=company)
    assert score < 50
    assert recommend(score, hard_fail=True) == "SKIP"


def test_score_breakdown_has_five_factors():
    tender = {
        "cnaes_compativeis": ["8121400"],
        "uf": "SP",
        "municipio": "SAO PAULO",
        "valor_total_estimado": 40000,
        "exclusivo_me_epp": True,
        "data_abertura_propostas": (date.today() + timedelta(days=14)).isoformat(),
        "data_encerramento_propostas": (date.today() + timedelta(days=20)).isoformat(),
    }
    company = {
        "cnae_fiscal": 8121400,
        "uf": "SP",
        "municipio": "SAO PAULO",
        "porte": "MICRO EMPRESA",
        "situacao_cadastral": 2,
        "descricao_situacao_cadastral": "ATIVA",
    }
    breakdown = score_match(tender=tender, company=company)
    factors = breakdown.as_factors()
    assert set(factors) == {"cnae", "geography", "porte", "economic", "deadline"}
    assert sum(factors.values()) == pytest.approx(breakdown.total, abs=0.2)


def test_resolve_cnaes_merges_objeto():
    tender = {"objeto_resumido": "serviços de limpeza predial", "cnaes_compativeis": []}
    assert "8121400" in resolve_cnaes(tender)


def test_resolve_exclusivo_from_beneficios():
    tender = {"beneficios_me_epp": {"exclusivo_me_epp": True}}
    assert resolve_exclusivo_me_epp(tender) is True


def test_eligibility_yaml_loads_and_hard_fails_demais():
    cfg = load_eligibility_config()
    assert cfg["version"] == 1
    assert any(r["id"] == "lote_exclusivo_me_epp" for r in cfg["rules"])

    verdict = evaluate_eligibility(
        tender={"exclusivo_me_epp": True, "uf": "SP"},
        company={
            "porte": "DEMAIS",
            "situacao_cadastral": 2,
            "descricao_situacao_cadastral": "ATIVA",
            "uf": "SP",
        },
    )
    assert verdict.eligible is False
    assert any("exclusivo" in f.lower() or "ME/EPP" in f for f in verdict.hard_failures)


def test_eligibility_art_164_soft_warning():
    abertura = date.today() + timedelta(days=1)
    verdict = evaluate_eligibility(
        tender={
            "uf": "SP",
            "data_abertura_propostas": abertura.isoformat(),
            "data_encerramento_propostas": (date.today() + timedelta(days=5)).isoformat(),
        },
        company={
            "porte": "MICRO EMPRESA",
            "situacao_cadastral": 2,
            "descricao_situacao_cadastral": "ATIVA",
            "uf": "SP",
        },
        today=date.today(),
    )
    assert verdict.eligible is True
    assert any("Art. 164" in w or "164" in w for w in verdict.soft_warnings) or any(
        "lead" in r for r in verdict.rules_applied
    )


@pytest.mark.asyncio
async def test_matchmaking_with_stub_client():
    class StubClient:
        async def search_active(self, **kwargs):
            return [
                {
                    "cnpj": "12345678000199",
                    "razao_social": "LIMPEZA ME LTDA",
                    "uf": "SP",
                    "municipio": "SAO PAULO",
                    "porte": "MICRO EMPRESA",
                    "cnae_fiscal": 8121400,
                    "cnaes_secundarios": [],
                    "situacao_cadastral": 2,
                    "descricao_situacao_cadastral": "ATIVA",
                },
                {
                    "cnpj": "99888777000111",
                    "razao_social": "INATIVA SA",
                    "uf": "SP",
                    "porte": "DEMAIS",
                    "cnae_fiscal": 8121400,
                    "situacao_cadastral": 8,
                    "descricao_situacao_cadastral": "BAIXADA",
                },
            ]

        async def aclose(self):
            return None

    service = MatchmakingService(client=StubClient())  # type: ignore[arg-type]
    result = await service.match_tender(
        {
            "id_pncp": "00000000000000-1-000001/2026",
            "objeto_resumido": "serviços de limpeza",
            "uf": "SP",
            "municipio": "SAO PAULO",
            "beneficios_me_epp": {"exclusivo_me_epp": True},
            "valor_total_estimado": 40000,
            "data_encerramento_propostas": (date.today() + timedelta(days=12)).isoformat(),
        },
        min_score=40,
    )
    assert result.total_candidatos == 2
    assert len(result.matches) == 1
    assert result.matches[0].cnpj == "12345678000199"
    assert result.exclusivo_me_epp is True
    assert result.matches[0].recommendation in {"BID", "REVIEW"}
    assert result.matches[0].factors.cnae > 0


@pytest.mark.asyncio
async def test_match_company_inverse():
    class StubClient:
        async def get_company(self, cnpj: str):
            return {
                "cnpj": "12345678000199",
                "razao_social": "LIMPEZA ME LTDA",
                "uf": "SP",
                "municipio": "SAO PAULO",
                "porte": "MICRO EMPRESA",
                "cnae_fiscal": 8121400,
                "cnaes_secundarios": [],
                "situacao_cadastral": 2,
                "descricao_situacao_cadastral": "ATIVA",
            }

        async def aclose(self):
            return None

    service = MatchmakingService(client=StubClient())  # type: ignore[arg-type]
    tenders = [
        {
            "id_pncp": "00000000000000-1-000001/2026",
            "orgao_comprador": "PREFEITURA SP",
            "objeto_resumido": "serviços de limpeza predial",
            "uf": "SP",
            "municipio": "SAO PAULO",
            "valor_total_estimado": 35000,
            "beneficios_me_epp": {"exclusivo_me_epp": True},
            "data_encerramento_propostas": (date.today() + timedelta(days=15)).isoformat(),
        },
        {
            "id_pncp": "00000000000000-1-000002/2026",
            "orgao_comprador": "ORGAO TI",
            "objeto_resumido": "desenvolvimento de software sob demanda",
            "uf": "RJ",
            "valor_total_estimado": 200000,
            "data_encerramento_propostas": (date.today() + timedelta(days=20)).isoformat(),
        },
    ]
    result = await service.match_company(
        "12345678000199",
        tenders=tenders,
        min_score=30,
    )
    assert result.cnpj == "12345678000199"
    assert result.total_avaliados == 2
    assert len(result.opportunities) >= 1
    assert result.opportunities[0].id_pncp == "00000000000000-1-000001/2026"
    assert result.opportunities[0].recommendation in {"BID", "REVIEW"}
