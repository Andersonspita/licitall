from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import aiofiles

from src.config import Settings, get_settings
from src.ingestion.client import PncpId, parse_id_pncp

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*]+')


def _safe_filename(name: str, fallback: str) -> str:
    cleaned = _UNSAFE_CHARS.sub("_", name).strip().strip(".")
    return cleaned or fallback


class DocumentStorage:
    """Persiste binários (Edital, TR, planilhas) em data/raw/{id_licitacao}."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = self.settings.raw_docs_path
        self.root.mkdir(parents=True, exist_ok=True)

    def tender_dir(self, id_pncp: str | PncpId) -> Path:
        parsed = id_pncp if isinstance(id_pncp, PncpId) else parse_id_pncp(id_pncp)
        path = self.root / parsed.slug
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def save_bytes(self, id_pncp: str | PncpId, filename: str, content: bytes) -> Path:
        directory = self.tender_dir(id_pncp)
        target = directory / _safe_filename(filename, "anexo.bin")
        async with aiofiles.open(target, "wb") as handle:
            await handle.write(content)
        return target

    def list_files(self, id_pncp: str | PncpId) -> list[Path]:
        directory = self.tender_dir(id_pncp)
        return sorted(path for path in directory.iterdir() if path.is_file())

    @staticmethod
    def filename_from_arquivo(arquivo: dict[str, Any], index: int) -> str:
        title = (
            arquivo.get("titulo")
            or arquivo.get("nome")
            or arquivo.get("tipoDocumentoNome")
            or f"anexo_{index}"
        )
        if isinstance(title, str) and not Path(title).suffix:
            title = f"{title}.pdf"
        return str(title)
