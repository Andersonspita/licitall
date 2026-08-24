from __future__ import annotations

import re

from src.compliance.lei_14133 import LEI_14133_REF
from src.models.enums import LegalAction
from src.models.schemas import DocumentRef, LegalRiskItem
from src.parser.docling_parser import ParsedDocument, refs_from_markdown

LEGAL_CORPUS_HINTS = (
    "Lei Federal nº 14.133/2021",
    "Lei Complementar nº 123/2006",
    "Jurisprudência consolidada do TCU",
)

_RISK_RULES: tuple[tuple[re.Pattern[str], str, str, LegalAction], ...] = (
    (
        re.compile(r"marca\s+(?:de\s+)?refer[eê]ncia|somente da marca|marca exclusiv", re.I),
        "Possível restrição por marca sem verificar justificativa técnica no trecho.",
        f"Art. 41 e princípios do Art. 5º da {LEI_14133_REF}; orientação TCU contra direcionamento.",
        LegalAction.PEDIDO_ESCLARECIMENTO,
    ),
    (
        re.compile(r"capital social m[ií]nimo.{0,40}(\d{1,3}(?:\.\d{3})*(?:,\d+)?\s*%|\d+\s*%)", re.I),
        "Exigência de capital social mínimo percentual — verificar se excede parâmetros do TCU (~10%).",
        f"Art. 69 da {LEI_14133_REF}; jurisprudência TCU sobre onerosidade excessiva.",
        LegalAction.PEDIDO_ESCLARECIMENTO,
    ),
    (
        re.compile(r"vistoria t[eé]cnica.{0,80}(obrigat[oó]ria|imprescind[ií]vel)", re.I),
        "Vistoria técnica obrigatória pode ser restritiva se o prazo/local inviabilizar competição.",
        f"Art. 63 e Art. 67 da {LEI_14133_REF}.",
        LegalAction.PEDIDO_ESCLARECIMENTO,
    ),
    (
        re.compile(r"impugna[cç][aã]o.{0,60}(\d+)\s*dias?\s*(?:corridos|úteis|uteis)?", re.I),
        "Conferir se o prazo de impugnação respeita 3 dias úteis antes da abertura (Art. 164).",
        f"Art. 164 da {LEI_14133_REF}.",
        LegalAction.PEDIDO_ESCLARECIMENTO,
    ),
)


def analyze_legal_risks_from_refs(refs: list[DocumentRef]) -> list[LegalRiskItem]:
    risks: list[LegalRiskItem] = []
    seen: set[str] = set()
    for ref in refs:
        for pattern, motivo, fundamento, acao in _RISK_RULES:
            match = pattern.search(ref.texto)
            if not match:
                continue
            clausula = match.group(0).strip()
            key = clausula.lower()
            if key in seen:
                continue
            seen.add(key)
            risks.append(
                LegalRiskItem(
                    clausula=clausula[:400],
                    motivo_risco=motivo,
                    fundamentacao_legal=fundamento,
                    sugestao_acao=acao,
                    pagina_referencia=ref.pagina,
                    paragrafo_referencia=ref.paragrafo,
                )
            )
    return risks


def analyze_legal_risks(markdown: str) -> list[LegalRiskItem]:
    return analyze_legal_risks_from_refs(refs_from_markdown(markdown))


def analyze_legal_risks_from_parsed(docs: list[ParsedDocument]) -> list[LegalRiskItem]:
    refs = [ref for doc in docs for ref in doc.refs]
    if not refs:
        refs = refs_from_markdown("\n\n".join(doc.markdown for doc in docs))
    return analyze_legal_risks_from_refs(refs)


async def analyze_legal_risks_with_rag(
    docs: list[ParsedDocument],
    *,
    top_k: int = 3,
) -> list[LegalRiskItem]:
    """Triagem heurística enriquecida com trechos da Lei 14.133 / TCU (pgvector ou memória)."""
    from src.rag.retriever import ensure_legal_index, retrieve_legal_context

    await ensure_legal_index()
    base = analyze_legal_risks_from_parsed(docs)
    enriched: list[LegalRiskItem] = []
    for risk in base:
        hits = await retrieve_legal_context(f"{risk.clausula}\n{risk.motivo_risco}", top_k=top_k)
        if hits:
            best = hits[0]
            fund = (
                f"{risk.fundamentacao_legal} | RAG: {best.fundamentacao} "
                f"(score={best.score:.3f}, fonte={best.source})"
            )
            enriched.append(risk.model_copy(update={"fundamentacao_legal": fund}))
        else:
            enriched.append(risk)
    return enriched
