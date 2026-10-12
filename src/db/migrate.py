"""Aplica as migrações (`python -m src.db.migrate`). Também adota bancos criados antes do Alembic.

Banco "legado" = tem as tabelas mas não tem `alembic_version` (foi criado por `create_all`). Ele é marcado como estando na
migração-base e depois recebe as migrações novas. Se o esquema dele divergir dos modelos, avisa (e, em produção, aborta).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

import src.models.tables  # noqa: F401
import src.rag.store  # noqa: F401
from src.config import get_settings

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "0001"
log = logging.getLogger("licitall.migrate")


def alembic_config(url: str | None = None) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    if url:
        cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


async def _tables(url: str) -> set[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            return await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    finally:
        await engine.dispose()


async def _diff(url: str) -> list:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            return await conn.run_sync(
                lambda c: compare_metadata(MigrationContext.configure(c, opts={"compare_type": True}), SQLModel.metadata)
            )
    finally:
        await engine.dispose()


def schema_diff(url: str) -> list:
    return asyncio.run(_diff(url))


def migrate(url: str | None = None, strict: bool = False) -> str:
    url = url or get_settings().database_url
    tables = asyncio.run(_tables(url))
    has_version, legacy = "alembic_version" in tables, "tender_ingest" in tables
    cfg = alembic_config(url)
    note = "ok"
    if not has_version and legacy:
        command.stamp(cfg, BASELINE)
        diff = schema_diff(url)
        note = "banco legado adotado na migração-base"
        if diff:
            msg = f"O esquema do banco legado diverge dos modelos ({len(diff)} diferenças): {diff[:3]}"
            if strict:
                raise RuntimeError(msg)
            log.warning(msg)
            note += " (com divergências; veja o aviso)"
    command.upgrade(cfg, "head")
    return note


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        print("migrações:", migrate(strict=get_settings().app_env.lower() == "production"))
    except Exception as exc:  # noqa: BLE001
        print(f"Falha ao migrar: {exc}", file=sys.stderr)
        sys.exit(1)
