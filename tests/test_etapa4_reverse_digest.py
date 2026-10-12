"""Busca reversa e digest agrupado por edital (lógica pura)."""

from __future__ import annotations

from src.matching.digest import build_digest_text, group_matches
from src.matching.reverse import accepts_uf


def _row(id_pncp, n, score, **kw):
    base = {"id_pncp": id_pncp, "numero_item": n, "score_total": score, "descricao": f"item {n}",
            "orgao": "Prefeitura X", "uf": "BA", "objeto": "Material de escritório"}
    base.update(kw)
    return base


def test_accepts_uf():
    assert accepts_uf([], "AC")
    assert accepts_uf(["BA", "SE"], "ba")
    assert not accepts_uf(["BA"], "AC")
    assert not accepts_uf(["BA"], None)


def test_agrupa_por_edital_e_ordena_pelo_melhor_score():
    rows = [_row("B", 1, 70), _row("A", 2, 90), _row("A", 1, 66), _row("A", 3, 80)]
    groups = group_matches(rows)
    assert [g["id_pncp"] for g in groups] == ["A", "B"]
    a = groups[0]
    assert a["qtd_itens"] == 3 and a["melhor_score"] == 90
    assert [i["numero_item"] for i in a["itens"]] == [2, 3, 1]


def test_digest_notifica_uma_vez_por_edital_nao_por_item():
    rows = [_row("A", n, 70 + n) for n in range(1, 24)]
    text = build_digest_text("Linha Escolar", group_matches(rows))
    assert "23 itens compatíveis" in text
    assert text.count("PNCP A") == 1
    assert "e mais 20" in text  # mostra 3 itens e resume o resto
    assert "Lei 8.906/1994" in text


def test_digest_singular_e_limite_top_n():
    rows = [_row("A", 1, 80), _row("B", 1, 75), _row("C", 1, 70)]
    text = build_digest_text("P", group_matches(rows), top_n=2)
    assert "1 item compatível" in text
    assert "PNCP C" not in text and "+1 edital(is) não exibido(s)" in text


def test_digest_vazio():
    assert "Nenhuma oportunidade nova" in build_digest_text("P", [])


def test_paginacao_limites():
    from src.matching.opportunities import clamp_page

    assert clamp_page(0, 20) == (1, 20)
    assert clamp_page(3, 1000) == (3, 100)
    assert clamp_page(-5, 0) == (1, 1)


def test_rota_oportunidades_antes_da_generica():
    from _rotas import rota

    assert rota("GET", "/matching/profiles/abc/oportunidades") == "/matching/profiles/{profile_id}/oportunidades"
