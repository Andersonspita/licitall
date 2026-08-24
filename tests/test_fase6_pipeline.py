"""Testes Fase 6 — pipeline orquestrado e health de dependências."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.advisory.kit import CompanyContext
from src.pipeline.orchestrator import run_full_pipeline


@pytest.mark.asyncio
async def test_run_full_pipeline_with_existing_files(tmp_path, monkeypatch):
    from src.config import get_settings

    monkeypatch.setenv("RAW_DOCS_DIR", str(tmp_path / "raw"))
    get_settings.cache_clear()

    tender_dir = tmp_path / "raw" / "00000000000000-1-000001_2026"
    tender_dir.mkdir(parents=True)
    (tender_dir / "edital.pdf").write_bytes(b"%PDF-1.4 smoke")

    id_pncp = "00000000000000-1-000001/2026"
    fake_extract = {
        "extraction": {
            "tender": {
                "id_pncp": id_pncp,
                "orgao_comprador": "ORGAO TESTE",
                "cnpj_orgao": "00000000000000",
                "uf": "SP",
                "municipio": "SAO PAULO",
                "modalidade": "PREGAO_ELETRONICO",
                "objeto_resumido": "Objeto smoke",
                "valor_total_estimado": 50000,
            }
        },
        "checklist": ["Certidão FGTS"],
    }

    with (
        patch("src.pipeline.orchestrator.ensure_legal_index", new=AsyncMock(return_value=1)),
        patch("src.pipeline.orchestrator.TenderPipeline") as pipeline_cls,
        patch("src.pipeline.orchestrator.MatchmakingService") as matcher_cls,
        patch("src.pipeline.orchestrator.OutreachService") as outreach_cls,
    ):
        pipeline = pipeline_cls.return_value
        pipeline.run = AsyncMock(return_value=fake_extract)

        matcher = matcher_cls.return_value
        matcher.match_tender = AsyncMock(
            return_value=MagicMock(
                model_dump=lambda mode="json": {"matches": [], "avisos": []},
                avisos=[],
            )
        )
        matcher.aclose = AsyncMock()

        outreach = outreach_cls.return_value
        outreach.build_message = MagicMock(return_value="preview whatsapp")
        outreach.notify_opportunity = AsyncMock()
        outreach.aclose = AsyncMock()

        result = await run_full_pipeline(
            id_pncp,
            company=CompanyContext(razao_social="Empresa Smoke LTDA", cnpj="12345678000199"),
            download_if_missing=False,
            save_kit=False,
            run_matching=True,
        )

    assert result.id_pncp == id_pncp
    assert result.extraction == fake_extract
    assert result.whatsapp_preview == "preview whatsapp"
    assert result.kit.minutas


@pytest.mark.asyncio
async def test_check_dependencies_structure():
    from src.infra.health import check_dependencies

    report = await check_dependencies()
    assert "summary" in report
    assert "services" in report
    assert isinstance(report["services"], list)
    names = {s.get("service") for s in report["services"]}
    assert {"postgres", "redis", "minha_receita", "evolution_api"} <= names
