from __future__ import annotations

from typing import Any

import httpx

from src.config import Settings, get_settings
from src.models.enums import CompanySize

SITUACAO_ATIVA = 2
PORTE_MAP: dict[str, CompanySize] = {
    "MICRO EMPRESA": CompanySize.ME,
    "EMPRESA DE PEQUENO PORTE": CompanySize.EPP,
    "DEMAIS": CompanySize.DEMAIS,
    "NÃO INFORMADO": CompanySize.NAO_INFORMADO,
}


class MinhaReceitaClient:
    """Consulta a API local do Minha Receita (não altera o repositório de referência)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.AsyncClient(
            base_url=self.settings.minha_receita_base_url.rstrip("/"),
            timeout=90.0,
            headers={"Accept": "application/json"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_company(self, cnpj: str) -> dict[str, Any]:
        digits = "".join(ch for ch in cnpj if ch.isalnum())
        response = await self._client.get(f"/{digits}")
        response.raise_for_status()
        return response.json()

    async def search(
        self,
        *,
        cnae: str | list[str] | None = None,
        uf: str | list[str] | None = None,
        municipio: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: list[tuple[str, str]] = [("limit", str(min(limit, 1000)))]
        for value in _as_list(cnae):
            params.append(("cnae", value))
        for value in _as_list(uf):
            params.append(("uf", value.upper()))
        if municipio:
            params.append(("municipio", municipio))
        if cursor:
            params.append(("cursor", cursor))
        response = await self._client.get("/", params=params)
        response.raise_for_status()
        return response.json()

    async def search_active(
        self,
        *,
        cnae: str | list[str],
        uf: str | None = None,
        municipio: str | None = None,
        portes: tuple[CompanySize, ...] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        payload = await self.search(cnae=cnae, uf=uf, municipio=municipio, limit=limit)
        companies = payload.get("data") or []
        active = [
            company
            for company in companies
            if company.get("situacao_cadastral") == SITUACAO_ATIVA
            or str(company.get("descricao_situacao_cadastral") or "").upper() == "ATIVA"
        ]
        if portes:
            allowed = {item.value for item in portes}
            active = [
                company
                for company in active
                if PORTE_MAP.get(str(company.get("porte") or "").upper(), CompanySize.NAO_INFORMADO).value
                in allowed
            ]
        return active


def _as_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]
