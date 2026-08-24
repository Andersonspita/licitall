"""Smoke com Docker Compose (Postgres, Redis, Minha Receita, Evolution).

Uso:
  python scripts/smoke_compose.py
  python scripts/smoke_compose.py --api http://127.0.0.1:8000 --id 83021808000182-1-000518/2026
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import time
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


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def compose_up() -> bool:
    result = subprocess.run(
        ["docker", "compose", "up", "-d"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _fail("docker compose up", result.stderr.strip() or result.stdout.strip())
        return False
    _ok("docker compose up", "serviços iniciados")
    return True


async def wait_deps(timeout_sec: int = 120) -> dict:
    from src.infra.health import check_dependencies

    deadline = time.monotonic() + timeout_sec
    last: dict = {}
    while time.monotonic() < deadline:
        last = await check_dependencies()
        if last.get("all_up"):
            return last
        await asyncio.sleep(3)
    return last


async def smoke_api(api_base: str, id_pncp: str | None) -> None:
    import httpx

    base = api_base.rstrip("/")
    async with httpx.AsyncClient(timeout=120.0) as client:
        health = await client.get(f"{base}/health")
        health.raise_for_status()
        body = health.json()
        _ok("/health", f"fase={body.get('fase')}")

        deps = await client.get(f"{base}/health/deps")
        deps.raise_for_status()
        summary = deps.json().get("summary", "")
        _ok("/health/deps", summary)

        sync = await client.post(
            f"{base}/ingestion/pncp/sync",
            json={"data_inicial": None, "data_final": None, "only_open": True},
        )
        if sync.status_code == 200:
            ing = sync.json()
            _ok("PNCP sync Postgres", f"{ing.get('ingested')} registros")
        else:
            _skip("PNCP sync Postgres", f"HTTP {sync.status_code}: {sync.text[:200]}")

        if not id_pncp:
            _skip("pipeline run", "id_pncp não informado")
            return

        pipe = await client.post(
            f"{base}/pipeline/{id_pncp}/run",
            json={"download_if_missing": False, "run_matching": True, "persist_kit": True},
        )
        if pipe.status_code != 200:
            _fail("pipeline run", f"HTTP {pipe.status_code}: {pipe.text[:400]}")
            return
        payload = pipe.json()
        kit = payload.get("kit") or {}
        _ok(
            "pipeline run",
            f"minutas={len(kit.get('minutas') or [])} matching={bool(payload.get('matching'))}",
        )


async def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke LicitAll com Docker Compose")
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="Base URL da API FastAPI")
    parser.add_argument(
        "--id",
        dest="id_pncp",
        default="83021808000182-1-000518/2026",
        help="ID PNCP para pipeline ponta a ponta",
    )
    parser.add_argument("--no-compose", action="store_true", help="Não sobe o Compose (já rodando)")
    args = parser.parse_args()

    if not args.no_compose:
        if not docker_available():
            _skip("Docker", "daemon indisponível — ligue o Docker Desktop e rode de novo")
            return 0
        if not compose_up():
            return 1

    deps = await wait_deps()
    print(json.dumps(deps, ensure_ascii=False, indent=2))
    if not deps.get("all_up"):
        _skip("deps all_up", deps.get("summary", "parcial"))

    try:
        await smoke_api(args.api, args.id_pncp)
    except Exception as exc:
        _fail("API smoke", str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
