"""Filtro de editais abertos: situação + prazo de encerramento futuro."""

from __future__ import annotations

from datetime import datetime

from src.ingestion.service import is_open_for_proposals

NOW = datetime(2026, 10, 11, 12, 0, 0)  # horário de Brasília, sem fuso (como o PNCP envia)


def _item(situacao="Divulgada no PNCP", encerra="2026-10-26T09:30:00"):
    d = {"situacaoCompraNome": situacao}
    if encerra is not None:
        d["dataEncerramentoProposta"] = encerra
    return d


def test_aberto_com_prazo_futuro():
    assert is_open_for_proposals(_item(), NOW)


def test_prazo_vencido_nao_e_aberto_mesmo_divulgada():
    assert not is_open_for_proposals(_item(encerra="2025-04-15T00:00:00"), NOW)


def test_encerra_exatamente_agora_ou_um_minuto_atras_nao_e_aberto():
    assert not is_open_for_proposals(_item(encerra="2026-10-11T12:00:00"), NOW)
    assert not is_open_for_proposals(_item(encerra="2026-10-11T11:59:00"), NOW)
    assert is_open_for_proposals(_item(encerra="2026-10-11T12:01:00"), NOW)


def test_situacao_fora_da_lista_nao_e_aberto():
    assert not is_open_for_proposals(_item(situacao="Revogada"), NOW)
    assert not is_open_for_proposals(_item(situacao="Suspensa"), NOW)


def test_sem_data_de_encerramento_e_aceito():
    assert is_open_for_proposals(_item(encerra=None), NOW)
    assert is_open_for_proposals(_item(encerra=""), NOW)


def test_sem_situacao_depende_so_do_prazo():
    assert is_open_for_proposals({"dataEncerramentoProposta": "2026-12-01T10:00:00"}, NOW)
    assert not is_open_for_proposals({"dataEncerramentoProposta": "2026-01-01T10:00:00"}, NOW)


def test_data_invalida_nao_derruba_a_ingestao():
    assert is_open_for_proposals(_item(encerra="não é data"), NOW)


def test_usa_relogio_real_quando_now_nao_e_informado():
    assert not is_open_for_proposals(_item(encerra="2000-01-01T00:00:00"))
    assert is_open_for_proposals(_item(encerra="2999-01-01T00:00:00"))
