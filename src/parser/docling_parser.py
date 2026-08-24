from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.models.schemas import DocumentRef
from src.parser.sections import EDITAL_SECTION_SPECS, classify_heading

logger = logging.getLogger("licitall.parser")

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".html", ".htm", ".md", ".txt"}


@dataclass
class ParsedDocument:
    source_path: Path
    markdown: str
    sections: dict[str, str] = field(default_factory=dict)
    refs: list[DocumentRef] = field(default_factory=list)
    engine: str = "docling"
    meta: dict[str, Any] = field(default_factory=dict)

    def section_markdown(self, key: str) -> str:
        return self.sections.get(key, "")


class DoclingParser:
    """Wrapper do Docling com segmentação alinhada à Lei 14.133/2021.

    Não modifica o código-fonte do repositório DS4SD.Docling local.
    Se o pacote `docling` não estiver instalado, usa fallback de texto/Markdown.
    """

    def __init__(self) -> None:
        self._converter = None
        self._docling_available: bool | None = None

    @property
    def docling_available(self) -> bool:
        if self._docling_available is None:
            try:
                import docling  # noqa: F401

                self._docling_available = True
            except ImportError:
                self._docling_available = False
        return self._docling_available

    def _load(self):
        if self._converter is None:
            from docling.document_converter import DocumentConverter

            self._converter = DocumentConverter()
        return self._converter

    def convert(self, path: str | Path) -> ParsedDocument:
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(f"Documento não encontrado: {source}")

        if source.suffix.lower() in {".md", ".txt"}:
            markdown = source.read_text(encoding="utf-8", errors="ignore")
            return ParsedDocument(
                source_path=source,
                markdown=markdown,
                sections=split_sections(markdown),
                refs=refs_from_markdown(markdown),
                engine="plaintext",
            )

        if self.docling_available:
            try:
                return self._convert_docling(source)
            except Exception as exc:
                logger.warning("Docling falhou em %s: %s — usando fallback", source.name, exc)

        return self._convert_fallback(source)

    def _convert_docling(self, source: Path) -> ParsedDocument:
        result = self._load().convert(str(source))
        document = result.document
        markdown = document.export_to_markdown()
        refs = _refs_from_docling_document(document)
        if not refs:
            refs = refs_from_markdown(markdown)
        return ParsedDocument(
            source_path=source,
            markdown=markdown,
            sections=split_sections(markdown),
            refs=refs,
            engine="docling",
            meta={"pages": _guess_page_count(refs)},
        )

    def _convert_fallback(self, source: Path) -> ParsedDocument:
        """Fallback mínimo: extrai texto bruto de PDF via pypdfium2 se disponível."""
        text = ""
        engine = "fallback-empty"
        try:
            import pypdfium2 as pdfium

            pdf = pdfium.PdfDocument(str(source))
            parts: list[str] = []
            refs: list[DocumentRef] = []
            for index in range(len(pdf)):
                page = pdf[index]
                page_text = page.get_textpage().get_text_bounded()
                page_no = index + 1
                parts.append(f"<!-- page:{page_no} -->\n{page_text}")
                for para_idx, para in enumerate(_paragraphs(page_text), start=1):
                    refs.append(
                        DocumentRef(
                            pagina=page_no,
                            paragrafo=f"p{page_no}-{para_idx}",
                            texto=para,
                            secao=None,
                        )
                    )
            text = "\n\n".join(parts)
            engine = "pypdfium2"
            return ParsedDocument(
                source_path=source,
                markdown=text,
                sections=split_sections(text),
                refs=refs,
                engine=engine,
                meta={"pages": len(pdf)},
            )
        except Exception as exc:
            logger.warning("Fallback PDF indisponível (%s); retornando placeholder", exc)
            text = (
                f"[LicitAll] Não foi possível extrair texto de {source.name}. "
                "Instale `docling` (Fase 2) ou verifique o PDF."
            )
            return ParsedDocument(
                source_path=source,
                markdown=text,
                sections={},
                refs=[],
                engine=engine,
            )


