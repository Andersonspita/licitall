"""Ramo do edital por significado quando o mapa de palavras-chave não identifica (objeto × CNAEs da empresa)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import text

from _integracao import TAG, ambiente  # noqa: F401
from src.matching import ramo_semantico as rs
from src.matching.scoring import BID_THRESHOLD, REVIEW_THRESHOLD, TETO_RAMO_DESCONHECIDO, score_match
from src.matching.semantic import content_hash

EMPRESA = {
    "cnpj": "42638444000105", "razao_social": "ADVOCACIA TESTE", "uf": "BA", "municipio": "SALVADOR", "porte": "DEMAIS",
    "cnae_fiscal": 6911701, "cnae_fiscal_descricao": "Serviços advocatícios", "cnaes_secundarios": [],
    "situacao_cadastral": 2, "descricao_situacao_cadastral": "ATIVA",
}
LIMIARES = (0.3, 0.8)


def _edital(n: int, objeto: str) -> dict:
    return {"id_pncp": f"{TAG}-r{n}", "objeto_resumido": objeto, "uf": "BA", "municipio": "SALVADOR",
            "valor_total_estimado": 50000, "data_encerramento_propostas": (date.today() + timedelta(days=10)).isoformat()}


class EmbedderFalso:
    """Vetor [1,0] para texto jurídico, [0,1] para o resto, [0.6,0.8] para "mediação" (zona cinzenta)."""

    backend, cache_key = "teste", f"teste:{TAG}"

    def __init__(self) -> None:
        self.textos: list[str] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.textos.extend(texts)
        out = []
        for t in texts:
            t = t.lower()
            out.append([1.0, 0.0] if ("advoc" in t or "judicia" in t) else [0.6, 0.8] if "media" in t else [0.0, 1.0])
        return out


def test_descricoes_cnae_principal_e_secundarios_sem_repetir():
    emp = {**EMPRESA, "cnaes_secundarios": [{"codigo": 1, "descricao": "Serviços advocatícios"}, {"codigo": 2, "descricao": "Perícia"}]}
    assert rs.descricoes_cnae(emp) == ["Serviços advocatícios", "Perícia"]
    assert rs.descricoes_cnae({}) == []


def test_classificar_so_decide_nos_extremos():
    assert rs.classificar(0.85, (0.76, 0.84)) == "compativel"
    assert rs.classificar(0.84, (0.76, 0.84)) == "compativel"
    assert rs.classificar(0.80, (0.76, 0.84)) == "incerto"
    assert rs.classificar(0.75, (0.76, 0.84)) == "incompativel"


def test_avaliar_ignora_edital_com_cnae_e_usa_o_cnae_mais_parecido():
    vet = {content_hash("Serviços advocatícios"): [1.0, 0.0], content_hash("Perícia"): [0.0, 1.0],
           content_hash(rs.texto_objeto(_edital(1, "Patrocínio de ações trabalhistas"))): [0.9, 0.1]}
    editais = [_edital(1, "Patrocínio de ações trabalhistas"), {**_edital(2, "Limpeza"), "cnaes_compativeis": ["8121400"]}]
    out = rs.avaliar(editais, ["Serviços advocatícios", "Perícia"], vet, LIMIARES)
    assert set(out) == {editais[0]["id_pncp"]}
    assert out[editais[0]["id_pncp"]].referencia == "Serviços advocatícios" and out[editais[0]["id_pncp"]].status == "compativel"


def test_pontuacao_por_status():
    def total(status):
        return score_match(tender={**_edital(1, "x"), "cnaes_compativeis": [],
                                   "ramo_semantico": {"status": status, "similaridade": 0.9, "referencia": "Serviços advocatícios"}},
                           company=EMPRESA)

    compat, incompat, incerto = total("compativel"), total("incompativel"), total("incerto")
    assert compat.cnae == 28 and compat.total >= BID_THRESHOLD and compat.recommendation == "BID"
    assert incompat.cnae == 0 and incompat.total < REVIEW_THRESHOLD and incompat.recommendation == "SKIP"
    assert incerto.total == TETO_RAMO_DESCONHECIDO and incerto.recommendation == "REVIEW"
    assert any("Serviços advocatícios" in m for m in compat.explanations)


@pytest.mark.asyncio
async def test_match_company_classifica_por_significado_e_reaproveita_cache(ambiente):
    from src.matching.service import MatchmakingService

    _, dbmod = ambiente
    editais = [_edital(1, "Patrocínio de ações judiciais trabalhistas"), _edital(2, "Aquisição de persianas"),
               _edital(3, "Câmara de mediação de conflitos"), {**_edital(4, "Serviços de limpeza predial")}]
    emb = EmbedderFalso()
    service = MatchmakingService()
    try:
        async with dbmod.get_session_factory()() as s:
            r = await service.match_company("x", tenders=editais, session=s, company=EMPRESA, min_score=0, limit=10,
                                            embedder=emb, ramo_limiares=LIMIARES)
            por_id = {o.id_pncp: o for o in r.opportunities}
            assert por_id[f"{TAG}-r1"].recommendation == "BID" and por_id[f"{TAG}-r1"].ramo_semantico["status"] == "compativel"
            assert por_id[f"{TAG}-r2"].recommendation == "SKIP" and por_id[f"{TAG}-r2"].ramo_semantico["status"] == "incompativel"
            assert por_id[f"{TAG}-r3"].recommendation == "REVIEW" and por_id[f"{TAG}-r3"].ramo_semantico["status"] == "incerto"
            assert por_id[f"{TAG}-r4"].ramo_semantico is None and por_id[f"{TAG}-r4"].recommendation == "SKIP"  # CNAE do mapa
            assert r.opportunities[0].id_pncp == f"{TAG}-r1"
            assert len(emb.textos) == 4  # 1 descrição de CNAE + 3 objetos sem ramo (limpeza veio do mapa)

            emb.textos.clear()
            await service.match_company("x", tenders=editais, session=s, company=EMPRESA, min_score=0, embedder=emb,
                                        ramo_limiares=LIMIARES)
            assert emb.textos == []  # tudo do cache
    finally:
        await service.aclose()
        async with dbmod.get_session_factory()() as s:
            await s.execute(text("delete from embeddings_cache where backend = :b"), {"b": emb.cache_key})
            await s.commit()


@pytest.mark.asyncio
async def test_falha_do_provedor_vira_aviso_e_match_segue(ambiente):
    from src.matching.service import MatchmakingService

    class Quebrado(EmbedderFalso):
        async def embed(self, texts):
            raise RuntimeError("cota esgotada")

    _, dbmod = ambiente
    service = MatchmakingService()
    try:
        async with dbmod.get_session_factory()() as s:
            r = await service.match_company("x", tenders=[_edital(1, "Aquisição de persianas")], session=s, company=EMPRESA,
                                            min_score=0, embedder=Quebrado(), ramo_limiares=LIMIARES)
    finally:
        await service.aclose()
    assert r.opportunities[0].recommendation == "REVIEW" and r.opportunities[0].score == TETO_RAMO_DESCONHECIDO
    assert any("cota esgotada" in a for a in r.avisos)


@pytest.mark.asyncio
async def test_sem_chave_de_embedding_avisa_e_nao_muda_nada(ambiente):
    from src.matching.service import MatchmakingService

    _, dbmod = ambiente
    service = MatchmakingService()
    try:
        async with dbmod.get_session_factory()() as s:  # conftest zera as chaves: provedor "hash"
            r = await service.match_company("x", tenders=[_edital(1, "Aquisição de persianas")], session=s, company=EMPRESA, min_score=0)
    finally:
        await service.aclose()
    assert r.opportunities[0].score == TETO_RAMO_DESCONHECIDO
    assert any("GEMINI_API_KEY" in a for a in r.avisos)
