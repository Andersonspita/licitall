"""Ramo do edital por significado, quando o mapa de palavras-chave (`cnae_map`) não o identifica.

Compara o objeto do edital com a descrição de cada CNAE da empresa (Minha Receita: `cnae_fiscal_descricao` e
`cnaes_secundarios[].descricao`) e fica com a maior similaridade. Decide só nos extremos:
- similaridade >= alto  → "compativel"   (pontua quase como CNAE compatível)
- similaridade <  baixo → "incompativel" (vai para SKIP, como CNAE sem interseção)
- entre os dois         → "incerto"      (continua para revisão manual, teto de ramo desconhecido)

Limiares por provedor, em cosseno bruto. Só há limiar para provedor com calibração medida; sem ele (ou com o
`hash` local, que não é semântico) nada muda. Os de `gemini` são PROVISÓRIOS: vieram da medição item × perfil
(sem relação: mediana 0,76, p95 0,80; relacionados: p90 0,84) e precisam ser remedidos com objeto × CNAE.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.matching.semantic import content_hash, cosine, sanitize_item_text

LIMIARES_RAMO: dict[str, tuple[float, float]] = {"gemini": (0.76, 0.84)}


@dataclass(frozen=True)
class RamoSemantico:
    status: str  # compativel | incompativel | incerto
    similaridade: float
    referencia: str  # descrição do CNAE da empresa mais parecida

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "similaridade": round(self.similaridade, 3), "referencia": self.referencia}


def descricoes_cnae(company: dict[str, Any]) -> list[str]:
    """Descrições distintas dos CNAEs da empresa (principal primeiro)."""
    out: list[str] = []
    for d in [company.get("cnae_fiscal_descricao")] + [
        c.get("descricao") for c in company.get("cnaes_secundarios") or [] if isinstance(c, dict)
    ]:
        d = str(d or "").strip()
        if d and d not in out:
            out.append(d)
    return out


def classificar(similaridade: float, limiares: tuple[float, float]) -> str:
    baixo, alto = limiares
    if similaridade >= alto:
        return "compativel"
    if similaridade < baixo:
        return "incompativel"
    return "incerto"


def texto_objeto(tender: dict[str, Any]) -> str:
    return sanitize_item_text(tender.get("objeto_resumido"))


def avaliar(
    tenders: list[dict[str, Any]], descricoes: list[str], vetores: dict[str, list[float]], limiares: tuple[float, float]
) -> dict[str, RamoSemantico]:
    """id_pncp → ramo por significado, para os editais sem CNAE inferido. Puro (vetores já resolvidos)."""
    refs = [(d, vetores.get(content_hash(d))) for d in descricoes]
    refs = [(d, v) for d, v in refs if v]
    out: dict[str, RamoSemantico] = {}
    if not refs:
        return out
    for t in tenders:
        if t.get("cnaes_compativeis"):
            continue
        vec = vetores.get(content_hash(texto_objeto(t)))
        if not vec:
            continue
        sim, ref = max((cosine(vec, v), d) for d, v in refs)
        out[t["id_pncp"]] = RamoSemantico(classificar(sim, limiares), sim, ref)
    return out
