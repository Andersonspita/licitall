"""Anexos do edital — mapeamento de arquivos do PNCP."""

from __future__ import annotations

from src.ingestion.service import map_attachment_row


def test_mapeia_campos_do_pncp():
    row = map_attachment_row(
        {"titulo": " Edital.pdf ", "tipoDocumentoNome": "Edital", "url": " https://pncp.gov.br/a/1 "},
        "00000000000191-1-000001/2026",
    )
    assert row["titulo"] == "Edital.pdf"
    assert row["tipo_documento"] == "Edital"
    assert row["url_download"] == "https://pncp.gov.br/a/1"
    assert row["id_pncp"] == "00000000000191-1-000001/2026"


def test_aceita_chaves_alternativas_de_url():
    assert map_attachment_row({"uri": "https://x/1"}, "a")["url_download"] == "https://x/1"
    assert map_attachment_row({"urlDocumento": "https://x/2"}, "a")["url_download"] == "https://x/2"


def test_ignora_arquivo_sem_url():
    assert map_attachment_row({"titulo": "sem link"}, "a") is None
    assert map_attachment_row({"url": "   "}, "a") is None


def test_campos_opcionais_ficam_nulos():
    row = map_attachment_row({"url": "https://x/3"}, "a")
    assert row["titulo"] is None and row["tipo_documento"] is None


def test_rotas_de_anexos_registradas():
    from src.main import app

    paths = {(r.path, tuple(sorted(r.methods))) for r in app.routes if hasattr(r, "methods")}
    assert ("/ingestion/pncp/{id_pncp:path}/anexos", ("GET",)) in paths
    assert ("/ingestion/pncp/{id_pncp:path}/anexos/hydrate", ("POST",)) in paths
