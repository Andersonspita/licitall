"""Art. 164: a data de abertura do certame não é o início do recebimento de propostas."""

from __future__ import annotations

from datetime import datetime, timedelta

from src.compliance import data_abertura_certame
from src.models.tables import TenderIngest
from src.tenders.service import art164_meta


def test_helper_prefere_certame_explicito_depois_encerramento_depois_inicio():
    t = {
        "data_abertura_certame": "2026-11-03",
        "data_encerramento_propostas": "2026-10-22T09:00:00",
        "data_abertura_propostas": "2026-10-09T08:00:00",
    }
    assert str(data_abertura_certame(t)) == "2026-11-03"
    t.pop("data_abertura_certame")
    assert str(data_abertura_certame(t)) == "2026-10-22"
    t.pop("data_encerramento_propostas")
    assert str(data_abertura_certame(t)) == "2026-10-09"


def test_helper_aceita_datetime_ignora_vazios_e_invalidos():
    assert data_abertura_certame({}) is None
    assert data_abertura_certame({"data_encerramento_propostas": ""}) is None
    assert str(data_abertura_certame({"data_encerramento_propostas": datetime(2026, 10, 22, 9, 0)})) == "2026-10-22"
    # data inválida cai para a próxima fonte
    assert str(data_abertura_certame({"data_encerramento_propostas": "lixo", "data_abertura_propostas": "2026-10-09"})) == "2026-10-09"


def test_art164_meta_edital_recem_publicado_nao_aparece_como_vencido():
    """Caso real do PNCP: recebimento começou há 2 dias e encerra em 13; o prazo de impugnação está à frente."""
    row = TenderIngest(
        id_pncp="x",
        data_abertura_propostas=datetime.now() - timedelta(days=2),
        data_encerramento_propostas=datetime.now() + timedelta(days=13),
    )
    meta = art164_meta(row)
    assert meta["vencido"] is False
    assert meta["dias_uteis_restantes"] > 0
    assert meta["fonte"] == "calculado_art_164_encerramento_propostas"


def test_art164_meta_conta_a_partir_do_encerramento():
    encerra = datetime.now() + timedelta(days=4)
    meta = art164_meta(TenderIngest(id_pncp="x", data_encerramento_propostas=encerra))
    assert meta["tem_abertura"] is True
    assert meta["data_abertura"] == encerra.date().isoformat()
    assert meta["limite_impugnacao"] < meta["data_abertura"]  # o limite é 3 dias úteis ANTES da abertura


def test_art164_meta_sem_nenhuma_data():
    assert art164_meta(TenderIngest(id_pncp="x"))["tem_abertura"] is False
