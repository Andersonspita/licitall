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
# Com texto limpo os vetores mudam e a distribuição também: NÃO MEDIDO ainda (valores provisórios, só para rodar a medição).
LIMIARES_RAMO_LIMPO: dict[str, tuple[float, float]] = {"gemini": (0.78, 0.86)}

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


# Texto limpo (opção `texto_limpo`, em medição): sem as palavras genéricas que dominavam a similaridade no teste real
# ("Serviços" aproximava "Serviços advocatícios" de qualquer contratação de serviço; "Comércio varejista de" diluía o
# CNAE e itens curtos como "colchete para encadernação" pontuavam baixo contra papelaria).
_PREFIXOS_OBJETO = [re.compile(p) for p in (
    r"^\[[^\]]*\]\s*-?\s*",  # [LICITANET] - , [Portal de Compras Públicas] -
    r"^(o presente termo de referencia tem por objeto|a presente demanda tem por objeto|objeto:?)\s+",
    r"^selecao de proposta apta a gerar o melhor resultado para\s+",
    r"^registro de precos?\s+(para|visando)\s+",
    r"^(a|o|e|eventual|futura|parcelada|de forma parcelada)\s+",
    r"^(aquisicao|contratacao|fornecimento|prestacao|confeccao e fornecimento)(\s+(de|da|do|dos|das))?\s+",
    r"^(empresas?|pessoa juridica|instituicao)(\s+especializadas?)?(\s+(para|em|no|na|nos|nas|do|da))?\s+",
    r"^servicos?(\s+(comuns|continuos|nao continuados|tecnicos|especializados|integrados))*(\s+(de|em|para))?\s+",
)]
_PREFIXOS_CNAE = [re.compile(p) for p in (
    r"^comercio\s+(varejista|atacadista)(\s+especializado)?(\s+(de|em))?\s+",
    r"^(servicos?|atividades?)(\s+de)?\s+",
    r"^(fabricacao|confeccao)\s+de\s+",
)]
_SUFIXO_CNAE = re.compile(r",?\s+(exceto|nao especificad|e outros nao).*$")


def _sem_prefixos(texto: str, prefixos: list[re.Pattern[str]]) -> str:
    anterior = None
    while texto and texto != anterior:
        anterior = texto
        for p in prefixos:
            texto = p.sub("", texto, count=1).strip(" -:,.")
    return texto


def limpar_objeto(objeto: str) -> str:
    base = sanitize_item_text(objeto)
    return _sem_prefixos(base, _PREFIXOS_OBJETO) or base


def limpar_cnae(descricao: str) -> str:
    base = _sem_acento(descricao).strip()
    return _SUFIXO_CNAE.sub("", _sem_prefixos(base, _PREFIXOS_CNAE)) or base


def texto_cnae(descricao: str, limpo: bool = False) -> str:
    return limpar_cnae(descricao) if limpo else descricao


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


def texto_objeto(tender: dict[str, Any], limpo: bool = False) -> str:
    objeto = tender.get("objeto_resumido")
    return limpar_objeto(objeto) if limpo else sanitize_item_text(objeto)


def avaliar(
    tenders: list[dict[str, Any]],
    descricoes: list[str],
    vetores: dict[str, list[float]],
    limiares: tuple[float, float],
    *,
    empresa_so_comercio: bool = False,
    limpo: bool = False,
) -> dict[str, RamoSemantico]:
    """id_pncp → ramo por significado, para os editais sem CNAE inferido. Puro (vetores já resolvidos).

    Com `empresa_so_comercio`, objeto de serviço/locação/seguro nunca sai "compativel" (fica "incerto").
    """
    refs = [(d, vetores.get(content_hash(texto_cnae(d, limpo)))) for d in descricoes]
    refs = [(d, v) for d, v in refs if v]
    out: dict[str, RamoSemantico] = {}
    if not refs:
        return out
    for t in tenders:
        if t.get("cnaes_compativeis"):
            continue
        vec = vetores.get(content_hash(texto_objeto(t, limpo)))
        if not vec:
            continue
        sim, ref = max((cosine(vec, v), d) for d, v in refs)
        status = classificar(sim, limiares)
        if status == "compativel" and empresa_so_comercio and e_servico(str(t.get("objeto_resumido") or "")):
            status = "incerto"
        out[t["id_pncp"]] = RamoSemantico(status, sim, ref)
    return out
