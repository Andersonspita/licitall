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

import html
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from src.matching.semantic import content_hash, cosine, sanitize_item_text

# gemini: medido em editais reais da BA (out/2026) contra duas empresas.
# - Distribuidora com 24 CNAEs de comércio: acima de 0,83 quase tudo do ramo (exceto serviços, tratados abaixo); abaixo
#   de 0,78 quase nada; entre os dois, mistura (pastas e etiquetas a 0,78, cimento e próteses a 0,79).
# - Advocacia com 1 CNAE ("Serviços advocatícios"): NADA do ramo até 0,85; o topo era "Serviços de manutenção" (0,85),
#   puxado pela palavra "Serviços" em comum.
# Corte que serve às duas: compatível a partir de 0,86 (precisão primeiro; os acertos de 0,83–0,85 ficam em revisar).
LIMIARES_RAMO: dict[str, tuple[float, float]] = {"gemini": (0.78, 0.86)}

# Empresa só de comércio (CNAE divisões 45–47) não presta serviço: o significado aproxima "serviço de luthier" de
# "comércio de instrumentos musicais", "locação de brinquedos" de "comércio de brinquedos".
_SERVICO = re.compile(r"(?<![a-z])(servicos?|locacao|aluguel|seguros?)(?![a-z])")


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


def so_comercio(cnaes: list[str]) -> bool:
    return bool(cnaes) and all(str(c)[:2] in {"45", "46", "47"} for c in cnaes)


def e_servico(objeto: str) -> bool:
    return bool(_SERVICO.search(_sem_acento(objeto)))


def _sem_acento(text: str) -> str:
    base = unicodedata.normalize("NFKD", html.unescape(text or "").lower())
    return "".join(c for c in base if not unicodedata.combining(c))


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
    tenders: list[dict[str, Any]],
    descricoes: list[str],
    vetores: dict[str, list[float]],
    limiares: tuple[float, float],
    *,
    empresa_so_comercio: bool = False,
) -> dict[str, RamoSemantico]:
    """id_pncp → ramo por significado, para os editais sem CNAE inferido. Puro (vetores já resolvidos).

    Com `empresa_so_comercio`, objeto de serviço/locação/seguro nunca sai "compativel" (fica "incerto").
    """
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
        status = classificar(sim, limiares)
        if status == "compativel" and empresa_so_comercio and e_servico(str(t.get("objeto_resumido") or "")):
            status = "incerto"
        out[t["id_pncp"]] = RamoSemantico(status, sim, ref)
    return out
