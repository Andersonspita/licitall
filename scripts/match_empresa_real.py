"""Match inverso com uma empresa real: CNPJ → editais abertos do banco, com relatório legível.

    python -m scripts.match_empresa_real 12345678000199 [--uf BA] [--top 15] [--json saida.json]
    python -m scripts.match_empresa_real 12345678000199 --minha-receita https://minhareceita.org

Lê `tender_ingest` (rode o sync antes) e consulta o CNPJ na Minha Receita. Sem a base local
(ETL), `--minha-receita https://minhareceita.org` usa a API pública, que tem o mesmo formato.
Não grava nada no banco.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import Counter
from typing import Any


def _moeda(valor: float | None) -> str:
    if valor is None:
        return "—"
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def main(args: argparse.Namespace) -> None:
    if args.minha_receita:
        os.environ["MINHA_RECEITA_BASE_URL"] = args.minha_receita

    from src.db import get_session_factory, init_db
    from src.matching.service import MatchmakingService

    await init_db()
    service = MatchmakingService()
    try:
        async with get_session_factory()() as session:
            editais = await service.list_open_tenders(session, uf=args.uf)
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
    if not editais or not result.razao_social:
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cnpj")
    parser.add_argument("--uf", help="Só editais desta UF (padrão: todas)")
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--json", help="Grava o resultado completo neste arquivo")
    parser.add_argument("--minha-receita", help="URL da Minha Receita (ex.: https://minhareceita.org)")
    asyncio.run(main(parser.parse_args()))
