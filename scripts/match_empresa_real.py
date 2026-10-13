"""Match inverso com uma empresa real: CNPJ → editais abertos do banco, com relatório legível.

    python -m scripts.match_empresa_real 12345678000199 [--uf BA] [--top 15] [--json saida.json]
    python -m scripts.match_empresa_real 12345678000199 --minha-receita https://minhareceita.org
    python -m scripts.match_empresa_real 12345678000199 --uf BA --sincronizar 7   # busca antes os abertos dos últimos 7 dias
    python -m scripts.match_empresa_real 12345678000199 --uf BA --medir-ramo      # distribuição da similaridade objeto × CNAE
    python -m scripts.match_empresa_real 12345678000199 --uf BA --limiares 0.74,0.82

Editais cujo ramo o mapa de palavras-chave não identifica são comparados por significado com os CNAEs da empresa
(com GEMINI_API_KEY). Na primeira vez são ~1 chamada por 100 objetos (cota gratuita: 100/min); depois vem do cache.

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
                session=session,
                limit=len(editais) or 1,
                min_score=0,
                uf_filter=args.uf,
                ramo_limiares=args.limiares,
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
    ramos = Counter(o.ramo for o in ops)
    principal = [o for o in ops if o.ramo == "principal"]
    secundario, semantico = ramos["secundario"], ramos["significado"]
    print(f"\nEditais abertos avaliados: {len(editais)}{f' (UF {args.uf.upper()})' if args.uf else ''}")
    print(f"  com itens no banco: {com_itens} · com CNAE inferido: {com_cnae}")
    print(f"  do ramo da empresa: {len(principal)} pelo CNAE principal · {secundario} só por secundário · {semantico} por significado")
    print(f"  BID: {recs['BID']} · REVIEW: {recs['REVIEW']} · SKIP: {recs['SKIP']}")

    print(f"\nTop {args.top} (ramo principal primeiro, depois secundário/significado, depois desconhecido; dentro do ramo, pela nota):")
    for pos, o in enumerate(ops[: args.top], 1):
        f = o.factors
        print(f"\n{pos:>2}. [{o.recommendation}] {o.score:.0f} pts · ramo {o.ramo} — {o.orgao_comprador or '—'} ({o.municipio or '—'}/{o.uf or '—'})")
        print(f"    {(o.objeto_resumido or '').strip()[:180]}")
        print(f"    valor {_moeda(o.valor_total_estimado)} · encerra {o.data_encerramento_propostas or '—'} · {o.id_pncp}")
        print(f"    CNAE {f.cnae:.0f} · geo {f.geography:.0f} · porte {f.porte:.0f} · econ {f.economic:.0f} · prazo {f.deadline:.0f}")
        if o.ramo_semantico:
            r = o.ramo_semantico
            ressalva = f", {r['ressalva']}" if r.get("ressalva") else ""
            print(f"    ramo por significado: {r['status']}{ressalva} (similaridade {r['similaridade']:.3f} com \"{r['referencia']}\")")
        for motivo in o.eligibility_failures:
            print(f"    ✗ {motivo}")
        for aviso in o.eligibility_warnings:
            if "LC 123" in aviso:
                print(f"    ! {aviso}")

    fora = [o for o in principal if o not in ops[: args.top]]
    if fora:
        print(f"\nDo CNAE principal, fora do top {args.top}:")
        for o in fora:
            motivo = "; ".join(o.eligibility_failures) or f"{o.score:.0f} pts"
            print(f"  [{o.recommendation}] {(o.objeto_resumido or '').strip()[:90]} — {motivo}")

    if args.medir_ramo:
        medir_ramo(ops)

    if args.json:
        payload: dict[str, Any] = result.model_dump(mode="json")
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print(f"\nResultado completo em {args.json}")


def medir_ramo(ops: list[Any]) -> None:
    """Distribuição da similaridade objeto × CNAE, com exemplos por faixa, para calibrar os limiares."""
    com = sorted((o for o in ops if o.ramo_semantico), key=lambda o: -o.ramo_semantico["similaridade"])
    if not com:
        print("\nNenhum edital comparado por significado (veja o AVISO no início; sem aviso, todos tiveram ramo pelo mapa).")
        return
    sims = [o.ramo_semantico["similaridade"] for o in com]
    print(f"\nSimilaridade objeto × CNAE em {len(com)} editais: máx {sims[0]:.3f} · mediana {sims[len(sims) // 2]:.3f} · mín {sims[-1]:.3f}")
    faixas: dict[str, list[Any]] = {}
    for o in com:
        faixas.setdefault(f"{int(o.ramo_semantico['similaridade'] * 100) / 100:.2f}", []).append(o)
    for faixa, itens in faixas.items():
        print(f"  {faixa}: {len(itens):>4} " + "#" * min(60, len(itens)))
    print("\nExemplos por faixa (sem repetir objeto; confira quais são do ramo):")
    for faixa, itens in faixas.items():
        vistos: list[str] = []
        for o in itens:
            obj = " ".join((o.objeto_resumido or "").split())[:90]
            if obj not in vistos:
                vistos.append(obj)
                r = o.ramo_semantico
                ressalva = f" ({r['ressalva']})" if r.get("ressalva") else ""
                print(f"  {faixa}  [{r['status']}{ressalva}] {obj}  ~ {r['referencia'][:40]}")
            if len(vistos) == 4:
                break


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
    parser.add_argument("--medir-ramo", action="store_true", help="Mostra a distribuição da similaridade objeto × CNAE")
    parser.add_argument("--limiares", type=lambda v: tuple(float(x) for x in v.split(",")), metavar="BAIXO,ALTO",
                        help="Limiares de cosseno do ramo por significado (padrão do provedor; gemini: 0.76,0.84)")
    parser.add_argument("--minha-receita", help="URL da Minha Receita (ex.: https://minhareceita.org)")
    asyncio.run(main(parser.parse_args()))
