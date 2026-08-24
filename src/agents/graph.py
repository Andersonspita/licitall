from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


class LicitAllState(TypedDict, total=False):
    id_pncp: str
    uf: str
    raw_payload: dict[str, Any]
    document_paths: list[str]
    markdown: str
    tender: dict[str, Any]
    legal_risks: list[dict[str, Any]]
    checklist: list[str]
    matches: list[dict[str, Any]]
    messages: Annotated[list, add_messages]
    error: str


async def ingestion_node(state: LicitAllState) -> LicitAllState:
    return state


async def parser_node(state: LicitAllState) -> LicitAllState:
    return state


async def legal_analyzer_node(state: LicitAllState) -> LicitAllState:
    return state


async def matcher_node(state: LicitAllState) -> LicitAllState:
    return state


def build_graph():
    """Grafo Fase 3: IngestionNode → ParserNode → LegalAnalyzerNode → MatcherNode."""
    graph = StateGraph(LicitAllState)
    graph.add_node("ingestion", ingestion_node)
    graph.add_node("parser", parser_node)
    graph.add_node("legal_analyzer", legal_analyzer_node)
    graph.add_node("matcher", matcher_node)
    graph.add_edge(START, "ingestion")
    graph.add_edge("ingestion", "parser")
    graph.add_edge("parser", "legal_analyzer")
    graph.add_edge("legal_analyzer", "matcher")
    graph.add_edge("matcher", END)
    return graph.compile()
