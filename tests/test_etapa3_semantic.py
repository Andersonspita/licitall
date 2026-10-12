"""Etapa 3 do matching por item — Camada 3 (embeddings com cache por hash)."""

from __future__ import annotations

import asyncio

from src.matching.semantic import (
    content_hash,
    cosine,
    final_score,
    profile_description,
    resolve_vectors,
    sanitize_item_text,
    semantic_score,
)


class FakeEmbedder:
    def __init__(self):
        self.calls: list[list[str]] = []

    async def embed(self, texts):
        self.calls.append(list(texts))
        return [[float(len(t)), 1.0] for t in texts]


def test_sanitize_exemplo_do_edital():
    raw = (
        "ITEM 001 - AQUISIÇÃO DE PAPEL A4, 75G/M2, ALCALINO, EMBALAGEM COM 500 FOLHAS, "
        "CONFORME ESPECIFICAÇÕES DO TERMO DE REFERÊNCIA ANEXO I DO EDITAL Nº 23/2026. "
        "MARCA DE REFERÊNCIA REPORT OU SUPERIOR. PROCESSO ADM 4421."
    )
    assert sanitize_item_text(raw) == "papel a4 75g/m2 alcalino embalagem com 500 folhas"


def test_sanitize_limita_tamanho_e_trata_vazio():
    assert len(sanitize_item_text("x " * 1000)) <= 500
    assert sanitize_item_text(None) == ""


def test_variacoes_do_mesmo_item_geram_mesmo_hash():
    a = sanitize_item_text("ITEM 1 - Pneu 175/70 R14 radial, conforme edital")
    b = sanitize_item_text("item 22: PNEU 175/70 R14 RADIAL")
    assert a == b and content_hash(a) == content_hash(b)


def test_cache_nao_paga_duas_vezes_pelo_mesmo_texto():
    emb = FakeEmbedder()
    texts = ["pneu 175/70 r14 radial"] * 300 + ["papel a4"]
    res = asyncio.run(resolve_vectors(texts, {}, emb))
    assert res.api_texts_sent == 2 and res.api_calls == 1
    assert len(res.new_entries) == 2


def test_textos_ja_em_cache_nao_chamam_a_api():
    emb = FakeEmbedder()
    h = content_hash("papel a4")
    res = asyncio.run(resolve_vectors(["papel a4"], {h: [0.1, 0.2]}, emb))
    assert emb.calls == [] and res.vectors[h] == [0.1, 0.2] and not res.new_entries


def test_lotes_de_ate_batch_size():
    emb = FakeEmbedder()
    texts = [f"item distinto {i}" for i in range(250)]
    res = asyncio.run(resolve_vectors(texts, {}, emb, batch_size=100))
    assert [len(c) for c in emb.calls] == [100, 100, 50]
    assert res.api_calls == 3


def test_cosseno_e_score_semantico():
    assert cosine([1, 0], [1, 0]) == 1.0
    assert cosine([1, 0], [0, 1]) == 0.0
    assert cosine([], [1]) == 0.0
    assert semantic_score(1.0) == 25.0
    assert semantic_score(0.5) == 12.5
    assert semantic_score(-0.4) == 0.0


def test_descricao_do_perfil_e_score_final():
    assert profile_description("Linha Escolar", ["caderno"], ["lápis"]) == "linha escolar caderno lapis"
    assert profile_description("x", [], [], override="  Material de escritório  ") == "material de escritorio"
    assert final_score(40, 20, 10) == {"score_total": 70.0, "alerta": True}
    assert final_score(0, 20, 10)["alerta"] is False
    assert final_score(40, 35, 25)["score_total"] == 100.0
