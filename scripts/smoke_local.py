"""Smoke test local do LicitAll (Fase 1–5) sem depender de Evolution conectada.

Uso:
  python scripts/smoke_local.py

Com Docker (opcional):
  docker compose up -d
  uvicorn src.main:app --port 8000
  python scripts/smoke_local.py --api http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ok(name: str, detail: str = "") -> None:
    print(f"[OK] {name}" + (f" — {detail}" if detail else ""))


def _fail(name: str, detail: str) -> None:
    print(f"[FAIL] {name} — {detail}")


def _skip(name: str, detail: str) -> None:
    print(f"[SKIP] {name} — {detail}")


async def smoke_pncp() -> str | None:
    from src.ingestion.client import PncpClient
    from src.models.enums import ModalityEnum

    fim = date.today()
    ini = fim - timedelta(days=2)
    async with PncpClient() as client:
        payload = await client.list_publicacoes(
            data_inicial=ini,
            data_final=fim,
            modalidade=ModalityEnum.PREGAO_ELETRONICO,
            pagina=1,
            tamanho_pagina=10,
        )
        total = int(payload.get("totalRegistros") or 0)
        rows = payload.get("data") or []
        _ok("PNCP publicacao", f"{total} registros no período; página com {len(rows)} itens")
        if not rows:
            return None
        id_pncp = rows[0].get("numeroControlePNCP")
        _ok("PNCP amostra", str(id_pncp))
        return str(id_pncp) if id_pncp else None


async def smoke_rag() -> None:
    from src.rag.store import LegalStore

    store = LegalStore()
    n = await store.index_corpus()
    hits = await store.search("prazo de impugnação artigo 164", top_k=3)
    assert n > 0 and hits
    _ok("RAG Lei 14.133", f"{n} chunks; top={hits[0].titulo} score={hits[0].score:.3f}")


def smoke_advisory() -> None:
    from src.advisory.kit import CompanyContext, build_document_kit
    from src.models.enums import ModalityEnum
    from src.models.schemas import TenderSchema

    tender = TenderSchema(
        id_pncp="00000000000000-1-000001/2026",
        orgao_comprador="ORGAO SMOKE",
        cnpj_orgao="00000000000000",
        uf="SP",
        municipio="SAO PAULO",
        modalidade=ModalityEnum.PREGAO_ELETRONICO,
        objeto_resumido="Serviços de limpeza predial",
        valor_total_estimado=45000,
    )
    kit = build_document_kit(tender, CompanyContext(razao_social="SMOKE ME LTDA"))
    assert "8.906/1994" in kit.minutas["proposta"]
    assert "Art. 164" in kit.minutas["esclarecimento"]
    _ok("Advisory kit", f"{len(kit.minutas)} minutas com disclaimer OAB")


def smoke_outreach_preview() -> None:
    from src.outreach.service import OutreachPayload, OutreachService

    text = OutreachService().build_message(
        OutreachPayload(
            phone="5511999999999",
            orgao="ORGAO SMOKE",
            objeto="Limpeza",
            valor_total=1000,
            id_pncp="00000000000000-1-000001/2026",
        )
    )
    assert "14.133" in text
    _ok("Outreach preview", f"{len(text)} chars")


def smoke_matching_score() -> None:
    from src.matching.cnae_map import infer_cnaes_from_text
    from src.matching.scoring import matching_score

    cnaes = infer_cnaes_from_text("desenvolvimento de software")
    score = matching_score(
        tender={"cnaes_compativeis": cnaes, "uf": "SP", "exclusivo_me_epp": True},
        company={
            "cnae_fiscal": cnaes[0] if cnaes else "6201501",
            "uf": "SP",
            "porte": "MICRO EMPRESA",
            "cnaes_secundarios": [],
        },
    )
    assert score > 50
    _ok("Matching score", f"cnaes={cnaes[:3]} score={score}")


async def smoke_api(base: str) -> None:
    import httpx

    async with httpx.AsyncClient(base_url=base.rstrip("/"), timeout=60.0) as client:
        health = await client.get("/health")
        health.raise_for_status()
        data = health.json()
        _ok("API /health", f"fase={data.get('fase')} marco={data.get('marco_legal')}")

        idx = await client.post("/rag/index/lei-14133")
        if idx.status_code < 400:
            _ok("API /rag/index", str(idx.json().get("indexed")))
        else:
            _fail("API /rag/index", idx.text[:200])

        preview = await client.post(
            "/outreach/whatsapp/preview",
            json={
                "phone": "5511999999999",
                "orgao": "ORGAO",
                "objeto": "Teste",
                "valor_total": 1,
                "id_pncp": "00000000000000-1-000001/2026",
            },
        )
        if preview.status_code < 400:
            _ok("API outreach preview", f"{preview.json().get('chars')} chars")
        else:
            _fail("API outreach preview", preview.text[:200])


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="", help="Base URL da API (ex.: http://127.0.0.1:8000)")
    args = parser.parse_args()

    print("=== LicitAll smoke local ===")
    print(f"cwd={ROOT}")
    failures = 0

    try:
        await smoke_pncp()
    except Exception as exc:
        _fail("PNCP", str(exc))
        failures += 1

    try:
        await smoke_rag()
    except Exception as exc:
        _fail("RAG", str(exc))
        failures += 1

    try:
        smoke_advisory()
    except Exception as exc:
        _fail("Advisory", str(exc))
        failures += 1

    try:
        smoke_outreach_preview()
    except Exception as exc:
        _fail("Outreach", str(exc))
        failures += 1

    try:
        smoke_matching_score()
    except Exception as exc:
        _fail("Matching", str(exc))
        failures += 1

    # Docker check
    try:
        import subprocess

        r = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0:
            _ok("Docker daemon", "disponível")
        else:
            _skip("Docker daemon", "indisponível — compose/Postgres/Evolution não testados")
    except Exception as exc:
        _skip("Docker daemon", str(exc))

    if args.api:
        try:
            await smoke_api(args.api)
        except Exception as exc:
            _fail("API HTTP", str(exc))
            failures += 1
    else:
        _skip("API HTTP", "passe --api http://127.0.0.1:8000 com uvicorn no ar")

    print("=== fim ===")
    print(json.dumps({"failures": failures}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
