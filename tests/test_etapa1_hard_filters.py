"""Etapa 1 do matching por item — filtros rígidos (Camada 1)."""

from __future__ import annotations

from src.matching.hard_filters import (
    ProfileFilters,
    evaluate_hard_filters,
    filter_items,
    normalize_text,
    term_matches,
)


def _item(**kw):
    base = {"descricao": "Cadeira giratória de escritório", "valor_unitario_estimado": 500.0}
    base.update(kw)
    return base


def test_normalize_text_remove_acentos_e_caixa():
    assert normalize_text("  Madeira   MACIÇA ") == "madeira maciça".replace("ç", "c")


def test_term_matches_palavra_inteira_e_plural():
    text = normalize_text("Serviço de reformas prediais")
    assert term_matches("reforma", text)
    assert not term_matches("form", text)
    assert term_matches("madeira maciça", normalize_text("MESA DE MADEIRA MACICA"))


def test_perfil_sem_restricoes_aprova():
    assert evaluate_hard_filters(_item(), ProfileFilters(), uf="BA").passed


def test_uf_fora_do_perfil_elimina():
    result = evaluate_hard_filters(_item(), ProfileFilters(ufs_permitidas=("BA", "SE")), uf="AC")
    assert not result.passed
    assert "UF AC" in result.reasons[0]


def test_uf_dentro_do_perfil_aprova_sem_depender_de_caixa():
    assert evaluate_hard_filters(_item(), ProfileFilters(ufs_permitidas=("BA",)), uf="ba").passed


def test_faixa_de_valor():
    profile = ProfileFilters(valor_minimo_item=100, valor_maximo_item=1000)
    assert evaluate_hard_filters(_item(valor_unitario_estimado=500), profile).passed
    assert not evaluate_hard_filters(_item(valor_unitario_estimado=50), profile).passed
    assert not evaluate_hard_filters(_item(valor_unitario_estimado=5000), profile).passed


def test_valor_desconhecido_nao_elimina():
    profile = ProfileFilters(valor_minimo_item=100, valor_maximo_item=1000)
    item = _item(valor_unitario_estimado=None, valor_total_estimado=None)
    assert evaluate_hard_filters(item, profile).passed


def test_apenas_me_epp_exige_item_exclusivo():
    profile = ProfileFilters(apenas_me_epp=True)
    assert not evaluate_hard_filters(_item(exclusivo_me_epp=False), profile).passed
    assert evaluate_hard_filters(_item(exclusivo_me_epp=True), profile).passed


def test_termo_negativo_na_descricao_ou_no_objeto():
    profile = ProfileFilters(termos_negativos=("locação", "reforma"))
    assert not evaluate_hard_filters(_item(descricao="LOCACAO de cadeiras"), profile).passed
    assert not evaluate_hard_filters(_item(), profile, extra_text="Reforma do prédio").passed
    assert evaluate_hard_filters(_item(), profile, extra_text="Aquisição de mobiliário").passed


def test_motivos_acumulam_e_filter_items_separa():
    profile = ProfileFilters(ufs_permitidas=("BA",), valor_maximo_item=100)
    result = evaluate_hard_filters(_item(valor_unitario_estimado=500), profile, uf="AC")
    assert len(result.reasons) == 2

    kept, dropped = filter_items(
        [_item(valor_unitario_estimado=50), _item(valor_unitario_estimado=500)], profile, uf="BA"
    )
    assert len(kept) == 1 and len(dropped) == 1


def test_map_item_row_extrai_campos_do_pncp():
    from src.ingestion.service import map_item_row

    raw = {
        "numeroItem": 3,
        "descricao": "Papel A4 75g",
        "quantidade": 100,
        "unidadeMedida": "Resma",
        "valorUnitarioEstimado": 25.5,
        "valorTotal": 2550,
        "materialOuServico": "M",
        "codigoItem": "123456",
    }
    row = map_item_row(raw, "00000000000191-1-000001/2026")
    assert row["numero_item"] == 3
    assert row["tipo"] == "M"
    assert row["codigo_catmat_catser"] == 123456
    assert row["valor_unitario_estimado"] == 25.5
    assert row["id_pncp"] == "00000000000191-1-000001/2026"


def test_map_item_row_ignora_item_sem_numero():
    from src.ingestion.service import map_item_row

    assert map_item_row({"descricao": "sem número"}, "x") is None


def test_rotas_de_perfil_antes_da_rota_generica():
    """/matching/{id_pncp:path} engoliria /matching/profiles se vier antes."""
    from src.main import app

    paths = [r.path for r in app.routes]
    generic = paths.index("/matching/{id_pncp:path}")
    assert paths.index("/matching/profiles") < generic
    assert paths.index("/matching/profiles/{profile_id}/filter") < generic
