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


class DigestItem(BaseModel):
    id_pncp: str
    orgao: str | None = None
    objeto: str | None = None
    valor_total: float | None = None
    score: float
    recommendation: str = "REVIEW"
    uf: str | None = None


class DigestPayload(BaseModel):
    phone: str = Field(..., description="Número com DDI, ex.: 5511999999999")
    company_name: str
    cnpj: str | None = None
    opportunities: list[DigestItem] = Field(default_factory=list)
    top_n: int = Field(default=5, ge=1, le=15)
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

    def build_digest_message(self, payload: DigestPayload) -> str:
        items = payload.opportunities[: payload.top_n]
        lines = [
            "LicitAll — digest de oportunidades",
            "",
            f"Empresa: {payload.company_name}",
        ]
        if payload.cnpj:
            lines.append(f"CNPJ: {payload.cnpj}")
        lines.append(f"Top {len(items)} match(es) ranqueados:")
        lines.append("")

        if not items:
            lines.append("Nenhuma oportunidade acima do limiar neste ciclo.")
        else:
            for idx, item in enumerate(items, start=1):
                valor = (
                    f"R$ {item.valor_total:,.2f}"
                    if item.valor_total is not None
                    else "valor n/d"
                )
                objeto = (item.objeto or "objeto n/d").strip()
                if len(objeto) > 120:
                    objeto = objeto[:117] + "..."
                lines.append(
                    f"{idx}. [{item.recommendation}] score {item.score:.0f} — "
                    f"{item.orgao or 'Órgão n/d'} ({item.uf or 'UF?'})"
                )
                lines.append(f"   {objeto}")
                lines.append(f"   {valor} · PNCP {item.id_pncp}")
                lines.append("")

        lines.extend(
            [
                "Score explicável: CNAE + geo + porte LC 123 + fit econômico + prazo/Art. 164.",
                "Recomendações: BID (≥70) · REVIEW (40–69) · SKIP (<40).",
                "Minutas de IA exigem revisão humana (Lei 8.906/1994). Marco: Lei 14.133/2021.",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"

    async def notify_opportunity(self, payload: OutreachPayload) -> dict[str, Any]:
        text = self.build_message(payload)
        result = await self.client.send_text(payload.phone, text, instance=payload.instance)
        return {"sent": True, "evolution": result, "preview": text[:500]}

    async def notify_digest(self, payload: DigestPayload) -> dict[str, Any]:
        text = self.build_digest_message(payload)
        result = await self.client.send_text(payload.phone, text, instance=payload.instance)
        return {
            "sent": True,
            "evolution": result,
            "preview": text[:800],
            "items": len(payload.opportunities[: payload.top_n]),
        }
