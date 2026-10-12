"""Match inverso lendo `tender_ingest` real: só editais abertos, itens do banco na inferência de CNAE."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from _integracao import TAG, ambiente  # noqa: F401
from src.ingestion.service import _BRT
from src.matching.cnae_map import infer_cnaes_from_text
from src.matching.service import MatchmakingService
from src.models.tables import TenderIngest, TenderItemRow

UF = "ZZ"  # UF inexistente isola o teste dos editais que já estiverem no banco
GENERICO = "Aquisição conforme termo de referência"
EMPRESA = {
    "cnpj": "12345678000199", "razao_social": "LIMPEZA ME LTDA", "uf": UF, "municipio": "CIDADE",
    "porte": "MICRO EMPRESA", "cnae_fiscal": 8121400, "cnaes_secundarios": [],
    "situacao_cadastral": 2, "descricao_situacao_cadastral": "ATIVA",
}


def _id(n: int) -> str:
    return f"{TAG}-{n}"


def _edital(n: int, *, dias: int | None, situacao: str = "Divulgada no PNCP", objeto: str = GENERICO, uf: str = UF):
    agora = datetime.now(_BRT).replace(tzinfo=None)
    return TenderIngest(
        id_pncp=_id(n), uf=uf, municipio="CIDADE", situacao=situacao, objeto_resumido=objeto,
        orgao_comprador=f"Órgão {n}", valor_total_estimado=50000.0,
        data_encerramento_propostas=None if dias is None else agora + timedelta(days=dias),
    )


@pytest.fixture
async def editais(ambiente):
    _, dbmod = ambiente
    async with dbmod.get_session_factory()() as s:
        s.add_all([
            _edital(1, dias=20),                                   # aberto, só itens indicam o ramo
            _edital(2, dias=-1),                                   # "Divulgada" mas prazo vencido
            _edital(3, dias=10, situacao="Encerrada"),             # situação fechada
            _edital(4, dias=None, objeto="serviços de limpeza predial"),  # sem data: aceito
            _edital(5, dias=5, objeto="serviços de limpeza predial"),
            _edital(6, dias=5, uf="ZY"),                           # outra UF
        ])
        s.add(TenderItemRow(id_pncp=_id(1), numero_item=1, descricao="Serviço de limpeza predial com fornecimento de material"))
        s.add(TenderItemRow(id_pncp=_id(1), numero_item=2, descricao="Saco de lixo", exclusivo_me_epp=True))
        await s.commit()
    yield dbmod
    async with dbmod.get_session_factory()() as s:
        await s.execute(text("delete from itens_contratacao where id_pncp like :p"), {"p": f"{TAG}-%"})
        await s.execute(text("delete from tender_ingest where id_pncp like :p"), {"p": f"{TAG}-%"})
        await s.commit()


@pytest.mark.asyncio
async def test_lista_so_abertos_que_encerram_primeiro_e_com_itens(editais):
    service = MatchmakingService()
    try:
        async with editais.get_session_factory()() as s:
            lista = await service.list_open_tenders(s, uf=UF)
    finally:
        await service.aclose()
    assert [t["id_pncp"] for t in lista] == [_id(5), _id(1), _id(4)]  # sem data por último
    item = next(t for t in lista if t["id_pncp"] == _id(1))
    assert not infer_cnaes_from_text(GENERICO)  # o objeto sozinho não indica o ramo...
    assert "8121400" in item["cnaes_compativeis"]  # ...os itens do banco indicam
    assert item["exclusivo_me_epp"] is False  # um item exclusivo não torna o edital inteiro exclusivo


@pytest.mark.asyncio
async def test_match_company_pelo_banco_ignora_vencidos(editais):
    service = MatchmakingService()
    try:
        async with editais.get_session_factory()() as s:
            result = await service.match_company("12345678000199", session=s, uf_filter=UF, min_score=0, company=EMPRESA)
    finally:
        await service.aclose()
    assert result.total_avaliados == 3
    ids = {o.id_pncp for o in result.opportunities}
    assert ids == {_id(1), _id(4), _id(5)}
    assert all(o.factors.cnae == 35 for o in result.opportunities)


@pytest.mark.asyncio
async def test_upsert_do_sync_grava_data_sem_fuso(editais):
    """Regressão: com o SQLModel recente, `datetime` sem fuso fazia todo upsert do sync falhar."""
    from src.ingestion.service import map_pncp_item, upsert_tender

    item = {  # formato da consulta do PNCP: horário de Brasília sem fuso
        "numeroControlePNCP": _id(99), "unidadeOrgao": {"ufSigla": UF}, "situacaoCompraNome": "Divulgada no PNCP",
        "dataPublicacaoPncp": "2029-12-20T08:00:00", "dataEncerramentoProposta": "2030-01-02T09:30:00",
    }
    async with editais.get_session_factory()() as s:
        await upsert_tender(s, map_pncp_item(item))
        await upsert_tender(s, map_pncp_item(item))  # idempotente (ON CONFLICT)
        await s.commit()
        rows = (await s.execute(text("select data_encerramento_propostas from tender_ingest where id_pncp = :i"), {"i": _id(99)})).all()
    assert rows == [(datetime(2030, 1, 2, 9, 30),)]
