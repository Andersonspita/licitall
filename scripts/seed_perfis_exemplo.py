"""Cria dois perfis de interesse de exemplo (idempotente).

    python -m scripts.seed_perfis_exemplo --email EMAIL_DE_UM_USUARIO [--ufs BA,SE,AL] [--remover]

Sem --ufs os perfis valem para o Brasil inteiro. Não define códigos CATMAT/CATSER de propósito:
não se inventam códigos de catálogo; o cliente cadastra os reais pela tela "Aderência ao perfil".
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from typing import Any

from sqlmodel import select

from src.db import get_session_factory, init_db
from src.matching import profiles as svc
from src.models.tables import InterestProfile, Usuario

PERFIS: list[dict[str, Any]] = [
    {
        "nome_perfil": "Equipamentos de Informática",
        "valor_minimo_item": 50.0,
        "valor_maximo_item": 200000.0,
        "palavras": {
            "POSITIVA": ["notebook", "computador", "desktop", "monitor", "impressora", "servidor", "switch", "tablet"],
            "NEGATIVA": ["locação", "aluguel", "reforma"],
        },
        "descricao_sintetica": "Fornecimento de notebooks, computadores, monitores, impressoras e equipamentos de rede",
    },
    {
        "nome_perfil": "Mobiliário Escolar",
        "valor_minimo_item": 20.0,
        "valor_maximo_item": 100000.0,
        "palavras": {
            "POSITIVA": ["carteira escolar", "cadeira", "mesa", "armário", "quadro branco", "lousa", "estante"],
            "NEGATIVA": ["locação", "aluguel", "reforma"],
        },
        "descricao_sintetica": "Fornecimento de carteiras escolares, mesas, cadeiras, armários e quadros para escolas",
    },
]


async def empresa_do_usuario(email: str) -> uuid.UUID:
    await init_db()
    async with get_session_factory()() as session:
        user = (await session.exec(select(Usuario).where(Usuario.email == email.strip().lower()))).first()
    if user is None:
        raise SystemExit(f"Não há usuário com o e-mail {email}. Crie a conta antes (tela de cadastro ou scripts.criar_usuario).")
    return user.empresa_id


async def seed(empresa_id: uuid.UUID, ufs: list[str]) -> list[str]:
    await init_db()
    log: list[str] = []
    async with get_session_factory()() as session:
        existentes = {
            p.nome_perfil
            for p in (await session.exec(select(InterestProfile).where(InterestProfile.empresa_id == empresa_id))).all()
        }
        for cfg in PERFIS:
            if cfg["nome_perfil"] in existentes:
                log.append(f"já existe: {cfg['nome_perfil']}")
                continue
            await svc.create_profile(session, empresa_id=empresa_id, ufs_permitidas=ufs, **cfg)
            log.append(f"criado: {cfg['nome_perfil']}")
    return log


async def remove(empresa_id: uuid.UUID) -> list[str]:
    nomes = {c["nome_perfil"] for c in PERFIS}
    log: list[str] = []
    async with get_session_factory()() as session:
        for p in (await session.exec(select(InterestProfile).where(InterestProfile.empresa_id == empresa_id))).all():
            if p.nome_perfil in nomes:
                await svc.delete_profile(session, p)
                log.append(f"removido: {p.nome_perfil}")
    return log


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", required=True, help="e-mail de um usuário já cadastrado: os perfis vão para a empresa dele")
    ap.add_argument("--ufs", default="", help="siglas separadas por vírgula; vazio = Brasil inteiro")
    ap.add_argument("--remover", action="store_true", help="remove os perfis de exemplo em vez de criar")
    args = ap.parse_args()
    ufs = [u.strip().upper() for u in args.ufs.split(",") if u.strip()]
    if any(len(u) != 2 for u in ufs):
        raise SystemExit("--ufs deve conter siglas de 2 letras, ex.: BA,SE,AL")
    async def executar() -> list[str]:
        empresa_id = await empresa_do_usuario(args.email)
        return await (remove(empresa_id) if args.remover else seed(empresa_id, ufs))

    out = asyncio.run(executar())
    print("\n".join(out) or "nada a fazer")


if __name__ == "__main__":
    main()