def split_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current = "preambulo"
    chunks: list[str] = []

    for line in markdown.splitlines():
        if line.lstrip().startswith("#"):
            heading = line.lstrip("# ").strip()
            matched = classify_heading(heading)
            if matched:
                sections[current] = "\n".join(chunks).strip()
                current = matched.key
                chunks = [line]
                continue
        chunks.append(line)

    sections[current] = "\n".join(chunks).strip()

    # Também tenta classificar blocos sem heading markdown (editais OCR)
    if len(sections) <= 1:
        sections.update(_split_by_keyword_blocks(markdown))

    return {key: value for key, value in sections.items() if value}


def refs_from_markdown(markdown: str) -> list[DocumentRef]:
    refs: list[DocumentRef] = []
    current_page = 1
    current_section: str | None = None
    para_idx = 0

    for block in re.split(r"\n\s*\n", markdown):
        page_marker = re.search(r"<!--\s*page:(\d+)\s*-->", block, re.I)
        if page_marker:
            current_page = int(page_marker.group(1))
            continue
        heading_line = next((ln for ln in block.splitlines() if ln.lstrip().startswith("#")), None)
        if heading_line:
            spec = classify_heading(heading_line)
            if spec:
                current_section = spec.key
        text = block.strip()
        if len(text) < 40:
            continue
        para_idx += 1
        refs.append(
            DocumentRef(
                pagina=current_page,
                paragrafo=f"p{current_page}-{para_idx}",
                texto=text[:2000],
                secao=current_section,
            )
        )
    return refs


def _refs_from_docling_document(document: Any) -> list[DocumentRef]:
    refs: list[DocumentRef] = []
    texts = getattr(document, "texts", None) or []
    for idx, item in enumerate(texts, start=1):
        text = getattr(item, "text", None) or str(item)
        if not text or len(text.strip()) < 20:
            continue
        page = _page_from_provenance(item)
        refs.append(
            DocumentRef(
                pagina=page or 1,
                paragrafo=f"docling-{idx}",
                texto=text.strip()[:2000],
                secao=None,
            )
        )
    return refs


def _page_from_provenance(item: Any) -> int | None:
    prov = getattr(item, "prov", None) or getattr(item, "provenance", None)
    if not prov:
        return None
    first = prov[0] if isinstance(prov, (list, tuple)) and prov else prov
    page = getattr(first, "page_no", None) or getattr(first, "page", None)
    try:
        return int(page) if page is not None else None
    except (TypeError, ValueError):
        return None


def _guess_page_count(refs: list[DocumentRef]) -> int:
    if not refs:
        return 0
    return max(ref.pagina for ref in refs)


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) >= 40]


def _split_by_keyword_blocks(markdown: str) -> dict[str, str]:
    """Quando não há headings Markdown, corta por palavras-chave tipográficas."""
    lines = markdown.splitlines()
    markers: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        cleaned = re.sub(r"\s+", " ", line).strip().lower()
        if len(cleaned) > 120:
            continue
        spec = classify_heading(cleaned)
        if spec:
            markers.append((i, spec.key))
    if not markers:
        return {}
    out: dict[str, str] = {}
    for idx, (start, key) in enumerate(markers):
        end = markers[idx + 1][0] if idx + 1 < len(markers) else len(lines)
        out[key] = "\n".join(lines[start:end]).strip()
    return out


def dump_parsed(parsed: ParsedDocument, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": str(parsed.source_path),
        "engine": parsed.engine,
        "meta": parsed.meta,
        "sections": list(parsed.sections.keys()),
        "section_labels": {s.key: s.label for s in EDITAL_SECTION_SPECS},
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path = target.with_suffix(".md")
    md_path.write_text(parsed.markdown, encoding="utf-8")
    return md_path
