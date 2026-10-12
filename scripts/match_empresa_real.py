"""Match inverso com uma empresa real: CNPJ → editais abertos do banco, com relatório legível.

    python -m scripts.match_empresa_real 12345678000199 [--uf BA] [--top 15] [--json saida.json]
    python -m scripts.match_empresa_real 12345678000199 --minha-receita https://minhareceita.org
    python -m scripts.match_empresa_real 12345678000199 --uf BA --sincronizar 7   # busca antes os abertos dos últimos 7 dias

Lê `tender_ingest` (rode o sync antes) e consulta o CNPJ na Minha Receita. Sem a base local
(ETL), `--minha-receita https://minhareceita.org` usa a API pública, que tem o mesmo formato.
Só grava no banco com --sincronizar (editais abertos do PNCP, o mesmo que o sync da API faz).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import Counter
from typing import Any

PAUSA_ENTRE_PAGINAS = 1.5  # segundos; o PNCP responde 429 a sequências rápidas


def _moeda(valor: float | None) -> str:
    if valor is None:
        return "—"
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def main(args: argparse.Namespace) -> None:
    if args.minha_receita:
        os.environ["MINHA_RECEITA_BASE_URL"] = args.minha_receita

    from sqlalchemy import func
    from sqlmodel import select

    from src.db import get_session_factory, init_db
    from src.ingestion.service import open_tenders_clause
    from src.matching.service import MatchmakingService
    from src.models.tables import TenderIngest

    await init_db()
    if args.sincronizar:
        await sincronizar(args.uf, args.sincronizar)

    service = MatchmakingService()
    try:
        async with get_session_factory()() as session:
            editais = await service.list_open_tenders(session, uf=args.uf)
            if not editais:
                filtro = [TenderIngest.uf == args.uf.upper()] if args.uf else []
                total = (await session.exec(select(func.count()).select_from(TenderIngest).where(*filtro))).one()
                abertos = (await session.exec(
                    select(func.count()).select_from(TenderIngest).where(open_tenders_clause(), *filtro))).one()
            result = await service.match_company(
                args.cnpj,
                tenders=editais,
                limit=len(editais) or 1,
                min_score=0,
                uf_filter=args.uf,
            )
    finally:
        await service.aclose()

    print(f"\nEmpresa: {result.razao_social or '—'} ({result.cnpj})")
    print(f"Porte: {result.porte or '—'} · {result.municipio or '—'}/{result.uf or '—'}")
    print(f"CNAEs: {', '.join(result.cnaes_empresa) or '—'}")
    for aviso in result.avisos:
        print(f"AVISO: {aviso}")
    if not editais:
        onde = f"da UF {args.uf.upper()}" if args.uf else "de nenhuma UF"
        print(f"\nNenhum edital aberto {onde} no banco ({total} editais gravados, {abertos} abertos).")
        print("Busque os abertos no PNCP rodando de novo com --sincronizar 7 (últimos 7 dias; exige --uf).")
        return
    if not result.razao_social:
        return

    com_itens = sum(1 for t in editais if t.get("itens"))
    com_cnae = sum(1 for t in editais if t.get("cnaes_compativeis"))
    ops = result.opportunities
    recs = Counter(o.recommendation for o in ops)
    cnae_ok = sum(1 for o in ops if o.factors.cnae >= 35)
    print(f"\nEditais abertos avaliados: {len(editais)}{f' (UF {args.uf.upper()})' if args.uf else ''}")
    print(f"  com itens no banco: {com_itens} · com CNAE inferido: {com_cnae} · CNAE compatível com a empresa: {cnae_ok}")
    print(f"  BID: {recs['BID']} · REVIEW: {recs['REVIEW']} · SKIP: {recs['SKIP']}")

    print(f"\nTop {args.top}:")
    for pos, o in enumerate(ops[: args.top], 1):
        f = o.factors
        print(f"\n{pos:>2}. [{o.recommendation}] {o.score:.0f} pts — {o.orgao_comprador or '—'} ({o.municipio or '—'}/{o.uf or '—'})")
        print(f"    {(o.objeto_resumido or '').strip()[:180]}")
        print(f"    valor {_moeda(o.valor_total_estimado)} · encerra {o.data_encerramento_propostas or '—'} · {o.id_pncp}")
        print(f"    CNAE {f.cnae:.0f} · geo {f.geography:.0f} · porte {f.porte:.0f} · econ {f.economic:.0f} · prazo {f.deadline:.0f}")
        for motivo in o.eligibility_failures:
            print(f"    ✗ {motivo}")

    if args.json:
        payload: dict[str, Any] = result.model_dump(mode="json")
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print(f"\nResultado completo em {args.json}")


async def sincronizar(uf: str | None, dias: int) -> None:
    """Editais abertos da UF nos últimos `dias`, página a página, com a mesma espera em 429 do sync da API.

    Uma modalidade que falha não derruba as outras; cada página é gravada assim que chega.
    """
    from datetime import date, timedelta

    from src.config import get_settings
    from src.db import get_session_factory
    from src.ingestion.client import PncpClient
    from src.ingestion.jobs import _fetch_page_with_retry
    from src.ingestion.service import is_open_for_proposals, map_pncp_item, upsert_tender
    from src.models.enums import DEFAULT_INGESTION_MODALITIES

    if not uf:
        raise SystemExit("--sincronizar exige --uf (para o Brasil inteiro use o sync da API, que vai UF a UF).")
    uf, final = uf.upper(), date.today()
    inicial = final - timedelta(days=dias)
    print(f"Sincronizando editais abertos de {uf} publicados de {inicial} a {final} (o PNCP limita pedidos; pode demorar)...")
    gravados, falhas = 0, []
    async with get_session_factory()() as session, PncpClient() as client:
        for modalidade in DEFAULT_INGESTION_MODALITIES:
            pagina, total = 1, 1
            try:
                while pagina <= total:
                    async def avisar(tentativa: int, motivo: str, espera: float) -> None:
                        print(f"  {modalidade.value} p.{pagina}: {motivo}, nova tentativa em {espera:.0f}s")

                    payload = await _fetch_page_with_retry(
                        client, data_inicial=inicial, data_final=final, modalidade=modalidade, uf=uf, pagina=pagina,
                        max_attempts=max(1, get_settings().pncp_page_retries), on_retry=avisar,
                    )
                    total = max(1, int(payload.get("totalPaginas") or 1))
                    for item in payload.get("data") or []:
                        if is_open_for_proposals(item):
                            await upsert_tender(session, map_pncp_item(item))
                            gravados += 1
                    await session.commit()
                    print(f"  {modalidade.value} p.{pagina}/{total} · {gravados} abertos até agora")
                    if payload.get("empty") or pagina >= total:
                        break
                    pagina += 1
                    await asyncio.sleep(PAUSA_ENTRE_PAGINAS)
            except Exception as exc:  # noqa: BLE001
                falhas.append(f"{modalidade.value}: {type(exc).__name__}")
                print(f"  {modalidade.value}: desisti na p.{pagina} ({type(exc).__name__}); seguindo com o que já foi gravado")
    print(f"{gravados} editais abertos gravados ou atualizados." + (f" Falhas: {', '.join(falhas)}." if falhas else ""))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cnpj")
    parser.add_argument("--uf", help="Só editais desta UF (padrão: todas)")
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--json", help="Grava o resultado completo neste arquivo")
    parser.add_argument("--sincronizar", type=int, metavar="DIAS", help="Antes, busca no PNCP os editais abertos publicados nos últimos DIAS")
    parser.add_argument("--minha-receita", help="URL da Minha Receita (ex.: https://minhareceita.org)")
    asyncio.run(main(parser.parse_args()))
