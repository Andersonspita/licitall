from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

EDITAL_SECTIONS = (
    "Objeto",
    "Habilitação Fiscal/Trabalhista",
    "Qualificação Técnica",
    "Critérios de Julgamento",
    "Minuta do Contrato",
)


@dataclass
class ParsedDocument:
    source_path: Path
    markdown: str
    sections: dict[str, str] = field(default_factory=dict)


class DoclingParser:
    """Wrapper do DS4SD Docling. Não altera o repositório de referência."""

    def __init__(self) -> None:
        self._converter = None

    def _load(self):
        if self._converter is None:
            from docling.document_converter import DocumentConverter

            self._converter = DocumentConverter()
        return self._converter

    def convert(self, path: str | Path) -> ParsedDocument:
        source = Path(path)
        result = self._load().convert(str(source))
        markdown = result.document.export_to_markdown()
        return ParsedDocument(
            source_path=source,
            markdown=markdown,
            sections=_split_sections(markdown),
        )


def _split_sections(markdown: str) -> dict[str, str]:
    """Segmentação preliminar por headings; refinada na Fase 2."""
    sections: dict[str, str] = {}
    current = "preambulo"
    chunks: list[str] = []
    for line in markdown.splitlines():
        heading = line.lstrip("# ").strip()
        matched = next((name for name in EDITAL_SECTIONS if name.lower() in heading.lower()), None)
        if matched and line.startswith("#"):
            sections[current] = "\n".join(chunks).strip()
            current = matched
            chunks = [line]
        else:
            chunks.append(line)
    sections[current] = "\n".join(chunks).strip()
    return {key: value for key, value in sections.items() if value}
