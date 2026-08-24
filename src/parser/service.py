from __future__ import annotations

from pathlib import Path

from src.ingestion.client import PncpId, parse_id_pncp
from src.ingestion.storage import DocumentStorage
from src.parser.docling_parser import DoclingParser, ParsedDocument, dump_parsed

PARSEABLE = {".pdf", ".docx", ".html", ".htm", ".md", ".txt"}


class ParserService:
    def __init__(
        self,
        storage: DocumentStorage | None = None,
        parser: DoclingParser | None = None,
    ) -> None:
        self.storage = storage or DocumentStorage()
        self.parser = parser or DoclingParser()

    def list_parseable(self, id_pncp: str | PncpId) -> list[Path]:
        return [
            path
            for path in self.storage.list_files(id_pncp)
            if path.suffix.lower() in PARSEABLE
        ]

    def parse_file(self, path: Path, *, persist: bool = True) -> ParsedDocument:
        parsed = self.parser.convert(path)
        if persist:
            out_dir = path.parent / "_parsed"
            dump_parsed(parsed, out_dir / f"{path.stem}.meta.json")
        return parsed

    def parse_tender(self, id_pncp: str, *, persist: bool = True) -> list[ParsedDocument]:
        parse_id_pncp(id_pncp)  # valida formato
        results: list[ParsedDocument] = []
        for path in self.list_parseable(id_pncp):
            results.append(self.parse_file(path, persist=persist))
        return results
