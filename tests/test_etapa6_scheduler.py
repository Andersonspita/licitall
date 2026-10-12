"""Envio agendado do digest — regras de horário (puras)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from src.matching.scheduler import BRT, is_due, next_run, normalize_phone, parse_horario


def brt(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=BRT)


def test_parse_horario_valido_e_invalido():
    assert parse_horario("08:00") == (8, 0)
    assert parse_horario("23:59") == (23, 59)
    for bad in ("8:00", "24:00", "12:60", "", "abc"):
        with pytest.raises(ValueError):
            parse_horario(bad)


def test_normalize_phone():
    assert normalize_phone("+55 (71) 99999-9999") == "5571999999999"
    for bad in ("123", "1" * 16, ""):
        with pytest.raises(ValueError):
            normalize_phone(bad)


def test_nao_vence_antes_do_horario():
    now = brt(2026, 10, 12, 7, 59)
    assert not is_due(horario="08:00", now=now, ultimo_envio_dia=None, ultima_tentativa=None)


def test_vence_no_horario_e_depois():
    assert is_due(horario="08:00", now=brt(2026, 10, 12, 8, 0), ultimo_envio_dia=None, ultima_tentativa=None)
    assert is_due(horario="08:00", now=brt(2026, 10, 12, 15, 30), ultimo_envio_dia=None, ultima_tentativa=None)


def test_nao_repete_no_mesmo_dia_mas_vence_no_dia_seguinte():
    now = brt(2026, 10, 12, 9, 0)
    assert not is_due(horario="08:00", now=now, ultimo_envio_dia=date(2026, 10, 12), ultima_tentativa=None)
    assert is_due(horario="08:00", now=brt(2026, 10, 13, 8, 5), ultimo_envio_dia=date(2026, 10, 12), ultima_tentativa=None)


def test_retentativa_so_apos_o_intervalo():
    now = brt(2026, 10, 12, 9, 0)
    recente = now - timedelta(minutes=5)
    antiga = now - timedelta(minutes=16)
    assert not is_due(horario="08:00", now=now, ultimo_envio_dia=None, ultima_tentativa=recente)
    assert is_due(horario="08:00", now=now, ultimo_envio_dia=None, ultima_tentativa=antiga)


def test_dia_e_calculado_em_horario_de_brasilia_nao_utc():
    # 01:30 UTC de 13/10 ainda é 22:30 de 12/10 em Brasília
    now = datetime(2026, 10, 13, 1, 30, tzinfo=timezone.utc)
    assert is_due(horario="22:00", now=now, ultimo_envio_dia=date(2026, 10, 11), ultima_tentativa=None)
    assert not is_due(horario="22:00", now=now, ultimo_envio_dia=date(2026, 10, 12), ultima_tentativa=None)


def test_next_run():
    assert next_run("08:00", brt(2026, 10, 12, 7, 0), None) == brt(2026, 10, 12, 8, 0)
    assert next_run("08:00", brt(2026, 10, 12, 9, 0), date(2026, 10, 12)) == brt(2026, 10, 13, 8, 0)
    now = brt(2026, 10, 12, 9, 0)
    assert next_run("08:00", now, None) == now  # vencido e não enviado: sai no próximo ciclo


def test_rotas_antes_da_generica():
    from src.main import app

    paths = [r.path for r in app.routes]
    generic = paths.index("/matching/{id_pncp:path}")
    assert paths.index("/matching/profiles/{profile_id}/agendamento") < generic
    assert paths.index("/matching/digest/run-due") < generic


def test_passed_today():
    from src.matching.scheduler import passed_today

    assert passed_today("08:00", brt(2026, 10, 12, 8, 0))
    assert passed_today("08:00", brt(2026, 10, 12, 19, 25))
    assert not passed_today("08:00", brt(2026, 10, 12, 7, 59))
