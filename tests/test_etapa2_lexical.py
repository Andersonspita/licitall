"""Etapa 2 do matching por item — Camada 2 (CATMAT + léxico)."""

from __future__ import annotations

from src.matching.lexical import (
    score_layer2,
    term_present,
    tokenize,
    trigram_similarity,
)


def test_tokenize_remove_stopwords_licitatorias_e_plural():
    tokens = tokenize("Aquisição de cadeiras para o Pregão SRP - registro de preços")
    assert tokens == ["cadeira"]


def test_trigram_similarity_estilo_pg_trgm():
    assert trigram_similarity("casa", "casa") == 1.0
    assert trigram_similarity("abc", "xyz") == 0.0
    assert trigram_similarity("microcomputador", "microcomputado") > 0.6


def test_term_present_tolera_erro_de_digitacao_e_espaco():
    tokens = tokenize("MICRO COMPUTADO tipo desktop")
    assert term_present("microcomputador", tokens)
    assert term_present("desktop", tokens)
    assert not term_present("notebook", tokens)


def test_termo_curto_exige_igualdade_exata():
    assert not term_present("tela", tokenize("tecla numérica"))


def test_catmat_identico_vale_40():
    item = {"descricao": "Caneta esferográfica", "codigo_catmat_catser": 123}
    r = score_layer2(item, catalogo={123: 1.0})
    assert r.score_catmat == 40.0 and r.candidato


def test_catmat_respeita_peso_e_codigo_diferente_zera():
    item = {"descricao": "x", "codigo_catmat_catser": 123}
    assert score_layer2(item, catalogo={123: 0.5}).score_catmat == 20.0
    assert score_layer2(item, catalogo={999: 1.0}).score_catmat == 0.0


def test_lexico_trata_palavras_positivas_como_alternativas():
    item = {"descricao": "Notebook corporativo 16GB com monitor"}
    r = score_layer2(item, positivas=["notebook", "monitor", "impressora", "teclado"])
    assert r.score_lexico == 28.0  # 2 de 4 achadas: 60% + 20% = 80% de 35
    assert r.termos_encontrados == ["notebook", "monitor"]
    assert r.candidato


def test_obrigatoria_ausente_remove_candidatura_mesmo_com_catmat():
    item = {"descricao": "Cadeira de escritório", "codigo_catmat_catser": 7}
    r = score_layer2(item, obrigatorias=["giratória"], positivas=["cadeira"], catalogo={7: 1.0})
    assert r.obrigatorias_ausentes == ["giratória"]
    assert not r.candidato


def test_sem_nenhum_sinal_nao_e_candidato():
    r = score_layer2({"descricao": "Pneu 175/70"}, positivas=["notebook"])
    assert r.score_parcial == 0 and not r.candidato


def test_texto_do_objeto_tambem_conta():
    r = score_layer2({"descricao": "Item 01"}, positivas=["papel"], extra_text="Aquisição de papel A4")
    assert r.score_lexico == 35.0  # perfil de uma só palavra: achada = 100%


def test_credito_lexico_curva_e_limites():
    from src.matching.lexical import credito_lexico

    assert credito_lexico(0, 7) == 0.0 and credito_lexico(1, 0) == 0.0
    assert credito_lexico(1, 7) == 0.6 and credito_lexico(2, 7) == 0.8
    assert credito_lexico(3, 7) == 1.0 and credito_lexico(7, 7) == 1.0  # nunca passa de 100%
    assert credito_lexico(1, 1) == 1.0 and credito_lexico(1, 2) == 0.6 and credito_lexico(2, 2) == 1.0


def test_rota_candidates_antes_da_rota_generica():
    from _rotas import rota

    assert rota("POST", "/matching/profiles/abc/candidates") == "/matching/profiles/{profile_id}/candidates"
