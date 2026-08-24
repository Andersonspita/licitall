from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.config.settings import ROOT_DIR

LEGAL_DATA_DIR = ROOT_DIR / "data" / "legal"


@dataclass(frozen=True)
class LegalChunk:
    chunk_id: str
    source: str  # lei_14133 | tcu
    titulo: str
    texto: str
    fundamentacao: str


_HEADING_RE = re.compile(r"^##\s+(.+)$", re.M)


def load_markdown_chunks(path: Path, source: str) -> list[LegalChunk]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    parts = _HEADING_RE.split(text)
    # parts: [preamble, title1, body1, title2, body2, ...]
    chunks: list[LegalChunk] = []
    if len(parts) < 3:
        if text.strip():
            chunks.append(
                LegalChunk(
                    chunk_id=f"{source}:full",
                    source=source,
                    titulo=path.stem,
                    texto=text.strip(),
                    fundamentacao=path.name,
                )
            )
        return chunks

    for idx in range(1, len(parts), 2):
        title = parts[idx].strip()
        body = parts[idx + 1].strip() if idx + 1 < len(parts) else ""
        if len(body) < 40:
            continue
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower()[:80]
        fund = title
        art = re.search(r"Art\.\s*\d+", title, re.I)
        if art:
            fund = f"{art.group(0)} da Lei nº 14.133/2021" if source == "lei_14133" else title
        chunks.append(
            LegalChunk(
                chunk_id=f"{source}:{slug}",
                source=source,
                titulo=title,
                texto=body,
                fundamentacao=fund,
            )
        )
    return chunks


def load_legal_corpus() -> list[LegalChunk]:
    chunks: list[LegalChunk] = []
    chunks.extend(load_markdown_chunks(LEGAL_DATA_DIR / "lei_14133" / "corpus.md", "lei_14133"))
    chunks.extend(load_markdown_chunks(LEGAL_DATA_DIR / "tcu" / "orientacoes_seed.md", "tcu"))
    return chunks
