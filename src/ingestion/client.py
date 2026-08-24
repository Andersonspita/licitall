from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import Settings, get_settings
from src.models.enums import (
    DEFAULT_INGESTION_MODALITIES,
    PNCP_MODALITY_CODES,
    ModalityEnum,
)

_ID_PNCP_RE = re.compile(r"^(\d{14})-1-(\d+)/(\d{4})$")


class PncpError(RuntimeError):
    """Falha ao consultar ou baixar recursos do PNCP."""


@dataclass(frozen=True, slots=True)
class PncpId:
    cnpj: str
    sequencial: int
    ano: int
    numero_controle: str

    @property
    def slug(self) -> str:
        """Identificador seguro para pasta no Windows (sem barra)."""
        return f"{self.cnpj}-1-{self.sequencial:06d}_{self.ano}"


def parse_id_pncp(numero_controle: str) -> PncpId:
    raw = numero_controle.strip()
    match = _ID_PNCP_RE.match(raw)
    if not match:
        raise ValueError(
            f"numeroControlePNCP inválido: {numero_controle!r}. "
            "Esperado CNPJ-1-SEQUENCIAL/ANO."
        )
    return PncpId(
        cnpj=match.group(1),
        sequencial=int(match.group(2)),
        ano=int(match.group(3)),
        numero_controle=raw,
    )


def _as_yyyymmdd(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.date().strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    digits = re.sub(r"\D", "", value)
    if len(digits) != 8:
        raise ValueError(f"Data PNCP inválida: {value!r}. Use AAAAMMDD.")
    return digits


class PncpClient:
    """Client assíncrono da API pública de Consultas e da API core do PNCP."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.pncp_timeout_seconds),
            headers={"Accept": "application/json", "User-Agent": "LicitAll/0.1"},
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> PncpClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        response = await self._client.get(url, params=params)
        if response.status_code == 204:
            return {}
        if response.status_code >= 500:
            response.raise_for_status()
        if response.status_code >= 400:
            raise PncpError(f"PNCP {response.status_code} em {url}: {response.text[:500]}")
        if not response.content:
            return {}
        return response.json()

    async def list_publicacoes(
        self,
        *,
        data_inicial: date | datetime | str,
        data_final: date | datetime | str,
        modalidade: ModalityEnum | int,
        uf: str | None = None,
        pagina: int = 1,
        tamanho_pagina: int | None = None,
        codigo_municipio_ibge: int | None = None,
        cnpj_orgao: str | None = None,
    ) -> dict[str, Any]:
        codigo = (
            modalidade
            if isinstance(modalidade, int)
            else PNCP_MODALITY_CODES[modalidade]
        )
        params: dict[str, Any] = {
            "dataInicial": _as_yyyymmdd(data_inicial),
            "dataFinal": _as_yyyymmdd(data_final),
            "codigoModalidadeContratacao": codigo,
            "pagina": pagina,
            "tamanhoPagina": max(10, min(int(tamanho_pagina or self.settings.pncp_page_size), 50)),
        }
        if uf:
            params["uf"] = uf.upper()
        if codigo_municipio_ibge:
            params["codigoMunicipioIbge"] = codigo_municipio_ibge
        if cnpj_orgao:
            params["cnpj"] = re.sub(r"\D", "", cnpj_orgao)
        url = f"{self.settings.pncp_consulta_base_url.rstrip('/')}/v1/contratacoes/publicacao"
        return await self._get_json(url, params)

    async def iter_publicacoes(
        self,
        *,
        data_inicial: date | datetime | str,
        data_final: date | datetime | str,
        uf: str | None = None,
        modalidades: tuple[ModalityEnum, ...] = DEFAULT_INGESTION_MODALITIES,
        codigo_municipio_ibge: int | None = None,
        cnpj_orgao: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Percorre todas as páginas de cada modalidade filtrada."""
        for modalidade in modalidades:
            pagina = 1
            total_paginas = 1
            while pagina <= total_paginas:
                payload = await self.list_publicacoes(
                    data_inicial=data_inicial,
                    data_final=data_final,
                    modalidade=modalidade,
                    uf=uf,
                    pagina=pagina,
                    codigo_municipio_ibge=codigo_municipio_ibge,
                    cnpj_orgao=cnpj_orgao,
                )
                total_paginas = int(payload.get("totalPaginas") or 1)
                for item in payload.get("data") or []:
                    yield item
                if payload.get("empty") or pagina >= total_paginas:
                    break
                pagina += 1

    async def list_propostas_abertas(
        self,
        *,
        data_final: date | datetime | str,
        modalidade: ModalityEnum | int,
        pagina: int = 1,
        tamanho_pagina: int | None = None,
        uf: str | None = None,
    ) -> dict[str, Any]:
        codigo = (
            modalidade
            if isinstance(modalidade, int)
            else PNCP_MODALITY_CODES[modalidade]
        )
        params: dict[str, Any] = {
            "dataFinal": _as_yyyymmdd(data_final),
            "codigoModalidadeContratacao": codigo,
            "pagina": pagina,
            "tamanhoPagina": max(10, min(int(tamanho_pagina or self.settings.pncp_page_size), 50)),
        }
        if uf:
            params["uf"] = uf.upper()
        url = f"{self.settings.pncp_consulta_base_url.rstrip('/')}/v1/contratacoes/proposta"
        return await self._get_json(url, params)

    async def get_arquivos(self, pncp_id: PncpId | str) -> list[dict[str, Any]]:
        parsed = pncp_id if isinstance(pncp_id, PncpId) else parse_id_pncp(pncp_id)
        url = (
            f"{self.settings.pncp_core_base_url.rstrip('/')}/v1/orgaos/"
            f"{parsed.cnpj}/compras/{parsed.ano}/{parsed.sequencial}/arquivos"
        )
        payload = await self._get_json(url)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            data = payload.get("data")
            return data if isinstance(data, list) else []
        return []

    async def get_itens(self, pncp_id: PncpId | str) -> list[dict[str, Any]]:
        parsed = pncp_id if isinstance(pncp_id, PncpId) else parse_id_pncp(pncp_id)
        url = (
            f"{self.settings.pncp_core_base_url.rstrip('/')}/v1/orgaos/"
            f"{parsed.cnpj}/compras/{parsed.ano}/{parsed.sequencial}/itens"
        )
        payload = await self._get_json(url)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            data = payload.get("data")
            return data if isinstance(data, list) else []
        return []

    async def download_bytes(self, file_url: str) -> bytes:
        response = await self._client.get(file_url)
        if response.status_code >= 400:
            raise PncpError(f"Falha ao baixar anexo ({response.status_code}): {file_url}")
        return response.content
