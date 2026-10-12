"""Qual rota atende uma requisição (a primeira que casar), sem depender da estrutura interna de app.routes."""

from __future__ import annotations

from starlette.routing import Match


def rota(metodo: str, caminho: str) -> str | None:
    from src.main import app

    scope = {"type": "http", "method": metodo, "path": caminho, "root_path": "", "headers": [], "query_string": b""}
    for r in app.routes:
        casou, filho = r.matches(scope)
        if casou == Match.FULL:
            return getattr(filho.get("route"), "path", None) or getattr(r, "path", None)
    return None
