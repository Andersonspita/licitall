"""Migrações (Alembic) contra um PostgreSQL real, em bancos descartáveis. Pula sem banco."""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

from src.db.migrate import BASELINE, alembic_config, migrate, schema_diff

BASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://licitall:licitall@localhost:5433/licitall")


def _admin(sql: str) -> None:
    async def go():
        eng = create_async_engine(make_url(BASE_URL).set(database="postgres"), isolation_level="AUTOCOMMIT")
        try:
            async with eng.connect() as c:
                await c.execute(text(sql))
        finally:
            await eng.dispose()

    asyncio.run(go())


def _query(url: str, sql: str):
    async def go():
        eng = create_async_engine(url)
        try:
            async with eng.connect() as c:
                return (await c.execute(text(sql))).all()
        finally:
            await eng.dispose()

    return asyncio.run(go())


def _create_all(url: str) -> None:
    import src.models.tables  # noqa: F401
    import src.rag.store  # noqa: F401

    async def go():
        eng = create_async_engine(url)
        try:
            async with eng.begin() as c:
                await c.run_sync(SQLModel.metadata.create_all)
        finally:
            await eng.dispose()

    asyncio.run(go())


@pytest.fixture
def banco():
    nome = f"licitall_migtest_{uuid.uuid4().hex[:8]}"
    try:
        _admin(f'create database "{nome}"')
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL indisponível: {exc}")
    url = str(make_url(BASE_URL).set(database=nome).render_as_string(hide_password=False))
    yield url
    _admin(f'drop database if exists "{nome}" with (force)')


def test_migracoes_geram_exatamente_o_esquema_dos_modelos(banco):
    assert migrate(banco, strict=True) == "ok"
    assert schema_diff(banco) == []  # nenhuma coluna, índice ou chave a mais ou a menos
    assert _query(banco, "select version_num from alembic_version") == [(BASELINE,)]


def test_migrar_de_novo_nao_muda_nada(banco):
    migrate(banco)
    assert migrate(banco) == "ok"
    assert schema_diff(banco) == []


def test_downgrade_remove_todas_as_tabelas(banco):
    migrate(banco)
    command.downgrade(alembic_config(banco), "base")
    tabelas = {r[0] for r in _query(banco, "select table_name from information_schema.tables where table_schema='public'")}
    assert tabelas <= {"alembic_version"}


def test_banco_legado_e_adotado_sem_perder_dados(banco):
    _create_all(banco)  # como era antes do Alembic

    async def inserir():
        eng = create_async_engine(banco)
        async with eng.begin() as c:
            await c.execute(text(
                "insert into tender_ingest (id_pncp, status, payload, created_at, updated_at) "
                "values ('x-1', 'INGESTED', '{}', now(), now())"))
        await eng.dispose()

    asyncio.run(inserir())
    assert "alembic_version" not in {r[0] for r in _query(banco, "select table_name from information_schema.tables where table_schema='public'")}

    nota = migrate(banco, strict=True)
    assert nota.startswith("banco legado adotado")
    assert _query(banco, "select version_num from alembic_version") == [(BASELINE,)]
    assert _query(banco, "select id_pncp from tender_ingest") == [("x-1",)]


def test_banco_legado_divergente_aborta_em_modo_estrito(banco):
    _create_all(banco)

    async def quebrar():
        eng = create_async_engine(banco)
        async with eng.begin() as c:
            await c.execute(text("alter table tender_ingest drop column error_message"))
        await eng.dispose()

    asyncio.run(quebrar())
    with pytest.raises(RuntimeError, match="diverge"):
        migrate(banco, strict=True)


def test_banco_legado_divergente_so_avisa_fora_de_producao(banco):
    _create_all(banco)

    async def quebrar():
        eng = create_async_engine(banco)
        async with eng.begin() as c:
            await c.execute(text("alter table tender_ingest drop column error_message"))
        await eng.dispose()

    asyncio.run(quebrar())
    assert "divergências" in migrate(banco, strict=False)
