"""Sonda as fontes de itens de um edital, uma a uma, mostrando status, tempo e quantidade.

    python -m scripts.sonda_itens 05816630000152-1-007503/2026 [outro-id ...]

`PncpClient.get_itens` esconde as falhas (espelho vazio + PNCP fora = lista vazia); aqui cada fonte aparece
separada: espelho de dados abertos do Compras.gov.br, API do PNCP (/api/pncp) e o caminho alternativo
(/pncp-api), que já respondeu 503 em testes anteriores. Não grava nada.
"""

from __future__ import annotations

import asyncio
import sys
import time

import httpx

from src.config import get_settings
from src.ingestion.client import parse_id_pncp

TIMEOUT = 30.0


async def sondar(client: httpx.AsyncClient, nome: str, url: str, params: dict | None = None) -> None:
    inicio = time.monotonic()
    try:
        r = await client.get(url, params=params)
    except httpx.HTTPError as exc:
        print(f"  {nome}: FALHOU após {time.monotonic() - inicio:.1f}s ({type(exc).__name__}: {exc})")
        return
    dur = time.monotonic() - inicio
    qtd = "?"
    try:
        corpo = r.json()
        lista = corpo if isinstance(corpo, list) else (corpo.get("resultado") or corpo.get("data") or [])
        qtd = len(lista)
        exemplo = (lista[0].get("descricaoResumida") or lista[0].get("descricao") or "") if lista else ""
    except ValueError:
        exemplo = r.text[:120].replace("\n", " ")
    print(f"  {nome}: HTTP {r.status_code} em {dur:.1f}s · itens: {qtd}" + (f" · ex.: {exemplo[:80]}" if exemplo else ""))


async def main(ids: list[str]) -> None:
    s = get_settings()
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"Accept": "application/json", "User-Agent": "LicitAll/0.1"},
                                 follow_redirects=True) as client:
        for raw in ids:
            p = parse_id_pncp(raw)
            caminho = f"/v1/orgaos/{p.cnpj}/compras/{p.ano}/{p.sequencial}/itens"
            print(f"\n{p.numero_controle}")
            await sondar(
                client, "Compras.gov.br (espelho)",
                f"{s.compras_dados_abertos_base_url.rstrip('/')}/modulo-contratacoes/2.1_consultarItensContratacoes_PNCP_14133_Id",
                {"tipo": "numeroControlePNCPCompra", "codigo": p.numero_controle, "pagina": 1, "tamanhoPagina": 500},
            )
            await sondar(client, "PNCP /api/pncp", f"{s.pncp_core_base_url.rstrip('/')}{caminho}")
            await sondar(client, "PNCP /pncp-api", f"https://pncp.gov.br/pncp-api{caminho}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    asyncio.run(main(sys.argv[1:]))
