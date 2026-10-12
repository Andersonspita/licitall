"""Regressão: o detalhe do edital quebrava (503) porque DocumentStorage recebia um Path."""

from __future__ import annotations

from src.config import get_settings
from src.tenders.service import filesystem_hints


def test_filesystem_hints_nao_levanta_excecao(tmp_path, monkeypatch):
    monkeypatch.setenv("RAW_DOCS_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        hints = filesystem_hints("00394411000109-1-000181/2026")
    finally:
        get_settings.cache_clear()
    assert hints["has_docs"] is False and hints["doc_count"] == 0
    assert hints["files"] == [] and hints["has_parsed"] is False and hints["has_kit"] is False


def test_filesystem_hints_lista_arquivos_gravados(tmp_path, monkeypatch):
    monkeypatch.setenv("RAW_DOCS_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        from src.ingestion.storage import DocumentStorage

        d = DocumentStorage().tender_dir("00394411000109-1-000181/2026")
        (d / "edital.pdf").write_bytes(b"%PDF-1.4")
        hints = filesystem_hints("00394411000109-1-000181/2026")
    finally:
        get_settings.cache_clear()
    assert hints["has_docs"] is True and hints["files"] == ["edital.pdf"]
