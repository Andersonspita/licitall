from __future__ import annotations

from pathlib import Path

from src.advisory.generator import DISCLAIMER_OAB, render_minuta
from src.advisory.kit import CompanyContext, DocumentKit, build_document_kit
from src.config import get_settings
from src.ingestion.client import parse_id_pncp

__all__ = [
    "DISCLAIMER_OAB",
    "CompanyContext",
    "DocumentKit",
    "build_document_kit",
    "render_minuta",
    "persist_kit",
]


def persist_kit(kit: DocumentKit) -> list[str]:
    """Salva minutas em data/raw/{slug}/_kit/."""
    settings = get_settings()
    parsed = parse_id_pncp(kit.id_pncp)
    out_dir = settings.raw_docs_path / parsed.slug / "_kit"
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for name, content in kit.minutas.items():
        path = out_dir / f"{name}.md"
        path.write_text(content, encoding="utf-8")
        saved.append(str(path))
    meta = out_dir / "kit_meta.txt"
    meta.write_text(
        "\n".join([kit.marco_legal, kit.disclaimer, *kit.avisos]),
        encoding="utf-8",
    )
    saved.append(str(meta))
    return saved
