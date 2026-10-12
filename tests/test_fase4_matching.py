"""Testes Fase 4+ — score explicável, elegibilidade YAML, match inverso."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.matching.cnae_map import infer_cnaes_from_text
from src.matching.eligibility import evaluate_eligibility, load_eligibility_config
from src.matching.scoring import matching_score, recommend, score_match
from src.matching.service import MatchmakingService, resolve_cnaes, resolve_exclusivo_me_epp


def test_infer_cnaes_ti():
    codes = infer_cnaes_from_text("Contratação de desenvolvimento de software e suporte de TI")
    assert "6201501" in codes or "6204000" in codes


def test_score_cnae_uf_me_epp():
    tender = {
        "cnaes_compativeis": ["6204000"],
        "uf": "DF",
        "municipio": "BRASILIA",
        "exclusivo_me_epp": True,
        "valor_total_estimado": 50000,
        "data_encerramento_propostas": (date.today() + timedelta(days=10)).isoformat(),
    }
    company = {
        "cnae_fiscal": 6204000,
        "cnaes_secundarios": [],
        "uf": "DF",
        "municipio": "BRASILIA",
        "porte": "MICRO EMPRESA",
        "situacao_cadastral": 2,
        "descricao_situacao_cadastral": "ATIVA",
    }
    breakdown = score_match(tender=tender, company=company)
    assert breakdown.total >= 85
    assert breakdown.recommendation == "BID"
    assert breakdown.as_factors()["cnae"] == 35.0


def test_score_penalizes_demais_on_exclusive_lot():
    tender = {
        "cnaes_compativeis": ["6204000"],
        "uf": "DF",
        "exclusivo_me_epp": True,
    }
    company = {
        "cnae_fiscal": 6204000,
        "uf": "DF",
        "porte": "DEMAIS",
        "situacao_cadastral": 2,
        "descricao_situacao_cadastral": "ATIVA",
    }
    score = matching_score(tender=tender, company=company)
    assert score < 50
    assert recommend(score, hard_fail=True) == "SKIP"


def test_score_breakdown_has_five_factors():
    tender = {
        "cnaes_compativeis": ["8121400"],
        "uf": "SP",
        "municipio": "SAO PAULO",
        "valor_total_estimado": 40000,
        "exclusivo_me_epp": True,
        "data_abertura_propostas": (date.today() + timedelta(days=14)).isoformat(),
        "data_encerramento_propostas": (date.today() + timedelta(days=20)).isoformat(),
    }
    company = {
        "cnae_fiscal": 8121400,
        "uf": "SP",
        "municipio": "SAO PAULO",
        "porte": "MICRO EMPRESA",
        "situacao_cadastral": 2,
        "descricao_situacao_cadastral": "ATIVA",
    }
    breakdown = score_match(tender=tender, company=company)
    factors = breakdown.as_factors()
    assert set(factors) == {"cnae", "geography", "porte", "economic", "deadline"}
    assert sum(factors.values()) == pytest.approx(breakdown.total, abs=0.2)


def test_resolve_cnaes_merges_objeto():
    tender = {"objeto_resumido": "serviços de limpeza predial", "cnaes_compativeis": []}
    assert "8121400" in resolve_cnaes(tender)


def test_resolve_exclusivo_from_beneficios():
    tender = {"beneficios_me_epp": {"exclusivo_me_epp": True}}
    assert resolve_exclusivo_me_epp(tender) is True


def test_eligibility_yaml_loads_and_hard_fails_demais():
    cfg = load_eligibility_config()
    assert cfg["version"] == 1
    assert any(r["id"] == "lote_exclusivo_me_epp" for r in cfg["rules"])

    verdict = evaluate_eligibility(
        tender={"exclusivo_me_epp": True, "uf": "SP"},
        company={
            "porte": "DEMAIS",
            "situacao_cadastral": 2,
            "descricao_situacao_cadastral": "ATIVA",
            "uf": "SP",
        },
    )
    assert verdict.eligible is False
    assert any("exclusivo" in f.lower() or "ME/EPP" in f for f in verdict.hard_failures)


def _verdict_164(**datas):
    return evaluate_eligibility(
        tender={"uf": "SP", **datas},
        company={
            "porte": "MICRO EMPRESA",
            "situacao_cadastral": 2,
            "descricao_situacao_cadastral": "ATIVA",
            "uf": "SP",
        },
        today=date.today(),
    )


def test_eligibility_art_164_alerta_quando_abertura_do_certame_e_proxima():
    hoje = date.today()
    verdict = _verdict_164(
        data_abertura_certame=(hoje + timedelta(days=1)).isoformat(),
        data_encerramento_propostas=(hoje + timedelta(days=5)).isoformat(),
    )
    assert verdict.eligible is True
    assert any("Art. 164" in w for w in verdict.soft_warnings)


def test_eligibility_art_164_usa_encerramento_e_nao_o_inicio_das_propostas():
    """O início do recebimento (ontem) não pode antecipar o prazo: a disputa abre quando ele encerra."""
    hoje = date.today()
    verdict = _verdict_164(
        data_abertura_propostas=(hoje - timedelta(days=1)).isoformat(),
        data_encerramento_propostas=(hoje + timedelta(days=15)).isoformat(),
    )
    assert verdict.eligible is True
    assert not any("Art. 164" in w for w in verdict.soft_warnings)


@pytest.mark.asyncio
async def test_matchmaking_with_stub_client():
    class StubClient:
        async def search_active(self, **kwargs):
            return [
                {
                    "cnpj": "12345678000199",
                    "razao_social": "LIMPEZA ME LTDA",
                    "uf": "SP",
                    "municipio": "SAO PAULO",
                    "porte": "MICRO EMPRESA",
                    "cnae_fiscal": 8121400,
                    "cnaes_secundarios": [],
                    "situacao_cadastral": 2,
                    "descricao_situacao_cadastral": "ATIVA",
                },
                {
                    "cnpj": "99888777000111",
                    "razao_social": "INATIVA SA",
                    "uf": "SP",
                    "porte": "DEMAIS",
                    "cnae_fiscal": 8121400,
                    "situacao_cadastral": 8,
                    "descricao_situacao_cadastral": "BAIXADA",
                },
            ]

        async def aclose(self):
            return None

    service = MatchmakingService(client=StubClient())  # type: ignore[arg-type]
    result = await service.match_tender(
        {
            "id_pncp": "00000000000000-1-000001/2026",
            "objeto_resumido": "serviços de limpeza",
            "uf": "SP",
            "municipio": "SAO PAULO",
            "beneficios_me_epp": {"exclusivo_me_epp": True},
            "valor_total_estimado": 40000,
            "data_encerramento_propostas": (date.today() + timedelta(days=12)).isoformat(),
        },
        min_score=40,
    )
    assert result.total_candidatos == 2
    assert len(result.matches) == 1
    assert result.matches[0].cnpj == "12345678000199"
    assert result.exclusivo_me_epp is True
    assert result.matches[0].recommendation in {"BID", "REVIEW"}
    assert result.matches[0].factors.cnae > 0


@pytest.mark.asyncio
async def test_match_company_inverse():
    class StubClient:
        async def get_company(self, cnpj: str):
            return {
                "cnpj": "12345678000199",
                "razao_social": "LIMPEZA ME LTDA",
                "uf": "SP",
                "municipio": "SAO PAULO",
                "porte": "MICRO EMPRESA",
                "cnae_fiscal": 8121400,
                "cnaes_secundarios": [],
                "situacao_cadastral": 2,
                "descricao_situacao_cadastral": "ATIVA",
            }

        async def aclose(self):
            return None

    service = MatchmakingService(client=StubClient())  # type: ignore[arg-type]
    tenders = [
        {
            "id_pncp": "00000000000000-1-000001/2026",
            "orgao_comprador": "PREFEITURA SP",
            "objeto_resumido": "serviços de limpeza predial",
            "uf": "SP",
            "municipio": "SAO PAULO",
            "valor_total_estimado": 35000,
            "beneficios_me_epp": {"exclusivo_me_epp": True},
            "data_encerramento_propostas": (date.today() + timedelta(days=15)).isoformat(),
        },
        {
            "id_pncp": "00000000000000-1-000002/2026",
            "orgao_comprador": "ORGAO TI",
            "objeto_resumido": "desenvolvimento de software sob demanda",
            "uf": "RJ",
            "valor_total_estimado": 200000,
            "data_encerramento_propostas": (date.today() + timedelta(days=20)).isoformat(),
        },
    ]
    result = await service.match_company(
        "12345678000199",
        tenders=tenders,
        min_score=30,
    )
    assert result.cnpj == "12345678000199"
    assert result.total_avaliados == 2
    assert len(result.opportunities) >= 1
    assert result.opportunities[0].id_pncp == "00000000000000-1-000001/2026"
    assert result.opportunities[0].recommendation in {"BID", "REVIEW"}


def test_ramo_incompativel_nao_vira_revisar_mesmo_com_uf_porte_valor_e_prazo():
    from src.matching.scoring import REVIEW_THRESHOLD, score_match

    empresa = {"uf": "BA", "municipio": "SALVADOR", "porte": "MICRO EMPRESA", "cnae_fiscal": 8121400}
    edital = {
        "cnaes_compativeis": ["4761003"], "uf": "BA", "municipio": "SALVADOR", "valor_total_estimado": 30000,
        "data_encerramento_propostas": (date.today() + timedelta(days=15)).isoformat(),
    }
    b = score_match(tender=edital, company=empresa)
    assert b.cnae == 0 and b.geography == 20  # os outros fatores continuam explicados
    assert b.total < REVIEW_THRESHOLD and b.recommendation == "SKIP"

    sem_cnae = score_match(tender={**edital, "cnaes_compativeis": []}, company=empresa)
    assert sem_cnae.recommendation in {"REVIEW", "BID"}  # ramo desconhecido continua para revisão


def test_generos_alimenticios_e_comercio_de_alimentos_nao_restaurante():
    from src.matching.cnae_map import infer_cnaes_from_text

    for objeto in ("Aquisição de gêneros alimentícios", "AQUISICAO DE GENEROS ALIMENTICIOS PARA A MERENDA"):
        assert "4639701" in infer_cnaes_from_text(objeto)
    assert "4639701" not in infer_cnaes_from_text("Fornecimento de refeições")


def test_servicos_juridicos_e_contabeis_tem_ramo_proprio():
    from src.matching.cnae_map import infer_cnaes_from_text

    assert "6911701" in infer_cnaes_from_text("Contratação de serviços de assessoria jurídica")
    assert "6911701" in infer_cnaes_from_text("Contratação de escritório de advocacia")
    assert "6920601" in infer_cnaes_from_text("Prestação de serviços de assessoria contábil")
    assert "6911701" not in infer_cnaes_from_text("Serviços de consultoria em gestão")


def test_ramo_desconhecido_nunca_e_bid_e_fica_abaixo_do_compativel():
    from src.matching.scoring import BID_THRESHOLD, REVIEW_THRESHOLD, score_match

    empresa = {"uf": "BA", "municipio": "SALVADOR", "porte": "DEMAIS", "cnae_fiscal": 6911701}
    base = {"uf": "BA", "municipio": "SALVADOR", "valor_total_estimado": 150000,
            "data_encerramento_propostas": (date.today() + timedelta(days=10)).isoformat()}
    generico = score_match(tender={**base, "cnaes_compativeis": []}, company=empresa)  # "Aquisição de bens comuns"
    compativel = score_match(tender={**base, "cnaes_compativeis": ["6911701"]}, company=empresa)
    assert REVIEW_THRESHOLD <= generico.total < BID_THRESHOLD and generico.recommendation == "REVIEW"
    assert compativel.recommendation == "BID" and compativel.total > generico.total


def test_advocacia_em_nome_de_lugar_nao_e_contratacao_de_advogado():
    from src.matching.cnae_map import infer_cnaes_from_text

    assert "6911701" not in infer_cnaes_from_text("Reforma do prédio da Escola Superior da Advocacia")
    assert "6911701" in infer_cnaes_from_text("Contratação de sociedade de advogados para representação judicial")


def test_mapa_casa_palavra_inteira_sem_acento_e_com_plural():
    from src.matching.cnae_map import infer_cnaes_from_text as f

    # falsos positivos reais do teste com a distribuidora de papelaria (BA, out/2026)
    assert f("BRACADEIRA PARA INJECAO") == []  # "cadeira" dentro de "braçadeira"
    assert f("módulos de folha de pagamento dos servidores") == []  # servidor público, não de rede
    assert f("CONFECÇÃO E O FORNECIMENTO DE PRÓTESES DENTÁRIAS") == []
    assert f("fornecimento de material e mão de obra") == []
    assert "4647801" in f("resma de papel A4") and "4647801" in f("MATERIAL DE EXPEDIENTE")
    assert "4751201" in f("Aquisição de computadores e impressoras") and "4751201" in f("servidores de rede")
    assert "4639701" in f("AQUISICAO DE GENEROS ALIMENTICIOS")


def test_cnae_principal_pesa_mais_que_secundario():
    from src.matching.scoring import WEIGHT_CNAE, WEIGHT_CNAE_SECUNDARIO, score_match

    empresa = {"uf": "BA", "porte": "DEMAIS", "cnae_fiscal": 4647801,
               "cnaes_secundarios": [{"codigo": 4754701, "descricao": "Móveis"}]}
    papelaria = score_match(tender={"uf": "BA", "cnaes_compativeis": ["4647801", "4761003"]}, company=empresa)
    moveis = score_match(tender={"uf": "BA", "cnaes_compativeis": ["3101200", "4754701"]}, company=empresa)
    assert papelaria.cnae == WEIGHT_CNAE and moveis.cnae == WEIGHT_CNAE_SECUNDARIO
    assert papelaria.total > moveis.total


def test_locacao_e_outro_ramo_que_venda():
    from src.matching.cnae_map import infer_cnaes_from_text as f

    locacao = f("LOCAÇÃO DE EQUIPAMENTOS DE IMPRESSÃO, INCLUINDO PLOTTER, SCANNER E IMPRESSORAS MULTIFUNCIONAIS")
    assert locacao == ["7733100"]  # aluguel de máquinas de escritório, não comércio de informática
    assert "4751201" in f("fornecimento de computadores de mesa, notebooks e impressoras")
    assert "4754701" not in f("fornecimento de computadores de mesa")  # "mesa" aqui não é móvel
    assert f("Locação de veículos tipo pick-up") == ["7711000", "7719599"]
    assert "4511101" in f("Aquisição de veículos 0 km")


def test_objeto_com_acento_em_entidade_html():
    from src.ingestion.service import map_pncp_item
    from src.matching.cnae_map import infer_cnaes_from_text

    bruto = "LOCAC&#807;A&#771;O DE IMPRESSORAS MULTIFUNCIONAIS"  # como veio do PNCP (Baixa Grande/BA, out/2026)
    assert infer_cnaes_from_text(bruto) == ["7733100"]
    assert map_pncp_item({"objetoCompra": bruto})["objeto_resumido"] == "LOCAÇÃO DE IMPRESSORAS MULTIFUNCIONAIS"


@pytest.mark.asyncio
async def test_ramo_principal_vem_antes_do_secundario_mesmo_com_nota_menor():
    """Teste real: papel A4 (73 pts) ficava abaixo de móveis (78) para uma distribuidora de papelaria."""
    from src.matching.service import MatchmakingService

    empresa = {"cnpj": "05195608000132", "razao_social": "PAPELARIA", "uf": "BA", "municipio": "FEIRA DE SANTANA",
               "porte": "DEMAIS", "cnae_fiscal": 4647801, "cnaes_secundarios": [{"codigo": 4754701, "descricao": "Móveis"}],
               "situacao_cadastral": 2, "descricao_situacao_cadastral": "ATIVA"}
    fim = (date.today() + timedelta(days=10)).isoformat()
    editais = [
        {"id_pncp": "moveis", "objeto_resumido": "Aquisição de mobiliário escolar", "uf": "BA", "valor_total_estimado": 2_000_000,
         "data_encerramento_propostas": fim},
        {"id_pncp": "papel", "objeto_resumido": "AQUISIÇÃO DE PAPEL A4", "uf": "BA", "valor_total_estimado": 20_000,
         "data_encerramento_propostas": fim},
        {"id_pncp": "persiana", "objeto_resumido": "Aquisição de persianas", "uf": "BA", "valor_total_estimado": 50_000,
         "data_encerramento_propostas": fim},
    ]
    r = await MatchmakingService().match_company("x", tenders=editais, company=empresa, min_score=0)
    por_id = {o.id_pncp: o for o in r.opportunities}
    assert por_id["papel"].score < por_id["moveis"].score  # o valor favorece móveis...
    assert [o.id_pncp for o in r.opportunities] == ["papel", "moveis", "persiana"]  # ...mas o ramo principal vem antes
    assert [o.ramo for o in r.opportunities] == ["principal", "secundario", "desconhecido"]


@pytest.mark.asyncio
async def test_valor_ate_80_mil_sem_exclusividade_declarada_alerta_e_rebaixa_demais():
    """LC 123 art. 48, I: até R$ 80 mil é exclusivo ME/EPP (salvo art. 49). Sem itens não se sabe se o edital declarou."""
    from src.matching.service import MatchmakingService

    fim = (date.today() + timedelta(days=10)).isoformat()
    edital = {"id_pncp": "a4", "objeto_resumido": "AQUISIÇÃO DE PAPEL A4", "uf": "BA", "valor_total_estimado": 8919.0,
              "data_encerramento_propostas": fim}
    base = {"cnpj": "1", "razao_social": "X", "uf": "BA", "cnae_fiscal": 4647801, "situacao_cadastral": 2,
            "descricao_situacao_cadastral": "ATIVA"}
    svc = MatchmakingService()
    demais = (await svc.match_company("1", tenders=[edital], company={**base, "porte": "DEMAIS"}, min_score=0)).opportunities[0]
    me = (await svc.match_company("1", tenders=[edital], company={**base, "porte": "MICRO EMPRESA"}, min_score=0)).opportunities[0]
    assert demais.recommendation == "REVIEW" and demais.eligibility_ok  # alerta, não bloqueia: a fonte não informou
    assert any("Art. 48" in w and "R$ 8.919,00" in w for w in demais.eligibility_warnings)
    assert me.recommendation == "BID" and not any("Art. 48" in w for w in me.eligibility_warnings)
    grande = (await svc.match_company("1", tenders=[{**edital, "valor_total_estimado": 300_000}],
                                      company={**base, "porte": "DEMAIS"}, min_score=0)).opportunities[0]
    assert not any("Art. 48" in w for w in grande.eligibility_warnings)
