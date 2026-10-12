"""Verificação de configuração de produção (sem banco)."""

from __future__ import annotations

import pytest

from src.config.production import assert_production_ready, production_problems
from src.config.settings import Settings

FORTE = dict(
    app_env="production",
    cookie_secure=True,
    debug=False,
    database_url="postgresql+asyncpg://licitall:Zq8vK2mXp7LrT4nB@postgres:5432/licitall",
    evolution_api_key="k" * 32,
    admin_emails="operador@empresa.com.br",
)


def cfg(**over) -> Settings:
    return Settings(_env_file=None, **{**FORTE, **over})


def test_configuracao_forte_passa():
    assert production_problems(cfg()) == []
    assert_production_ready(cfg())  # não levanta


def test_desenvolvimento_nunca_bloqueia():
    assert_production_ready(Settings(_env_file=None, app_env="development", cookie_secure=False,
                                     database_url="postgresql+asyncpg://licitall:licitall@localhost/x"))


@pytest.mark.parametrize("campo,valor,trecho", [
    ("cookie_secure", False, "COOKIE_SECURE"),
    ("debug", True, "DEBUG"),
    ("database_url", "postgresql+asyncpg://licitall:licitall@db/x", "senha do banco"),
    ("database_url", "postgresql+asyncpg://licitall:curta1@db/x", "senha do banco"),
    ("database_url", "postgresql+asyncpg://licitall@db/x", "senha do banco"),
    ("evolution_api_key", "licitall-dev-evolution-key", "EVOLUTION_API_KEY"),
    ("evolution_api_key", "curta", "EVOLUTION_API_KEY"),
    ("admin_emails", "", "ADMIN_EMAILS"),
    ("admin_emails", " , ", "ADMIN_EMAILS"),
])
def test_cada_fraqueza_e_apontada(campo, valor, trecho):
    problemas = production_problems(cfg(**{campo: valor}))
    assert len(problemas) == 1 and trecho in problemas[0]


def test_recusa_subir_e_lista_todos_os_problemas():
    with pytest.raises(RuntimeError) as exc:
        assert_production_ready(Settings(_env_file=None, app_env="production"))
    msg = str(exc.value)
    for trecho in ("COOKIE_SECURE", "senha do banco", "EVOLUTION_API_KEY", "ADMIN_EMAILS"):
        assert trecho in msg


def test_app_env_nao_diferencia_caixa():
    with pytest.raises(RuntimeError):
        assert_production_ready(Settings(_env_file=None, app_env="PRODUCTION"))
