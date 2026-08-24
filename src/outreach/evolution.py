from __future__ import annotations

from typing import Any

import httpx

from src.config import Settings, get_settings


class EvolutionClient:
    """Disparo transacional via Evolution API local (não altera o repositório de referência)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.AsyncClient(
            base_url=self.settings.evolution_api_url.rstrip("/"),
            timeout=30.0,
            headers={
                "apikey": self.settings.evolution_api_key,
                "Content-Type": "application/json",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def send_text(self, number: str, text: str, instance: str | None = None) -> dict[str, Any]:
        instance_name = instance or self.settings.evolution_instance
        response = await self._client.post(
            f"/message/sendText/{instance_name}",
            json={"number": number, "text": text},
        )
        response.raise_for_status()
        return response.json()

    def build_opportunity_message(
        self,
        *,
        orgao: str,
        objeto: str,
        valor_total: float,
        id_pncp: str,
        dossier_url: str | None = None,
    ) -> str:
        link = f"\nDossiê: {dossier_url}" if dossier_url else ""
        return (
            "LicitAll — nova oportunidade pública\n\n"
            f"Órgão: {orgao}\n"
            f"Objeto: {objeto}\n"
            f"Valor estimado: R$ {valor_total:,.2f}\n"
            f"Id PNCP: {id_pncp}\n"
            "A peça é minuta de suporte de IA e exige revisão humana."
            f"{link}"
        )
