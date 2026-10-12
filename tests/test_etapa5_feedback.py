"""Feedback relevante/irrelevante e sugestão de termos negativos (lógica pura)."""

from __future__ import annotations

from src.matching.feedback import suggest_negative_terms


def test_sugere_palavras_novas_da_descricao():
    r = suggest_negative_terms(
        "Locação de cadeiras giratórias para eventos",
        known_terms=["cadeira"],
    )
    assert "locação" in r and "eventos" in r and "giratórias" in r
    assert "cadeiras" not in r  # mesma raiz de "cadeira"
    assert "para" not in r and "de" not in r


def test_nao_sugere_palavra_que_o_perfil_ja_usa():
    r = suggest_negative_terms("Papel A4 alcalino resma", known_terms=["papel", "resmas"])
    assert "papel" not in r and "resma" not in r and "alcalino" in r


def test_nao_sugere_palavra_presente_em_item_marcado_como_relevante():
    r = suggest_negative_terms(
        "Notebook usado recondicionado",
        known_terms=["notebook"],
        favorite_descriptions=["Notebook novo 16GB recondicionado"],
    )
    assert r == ["usado"]


def test_ignora_numeros_codigos_e_termos_curtos():
    r = suggest_negative_terms("Pneu 175/70 R14 ref ABC123 radial", known_terms=[])
    assert r == ["pneu", "radial"]


def test_limite_e_sem_repeticao():
    r = suggest_negative_terms("alfa alfa alfas beta gama delta epsilon zeta eta", known_terms=[], limit=3)
    assert r == ["alfa", "beta", "gama"]


def test_descricao_vazia():
    assert suggest_negative_terms("", known_terms=["x"]) == []


def test_rotas_de_feedback_antes_da_generica():
    from src.main import app

    paths = [r.path for r in app.routes]
    generic = paths.index("/matching/{id_pncp:path}")
    assert paths.index("/matching/matches/{match_id}/feedback") < generic
    assert paths.index("/matching/profiles/{profile_id}/palavras") < generic
