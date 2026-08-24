"""Verificação de dependências (Postgres, Redis, Minha Receita, Evolution)."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from src.config import get_settings


async def _check_http(name: str, url: str, path: str = "/") -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url.rstrip('/')}{path}")
            ok = response.status_code < 500
            return {
                "service": name,
                "status": "up" if ok else "degraded",
                "http_status": response.status_code,
                "url": url,
            }
    except Exception as exc:
        return {"service": name, "status": "down", "error": str(exc), "url": url}


async def _check_postgres() -> dict[str, Any]:
    try:
        from sqlalchemy import text

        from src.db import get_engine

        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"service": "postgres", "status": "up"}
    except Exception as exc:
        return {"service": "postgres", "status": "down", "error": str(exc)}


async def _check_redis() -> dict[str, Any]:
    settings = get_settings()
    try:
        import redis.asyncio as redis

        client = redis.from_url(settings.redis_url)
        await client.ping()
        await client.aclose()
        return {"service": "redis", "status": "up", "url": settings.redis_url}
    except Exception as exc:
        return {"service": "redis", "status": "down", "error": str(exc)}


async def check_dependencies() -> dict[str, Any]:
    settings = get_settings()
    checks = await asyncio.gather(
        _check_postgres(),
        _check_redis(),
        _check_http("minha_receita", settings.minha_receita_base_url),
        _check_http("evolution_api", settings.evolution_api_url),
        return_exceptions=True,
    )
    results: list[dict[str, Any]] = []
    for item in checks:
        if isinstance(item, Exception):
            results.append({"service": "unknown", "status": "down", "error": str(item)})
        else:
            results.append(item)
    up = sum(1 for r in results if r.get("status") == "up")
    return {
        "summary": f"{up}/{len(results)} serviços up",
        "all_up": up == len(results),
        "services": results,
    }
