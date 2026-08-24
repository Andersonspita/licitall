from __future__ import annotations

from src.models.schemas import TenderSchema

DISCLAIMER_OAB = (
    "MINUTA DE SUPORTE ADMINISTRATIVO GERADA POR INTELIGÊNCIA ARTIFICIAL. "
    "Este documento não constitui parecer jurídico nem substabelece advogado. "
    "Exige revisão, adequação e assinatura pelo responsável legal da empresa "
    "ou por advogado constituído, nos termos da Lei nº 8.906/1994 (Estatuto da OAB)."
)


def render_minuta(kind: str, tender: TenderSchema, body: str) -> str:
    title = {
        "proposta": "Proposta de Preços",
        "esclarecimento": "Pedido de Esclarecimento (Art. 164, Lei 14.133/2021)",
        "impugnacao": "Impugnação ao Edital (Art. 164, Lei 14.133/2021)",
        "declaracao": "Declarações obrigatórias",
    }.get(kind, kind)
    return (
        f"# {title}\n\n"
        f"**Id PNCP:** {tender.id_pncp}  \n"
        f"**Órgão:** {tender.orgao_comprador}  \n"
        f"**Objeto:** {tender.objeto_resumido}\n\n"
        f"{body.strip()}\n\n"
        f"---\n\n*{DISCLAIMER_OAB}*\n"
    )
