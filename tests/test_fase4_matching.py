"""Testes Fase 4 — matchmaking CNAE / geo / porte (LC 123)."""

from __future__ import annotations

import pytest

from src.matching.cnae_map import infer_cnaes_from_text
from src.matching.scoring import matching_score
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
    }
    company = {
        "cnae_fiscal": 6204000,
        "cnaes_secundarios": [],
        "uf": "DF",
        "municipio": "BRASILIA",
        "porte": "MICRO EMPRESA",
        "situacao_cadastral": 2,
    }
    score = matching_score(tender=tender, company=company)
    assert score >= 85


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
    }
    score = matching_score(tender=tender, company=company)
    assert score < 50


def test_resolve_cnaes_merges_objeto():
    tender = {"objeto_resumido": "serviços de limpeza predial", "cnaes_compativeis": []}
    assert "8121400" in resolve_cnaes(tender)


def test_resolve_exclusivo_from_beneficios():
    tender = {"beneficios_me_epp": {"exclusivo_me_epp": True}}
    assert resolve_exclusivo_me_epp(tender) is True


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
        },
        min_score=40,
    )
    assert result.total_candidatos == 2
    assert len(result.matches) == 1
    assert result.matches[0].cnpj == "12345678000199"
    assert result.exclusivo_me_epp is True
