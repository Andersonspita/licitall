"""Certidões e atestados no banco, isolados por empresa (PostgreSQL real)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import pytest

from _integracao import _registrar, ambiente  # noqa: F401
from src.habilitacao.logic import CERTIDOES_PADRAO, hoje_brt


def _dia(n: int) -> str:
    return (hoje_brt() + timedelta(days=n)).isoformat()


async def _item(c, nome_parcial: str) -> dict:
    itens = (await c.get("/certidoes")).json()["itens"]
    return next(i for i in itens if nome_parcial in i["nome"])


@pytest.mark.asyncio
async def test_sem_login_tudo_fechado(ambiente):
    novo, _ = ambiente
    async with novo() as c:
        for metodo, caminho in (("get", "/certidoes"), ("get", "/certidoes/resumo"), ("get", "/atestados"),
                                ("post", "/certidoes"), ("post", "/atestados"), ("put", f"/certidoes/{uuid.uuid4()}"),
                                ("delete", f"/atestados/{uuid.uuid4()}")):
            assert (await getattr(c, metodo)(caminho)).status_code == 401, (metodo, caminho)


@pytest.mark.asyncio
async def test_lista_padrao_e_criada_uma_vez_mesmo_com_acessos_simultaneos(ambiente):
    novo, _ = ambiente
    async with novo() as c:
        await _registrar(c, "pad")
        respostas = await asyncio.gather(*[c.get("/certidoes") for _ in range(6)])
        assert all(r.status_code == 200 for r in respostas)
        itens = (await c.get("/certidoes")).json()["itens"]
        assert sorted(i["nome"] for i in itens) == sorted(CERTIDOES_PADRAO)  # 7, sem duplicar
        assert all(i["padrao"] and i["situacao"] == "sem_data" for i in itens)
        assert (await c.get("/certidoes/resumo")).json()["sem_data"] == 7


@pytest.mark.asyncio
async def test_situacao_pela_validade_e_aviso_configuravel(ambiente):
    novo, _ = ambiente
    async with novo() as c:
        await _registrar(c, "sit")
        federal, fgts, cndt = await _item(c, "Federal"), await _item(c, "FGTS"), await _item(c, "CNDT")
        for item, dias in ((federal, -3), (fgts, 5), (cndt, 90)):
            r = await c.put(f"/certidoes/{item['id']}", json={"validade": _dia(dias), "observacao": "  conferida  em  cartório "})
            assert r.status_code == 200
        assert r.json()["observacao"] == "conferida em cartório"  # espaços normalizados

        res = (await c.get("/certidoes/resumo")).json()
        assert (res["vencida"], res["vence_em_breve"], res["valida"], res["sem_data"]) == (1, 1, 1, 4)
        assert [a["nome"] for a in res["atencao"]] == [federal["nome"], fgts["nome"]]  # mais urgente primeiro
        assert [a["dias"] for a in res["atencao"]] == [-3, 5]

        largo = (await c.get("/certidoes/resumo?aviso_dias=90")).json()
        assert largo["vence_em_breve"] == 2 and largo["valida"] == 0  # a de 90 dias entra no aviso (limite máximo)
        assert (await c.get("/certidoes?aviso_dias=0")).status_code == 422
        assert (await c.get("/certidoes?aviso_dias=91")).status_code == 422

        # limpar a data volta a "sem data"
        r = await c.put(f"/certidoes/{federal['id']}", json={"validade": None})
        assert r.json()["situacao"] == "sem_data" and r.json()["validade"] is None


@pytest.mark.asyncio
async def test_validacoes_da_certidao(ambiente):
    novo, _ = ambiente
    async with novo() as c:
        await _registrar(c, "val")
        item = await _item(c, "Federal")
        assert (await c.put(f"/certidoes/{item['id']}", json={"validade": "1980-01-01"})).status_code == 422
        assert (await c.put(f"/certidoes/{item['id']}", json={"validade": _dia(366 * 25)})).status_code == 422
        assert (await c.put(f"/certidoes/{item['id']}", json={"validade": "31/12/2026"})).status_code == 422  # formato
        assert (await c.put(f"/certidoes/{item['id']}", json={"observacao": "x" * 501})).status_code == 422
        assert (await c.put(f"/certidoes/{uuid.uuid4()}", json={})).status_code == 404
        assert (await c.put("/certidoes/nao-e-uuid", json={})).status_code == 422
        assert (await _item(c, "Federal"))["validade"] is None  # nada foi gravado


@pytest.mark.asyncio
async def test_documento_proprio_cria_duplica_e_remove(ambiente, monkeypatch):
    novo, _ = ambiente
    import src.habilitacao.routes as rotas

    async with novo() as c:
        await _registrar(c, "prop")
        r = await c.post("/certidoes", json={"nome": "  Certidão  de acervo técnico (CREA) "})
        assert r.status_code == 201 and r.json()["nome"] == "Certidão de acervo técnico (CREA)" and r.json()["padrao"] is False
        assert (await c.post("/certidoes", json={"nome": "Certidão de acervo técnico (CREA)"})).status_code == 409
        assert (await c.post("/certidoes", json={"nome": "CND Federal (Receita/PGFN)"})).status_code == 409  # igual a um padrão
        assert (await c.post("/certidoes", json={"nome": "x"})).status_code == 422

        padrao = await _item(c, "Federal")
        assert (await c.delete(f"/certidoes/{padrao['id']}")).status_code == 409  # lista oficial não se remove
        assert (await c.delete(f"/certidoes/{r.json()['id']}")).status_code == 204
        assert (await c.delete(f"/certidoes/{r.json()['id']}")).status_code == 404

        monkeypatch.setattr(rotas, "MAX_CERTIDOES", 9)  # 7 padrão + 2
        assert (await c.post("/certidoes", json={"nome": "Extra 1"})).status_code == 201
        assert (await c.post("/certidoes", json={"nome": "Extra 2"})).status_code == 201
        assert (await c.post("/certidoes", json={"nome": "Extra 3"})).status_code == 409


@pytest.mark.asyncio
async def test_certidoes_isoladas_por_empresa(ambiente):
    novo, _ = ambiente
    async with novo() as a, novo() as b:
        await _registrar(a, "ca")
        await _registrar(b, "cb")
        item_a = await _item(a, "Federal")
        await a.put(f"/certidoes/{item_a['id']}", json={"validade": _dia(10)})
        extra = (await a.post("/certidoes", json={"nome": "Só da empresa A"})).json()

        # a B tem a lista dela, com ids próprios e sem a data nem o documento da A
        itens_b = (await b.get("/certidoes")).json()["itens"]
        assert len(itens_b) == 7 and not {i["id"] for i in itens_b} & {item_a["id"], extra["id"]}
        assert all(i["validade"] is None for i in itens_b)
        assert (await b.get("/certidoes/resumo")).json()["sem_data"] == 7

        for r in (await b.put(f"/certidoes/{item_a['id']}", json={"validade": _dia(1)}),
                  await b.delete(f"/certidoes/{extra['id']}")):
            assert r.status_code == 404
        assert (await _item(a, "Federal"))["validade"] == _dia(10)  # a data da A não mudou
        assert any(i["id"] == extra["id"] for i in (await a.get("/certidoes")).json()["itens"])


ATESTADO = {"objeto": "Pavimentação asfáltica", "contratante": "Prefeitura de Camaçari", "data_emissao": "2025-03-10",
            "quantidade": 300.5, "unidade": "m²", "registro": "CREA-BA 12345"}


@pytest.mark.asyncio
async def test_atestados_crud_filtro_e_validacao(ambiente):
    novo, _ = ambiente
    async with novo() as c:
        await _registrar(c, "at")
        r = await c.post("/atestados", json=ATESTADO)
        assert r.status_code == 201 and r.json()["quantidade"] == 300.5 and r.json()["unidade"] == "m²"
        aid = r.json()["id"]
        await c.post("/atestados", json={"objeto": "Fornecimento de uniformes", "contratante": "Secretaria de Educação"})

        todos = (await c.get("/atestados")).json()
        assert todos["total"] == 2 and len(todos["itens"]) == 2
        assert [i["objeto"] for i in (await c.get("/atestados?q=PAVIMENTA")).json()["itens"]] == ["Pavimentação asfáltica"]
        assert [i["objeto"] for i in (await c.get("/atestados?q=educação")).json()["itens"]] == ["Fornecimento de uniformes"]  # contratante
        assert (await c.get("/atestados?q=%25")).json()["total"] == 2  # '%' não vira curinga: busca vazia, lista tudo
        assert (await c.get("/atestados?q=inexistente")).json()["itens"] == []

        r = await c.put(f"/atestados/{aid}", json={**ATESTADO, "quantidade": 500, "objeto": "  Pavimentação   de vias "})
        assert r.status_code == 200 and r.json()["quantidade"] == 500 and r.json()["objeto"] == "Pavimentação de vias"

        for ruim in ({**ATESTADO, "quantidade": -1}, {**ATESTADO, "objeto": " "}, {**ATESTADO, "contratante": ""},
                     {**ATESTADO, "data_emissao": (hoje_brt() + timedelta(days=10)).isoformat()},
                     {**ATESTADO, "unidade": "u" * 21}):
            assert (await c.post("/atestados", json=ruim)).status_code == 422, ruim
        assert (await c.get("/atestados")).json()["total"] == 2

        assert (await c.delete(f"/atestados/{aid}")).status_code == 204
        assert (await c.delete(f"/atestados/{aid}")).status_code == 404
        assert (await c.get("/atestados")).json()["total"] == 1


@pytest.mark.asyncio
async def test_atestados_isolados_por_empresa(ambiente):
    novo, _ = ambiente
    async with novo() as a, novo() as b:
        await _registrar(a, "aa")
        await _registrar(b, "ab")
        aid = (await a.post("/atestados", json=ATESTADO)).json()["id"]

        assert (await b.get("/atestados")).json() == {"total": 0, "itens": []}
        assert (await b.get("/atestados?q=pavimenta")).json()["itens"] == []
        assert (await b.put(f"/atestados/{aid}", json={**ATESTADO, "quantidade": 1})).status_code == 404
        assert (await b.delete(f"/atestados/{aid}")).status_code == 404
        mantido = (await a.get("/atestados")).json()["itens"][0]
        assert mantido["id"] == aid and mantido["quantidade"] == 300.5


@pytest.mark.asyncio
async def test_atestados_limite_por_empresa(ambiente, monkeypatch):
    novo, _ = ambiente
    import src.habilitacao.routes as rotas

    monkeypatch.setattr(rotas, "MAX_ATESTADOS", 2)
    async with novo() as c:
        await _registrar(c, "lim")
        assert (await c.post("/atestados", json=ATESTADO)).status_code == 201
        assert (await c.post("/atestados", json=ATESTADO)).status_code == 201
        assert (await c.post("/atestados", json=ATESTADO)).status_code == 409
