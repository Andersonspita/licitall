from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from src.agents.checklist import build_checklist_from_parsed
from src.agents.extractor import build_tender_from_sources
from src.agents.legal_rag import analyze_legal_risks_with_rag
from src.ingestion.client import PncpClient
from src.parser.service import ParserService
from src.rag.retriever import ensure_legal_index


class LicitAllState(TypedDict, total=False):
    id_pncp: str
    uf: str
    raw_payload: dict[str, Any]
    document_paths: list[str]
    parsed: list[dict[str, Any]]
    markdown: str
    tender: dict[str, Any]
    missing_fields: list[str]
    sections_found: list[str]
    legal_risks: list[dict[str, Any]]
    checklist: list[str]
    matches: list[dict[str, Any]]
    rag_indexed: int
    messages: Annotated[list, add_messages]
    error: str


async def ingestion_node(state: LicitAllState) -> LicitAllState:
    """Garante índice jurídico e metadados mínimos do PNCP."""
    indexed = await ensure_legal_index()
    updates: LicitAllState = {"rag_indexed": indexed}
    id_pncp = state.get("id_pncp")
    if id_pncp and not state.get("raw_payload"):
        # Payload opcional — itens buscados no extractor
        updates["raw_payload"] = state.get("raw_payload") or {}
    return updates


async def parser_node(state: LicitAllState) -> LicitAllState:
    id_pncp = state.get("id_pncp")
    if not id_pncp:
        return {"error": "id_pncp ausente"}
    service = ParserService()
    docs = service.parse_tender(id_pncp, persist=True)
    return {
        "document_paths": [str(doc.source_path) for doc in docs],
        "parsed": [
            {
                "file": str(doc.source_path),
                "engine": doc.engine,
                "sections": list(doc.sections.keys()),
                "refs_count": len(doc.refs),
                "markdown": doc.markdown,
            }
            for doc in docs
        ],
        "markdown": "\n\n".join(doc.markdown for doc in docs),
    }


async def extractor_node(state: LicitAllState) -> LicitAllState:
    id_pncp = state.get("id_pncp") or "UNKNOWN"
    from src.parser.docling_parser import ParsedDocument
    from pathlib import Path

    parsed_docs = [
        ParsedDocument(
            source_path=Path(item["file"]),
            markdown=item.get("markdown") or "",
            sections={k: "" for k in item.get("sections") or []},
            refs=[],
            engine=item.get("engine") or "graph",
        )
        for item in state.get("parsed") or []
    ]
    # Re-parse leve para refs/seções completas
    if id_pncp != "UNKNOWN":
        parsed_docs = ParserService().parse_tender(id_pncp, persist=False)

    itens: list[dict[str, Any]] = []
    try:
        async with PncpClient() as client:
            itens = await client.get_itens(id_pncp)
    except Exception:
        itens = []

    result = build_tender_from_sources(
        id_pncp=id_pncp,
        pncp_payload=state.get("raw_payload") or {},
        pncp_itens=itens,
        parsed_docs=parsed_docs,
    )
    return {
        "tender": result.tender.model_dump(mode="json"),
        "missing_fields": result.missing_fields,
        "sections_found": result.sections_found,
    }


async def legal_analyzer_node(state: LicitAllState) -> LicitAllState:
    id_pncp = state.get("id_pncp") or ""
    docs = ParserService().parse_tender(id_pncp, persist=False) if id_pncp else []
    risks = await analyze_legal_risks_with_rag(docs)
    checklist = build_checklist_from_parsed(docs)
    tender = dict(state.get("tender") or {})
    if tender:
        tender["riscos_juridicos"] = [r.model_dump(mode="json") for r in risks]
        tender["documentos_exigidos"] = checklist.as_flat_list()
        tender["documentos_habilitacao"] = [
            d.model_dump(mode="json")
            for d in (
                checklist.habilitacao_juridica
                + checklist.regularidade_fiscal_social_trabalhista
                + checklist.qualificacao_economico_financeira
                + checklist.qualificacao_tecnica
            )
        ]
    return {
        "legal_risks": [r.model_dump(mode="json") for r in risks],
        "checklist": checklist.as_flat_list(),
        "tender": tender,
    }


async def matcher_node(state: LicitAllState) -> LicitAllState:
    """Placeholder Fase 4 — matchmaking Minha Receita."""
    return {"matches": state.get("matches") or []}


def build_graph():
    """Ingestion → Parser → Extractor → LegalAnalyzer → Matcher."""
    graph = StateGraph(LicitAllState)
    graph.add_node("ingestion", ingestion_node)
    graph.add_node("parser", parser_node)
    graph.add_node("extractor", extractor_node)
    graph.add_node("legal_analyzer", legal_analyzer_node)
    graph.add_node("matcher", matcher_node)
    graph.add_edge(START, "ingestion")
    graph.add_edge("ingestion", "parser")
    graph.add_edge("parser", "extractor")
    graph.add_edge("extractor", "legal_analyzer")
    graph.add_edge("legal_analyzer", "matcher")
    graph.add_edge("matcher", END)
    return graph.compile()


async def run_tender_graph(id_pncp: str, *, raw_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    app = build_graph()
    final = await app.ainvoke(
        {
            "id_pncp": id_pncp,
            "raw_payload": raw_payload or {},
            "messages": [],
        }
    )
    return {
        "id_pncp": id_pncp,
        "rag_indexed": final.get("rag_indexed"),
        "sections_found": final.get("sections_found"),
        "missing_fields": final.get("missing_fields"),
        "checklist": final.get("checklist"),
        "legal_risks": final.get("legal_risks"),
        "tender": final.get("tender"),
        "document_paths": final.get("document_paths"),
        "matches": final.get("matches"),
        "error": final.get("error"),
        "marco_legal": "Lei Federal nº 14.133/2021",
        "fase": 3,
    }
