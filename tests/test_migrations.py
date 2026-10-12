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

from alembic.script import ScriptDirectory

from _integracao import sem_banco
from src.db.migrate import BASELINE, alembic_config, migrate, schema_diff

HEAD = ScriptDirectory.from_config(alembic_config()).get_current_head()

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
        sem_banco(exc)
    url = str(make_url(BASE_URL).set(database=nome).render_as_string(hide_password=False))
    yield url
    _admin(f'drop database if exists "{nome}" with (force)')


def test_migracoes_geram_exatamente_o_esquema_dos_modelos(banco):
    assert migrate(banco, strict=True) == "ok"
    assert schema_diff(banco) == []  # nenhuma coluna, índice ou chave a mais ou a menos
    assert _query(banco, "select version_num from alembic_version") == [(HEAD,)]


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
    assert _query(banco, "select version_num from alembic_version") == [(HEAD,)]
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


def test_banco_na_migracao_anterior_recebe_a_nova(banco):
    """Um banco que já está em 0001 (produção existente) ganha as tabelas novas sem perder nada."""
    command.upgrade(alembic_config(banco), BASELINE)
    tabelas = {r[0] for r in _query(banco, "select table_name from information_schema.tables where table_schema='public'")}
    assert "certidoes" not in tabelas and "atestados" not in tabelas
    assert migrate(banco, strict=True) == "ok"
    assert _query(banco, "select version_num from alembic_version") == [(HEAD,)]
    assert schema_diff(banco) == []


def _perfis_em_0002(url: str) -> tuple[str, str]:
    """Banco em 0002 (empresa_id ainda texto) com 1 perfil válido e 1 órfão (e-mail, de antes da autenticação)."""
    command.upgrade(alembic_config(url), "0002")
    empresa, valido, orfao = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())

    async def go():
        eng = create_async_engine(url)
        async with eng.begin() as c:
            await c.execute(text("insert into empresas (id, nome, created_at) values (:e, 'Empresa A', now())"), {"e": empresa})
            for pid, emp in ((valido, empresa.upper()), (orfao, "cliente@antigo.com.br")):  # UUID em maiúsculas também vale
                await c.execute(text(
                    "insert into perfis_interesse (id, empresa_id, nome_perfil, ufs_permitidas, valor_minimo_item, apenas_me_epp, ativo, created_at) "
                    "values (:p, :e, 'Perfil', '{}', 0, false, true, now())"), {"p": pid, "e": emp})
            await c.execute(text("insert into regras_palavras_chave (id, perfil_id, tipo, termo) values (gen_random_uuid(), :p, 'POSITIVA', 'papel')"), {"p": orfao})
        await eng.dispose()

    asyncio.run(go())
    return empresa, valido


def test_0003_para_com_perfis_orfaos_sem_apagar_nada(banco, monkeypatch):
    monkeypatch.delenv("LICITALL_REMOVER_PERFIS_ORFAOS", raising=False)
    _perfis_em_0002(banco)
    with pytest.raises(Exception, match="1 perfil.*sem empresa válida.*cliente@antigo.com.br.*LICITALL_REMOVER_PERFIS_ORFAOS"):
        migrate(banco, strict=True)
    assert _query(banco, "select version_num from alembic_version") == [("0002",)]
    assert _query(banco, "select count(*) from perfis_interesse") == [(2,)]


def test_0003_remove_orfaos_quando_pedido_e_liga_perfil_a_empresa(banco, monkeypatch):
    monkeypatch.setenv("LICITALL_REMOVER_PERFIS_ORFAOS", "1")
    empresa, valido = _perfis_em_0002(banco)
    assert migrate(banco, strict=True) == "ok"
    assert schema_diff(banco) == []
    assert _query(banco, "select id::text, empresa_id::text from perfis_interesse") == [(valido, empresa)]
    assert _query(banco, "select count(*) from regras_palavras_chave") == [(0,)]  # regras do órfão saíram em cascata

    async def excluir_empresa():
        eng = create_async_engine(banco)
        async with eng.begin() as c:
            await c.execute(text("delete from empresas where id = :e"), {"e": empresa})
        await eng.dispose()

    asyncio.run(excluir_empresa())
    assert _query(banco, "select count(*) from perfis_interesse") == [(0,)]  # sem perfis órfãos daqui em diante


def test_0003_downgrade_volta_para_texto(banco, monkeypatch):
    monkeypatch.setenv("LICITALL_REMOVER_PERFIS_ORFAOS", "1")
    _, valido = _perfis_em_0002(banco)
    migrate(banco)
    command.downgrade(alembic_config(banco), "0002")
    assert _query(banco, "select data_type from information_schema.columns where table_name='perfis_interesse' and column_name='empresa_id'") == [("character varying",)]
    assert _query(banco, "select id::text from perfis_interesse") == [(valido,)]
