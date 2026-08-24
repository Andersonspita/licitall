from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.outreach.evolution import EvolutionClient


class OutreachPayload(BaseModel):
    phone: str = Field(..., description="Número com DDI, ex.: 5511999999999")
    orgao: str
    objeto: str
    valor_total: float = 0
    id_pncp: str
    margem_estimada: str | None = None
    checklist_resumo: list[str] = Field(default_factory=list)
    dossier_url: str | None = None
    instance: str | None = None


class OutreachService:
    def __init__(self, client: EvolutionClient | None = None) -> None:
        self.client = client or EvolutionClient()

    async def aclose(self) -> None:
        await self.client.aclose()

    def build_message(self, payload: OutreachPayload) -> str:
        base = self.client.build_opportunity_message(
            orgao=payload.orgao,
            objeto=payload.objeto,
            valor_total=payload.valor_total,
            id_pncp=payload.id_pncp,
            dossier_url=payload.dossier_url,
        )
        extra: list[str] = []
        if payload.margem_estimada:
            extra.append(f"Margem estimada (indicativa): {payload.margem_estimada}")
        if payload.checklist_resumo:
            extra.append("Checklist (trechos do edital):")
            extra.extend(f"- {item}" for item in payload.checklist_resumo[:8])
        extra.append(
            "Minutas geradas por IA exigem revisão humana (Lei 8.906/1994). "
            "Marco: Lei 14.133/2021."
        )
        return base + ("\n\n" + "\n".join(extra) if extra else "")

    async def notify_opportunity(self, payload: OutreachPayload) -> dict[str, Any]:
        text = self.build_message(payload)
        result = await self.client.send_text(payload.phone, text, instance=payload.instance)
        return {"sent": True, "evolution": result, "preview": text[:500]}
