"""Itens do edital: espelho do Compras.gov.br primeiro, API do PNCP como reserva (servidores simulados)."""

from __future__ import annotations

import httpx
import pytest

from src.ingestion import client as cli
from src.ingestion.client import PncpClient, PncpError
from src.ingestion.service import map_item_row

ID = "05193073000160-1-000036/2026"
ITEM_COMPRAS = {
    "numeroItemPncp": 3, "numeroItemCompra": 3, "descricaoResumida": "Papel sulfite A4", "descricaodetalhada": None,
    "materialOuServico": "M", "codItemCatalogo": 150123, "quantidade": 10.0, "unidadeMedida": "RESMA",
    "valorUnitarioEstimado": 25.5, "valorTotal": 255.0, "tipoBeneficioNome": "Participação exclusiva para ME/EPP",
}


@pytest.fixture(autouse=True)
def _sem_pausa():
    cli._core_indisponivel_ate = 0.0
    yield
    cli._core_indisponivel_ate = 0.0


def _cliente(handler) -> PncpClient:
    chamadas: list[str] = []

    def registra(req: httpx.Request) -> httpx.Response:
        chamadas.append("compras" if "dadosabertos" in req.url.host else "core")
        return handler(req)

    c = PncpClient(client=httpx.AsyncClient(transport=httpx.MockTransport(registra)))
    c.chamadas = chamadas  # type: ignore[attr-defined]
    return c


def _json(dados, **extra):
    return httpx.Response(200, json=dados, **extra)


@pytest.mark.asyncio
async def test_usa_o_espelho_e_converte_os_campos():
    c = _cliente(lambda r: _json({"resultado": [ITEM_COMPRAS], "paginasRestantes": 0}))
    itens = await c.get_itens(ID)
    assert c.chamadas == ["compras"]  # type: ignore[attr-defined]
    row = map_item_row(itens[0], ID)
    assert row["numero_item"] == 3 and row["descricao"] == "Papel sulfite A4" and row["tipo"] == "M"
    assert row["codigo_catmat_catser"] == 150123 and row["quantidade"] == 10.0 and row["unidade_medida"] == "RESMA"
    assert row["exclusivo_me_epp"] is True


@pytest.mark.asyncio
async def test_pagina_ate_acabar():
    paginas = {"1": {"resultado": [ITEM_COMPRAS], "paginasRestantes": 1}, "2": {"resultado": [{**ITEM_COMPRAS, "numeroItemPncp": 4}], "paginasRestantes": 0}}
    c = _cliente(lambda r: _json(paginas[r.url.params["pagina"]]))
    assert [i["numeroItem"] for i in await c.get_itens(ID)] == [3, 4]


@pytest.mark.asyncio
async def test_cai_para_a_api_do_pncp_quando_o_espelho_falha():
    def h(r):
        return httpx.Response(404, text="x") if "dadosabertos" in r.url.host else _json([{"numeroItem": 1, "descricao": "do pncp"}])

    c = _cliente(h)
    assert (await c.get_itens(ID))[0]["descricao"] == "do pncp"
    assert c.chamadas == ["compras", "core"]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_espelho_vazio_e_pncp_fora_vira_lista_vazia_e_pausa_o_pncp():
    def h(r):
        if "dadosabertos" in r.url.host:
            return _json({"resultado": [], "paginasRestantes": 0})
        raise httpx.ReadTimeout("sem resposta")

    c = _cliente(h)
    assert await c.get_itens(ID) == []
    assert await c.get_itens(ID) == []  # segunda vez: não tenta o PNCP de novo
    assert c.chamadas == ["compras", "core", "compras"]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_falha_nas_duas_fontes_gera_erro():
    def h(r):
        if "dadosabertos" in r.url.host:
            return httpx.Response(404, text="x")
        raise httpx.ReadTimeout("sem resposta")

    with pytest.raises(httpx.ReadTimeout):
        await _cliente(h).get_itens(ID)
    with pytest.raises(PncpError, match="em pausa"):  # já em pausa: falha rápido, sem esperar o timeout
        await _cliente(h).get_itens(ID)
