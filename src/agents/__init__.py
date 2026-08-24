"""Agentes LicitAll. Importações pesadas (LangGraph) sob demanda."""

__all__ = ["build_graph"]


def build_graph():
    from src.agents.graph import build_graph as _build

    return _build()
