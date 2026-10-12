"""Regras puras de habilitação (sem banco)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from src.habilitacao.logic import (
    CERTIDOES_PADRAO,
    hoje_brt,
    limpar,
    situacao_certidao,
    validar_data_emissao,
    validar_quantidade,
    validar_validade,
)

HOJE = date(2026, 10, 12)


def test_sem_data():
    assert situacao_certidao(None, HOJE) == {"situacao": "sem_data", "dias": None}


@pytest.mark.parametrize("delta,esperado", [
    (-30, "vencida"), (-1, "vencida"),
    (0, "vence_em_breve"), (1, "vence_em_breve"), (15, "vence_em_breve"),
    (16, "valida"), (400, "valida"),
])
def test_situacao_pelos_dias(delta, esperado):
    r = situacao_certidao(HOJE + timedelta(days=delta), HOJE)
    assert r == {"situacao": esperado, "dias": delta}


def test_aviso_personalizado_e_minimo_de_1_dia():
    d = HOJE + timedelta(days=40)
    assert situacao_certidao(d, HOJE, 30)["situacao"] == "valida"
    assert situacao_certidao(d, HOJE, 45)["situacao"] == "vence_em_breve"
    assert situacao_certidao(HOJE + timedelta(days=1), HOJE, 0)["situacao"] == "vence_em_breve"  # aviso < 1 vira 1


def test_hoje_usa_horario_de_brasilia_e_nao_utc():
    # 01:30 UTC de 13/10 ainda é 22:30 de 12/10 em Brasília
    assert hoje_brt(datetime(2026, 10, 13, 1, 30, tzinfo=timezone.utc)) == date(2026, 10, 12)
    assert hoje_brt(datetime(2026, 10, 13, 3, 0, tzinfo=timezone.utc)) == date(2026, 10, 13)


def test_validade_plausivel():
    validar_validade(None, HOJE)
    validar_validade(HOJE, HOJE)
    validar_validade(HOJE + timedelta(days=365 * 5), HOJE)
    for ruim in (date(1989, 12, 31), HOJE + timedelta(days=366 * 21)):
        with pytest.raises(ValueError):
            validar_validade(ruim, HOJE)


def test_data_de_emissao():
    validar_data_emissao(None, HOJE)
    validar_data_emissao(date(2020, 1, 1), HOJE)
    validar_data_emissao(HOJE, HOJE)
    for ruim in (date(1949, 12, 31), HOJE + timedelta(days=5)):
        with pytest.raises(ValueError):
            validar_data_emissao(ruim, HOJE)


def test_quantidade():
    for ok in (None, 0, 0.5, 1_000_000):
        validar_quantidade(ok)
    for ruim in (-1, float("nan"), float("inf"), 1e13):
        with pytest.raises(ValueError):
            validar_quantidade(ruim)


def test_limpar():
    assert limpar("  Pavimentação   asfáltica \n") == "Pavimentação asfáltica"
    assert limpar("   ") is None and limpar(None) is None and limpar("") is None


def test_lista_padrao_sem_duplicados():
    assert len(CERTIDOES_PADRAO) == 7 and len(set(CERTIDOES_PADRAO)) == 7
