"""Infraestrutura compartilhada dos testes de integração (PostgreSQL real). Pula sem banco.

URL: TEST_DATABASE_URL (padrão: o Postgres do docker compose, porta 5433). Cada execução usa um TAG único nas contas e
empresas criadas e apaga tudo ao final (as tabelas filhas saem por ON DELETE CASCADE).
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest
from sqlalchemy import text

DB_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://licitall:licitall@localhost:5433/licitall")
TAG = uuid.uuid4().hex[:8]
ADMIN_EMAIL = f"itest-admin-{TAG}@teste.com.br"
SENHA = "senha-de-teste-123"


def sem_banco(exc: Exception) -> None:
    """Sem PostgreSQL: pula localmente, mas falha quando REQUIRE_DB=1 (CI não pode passar em silêncio)."""
    msg = f"PostgreSQL indisponível para o teste de integração: {exc}"
    if os.environ.get("REQUIRE_DB") == "1":
        pytest.fail(msg)
    pytest.skip(msg)


def _email(nome: str) -> str:
    return f"itest-{nome}-{TAG}@teste.com.br"


@pytest.fixture
async def ambiente(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("ADMIN_EMAILS", ADMIN_EMAIL)
    monkeypatch.setenv("AUTH_REGISTRATION_OPEN", "true")
    monkeypatch.setenv("DIGEST_SCHEDULER_ENABLED", "false")

    import src.db as dbmod
    from src.config import get_settings

    get_settings.cache_clear()
    dbmod._engine = None
    dbmod._session_factory = None
    try:
        await dbmod.init_db()
        async with dbmod.get_engine().connect() as c:
            await c.execute(text("select 1"))
    except Exception as exc:  # noqa: BLE001
        sem_banco(exc)

    from src.auth.routes import throttle
    from src.main import app

    throttle._fails.clear()

    def novo_cliente() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")

    yield novo_cliente, dbmod

    async with dbmod.get_session_factory()() as s:
        await s.execute(text("delete from perfis_interesse where empresa_id in (select id from empresas where nome like :p)"), {"p": f"ITEST {TAG}%"})
        await s.execute(text("delete from usuarios where email like :p"), {"p": f"itest-%-{TAG}@teste.com.br"})
        await s.execute(text("delete from empresas where nome like :p"), {"p": f"ITEST {TAG}%"})
        await s.commit()
    await dbmod.get_engine().dispose()
    dbmod._engine = None
    dbmod._session_factory = None
    throttle._fails.clear()
    get_settings.cache_clear()


async def _registrar(c: httpx.AsyncClient, nome: str, senha: str = SENHA, email: str | None = None):
    return await c.post("/auth/register", json={
        "empresa_nome": f"ITEST {TAG} {nome}", "nome": f"Usuario {nome}", "email": email or _email(nome), "senha": senha,
    })
