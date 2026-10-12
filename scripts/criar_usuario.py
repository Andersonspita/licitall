"""Cria um usuário (e a empresa dele) ou redefine a senha de um existente. Útil com AUTH_REGISTRATION_OPEN=false.

    python -m scripts.criar_usuario --email ana@empresa.com.br --nome "Ana Souza" --empresa "Empresa A Ltda" [--admin]

A senha é pedida de forma oculta (não vai para o histórico do terminal). Se o e-mail já existir, só a senha é redefinida.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass

from sqlmodel import select

from src.auth.security import hash_password, normalize_email, password_problem, valid_email
from src.db import get_session_factory, init_db
from src.models.tables import Empresa, Usuario


async def run(email: str, nome: str | None, empresa: str | None, admin: bool, senha: str) -> str:
    await init_db()
    async with get_session_factory()() as db:
        user = (await db.exec(select(Usuario).where(Usuario.email == email))).first()
        if user:
            user.senha_hash = hash_password(senha)
            user.ativo = True
            if admin:
                user.is_admin = True
            db.add(user)
            await db.commit()
            return f"senha redefinida: {email}"
        if not nome or not empresa:
            raise SystemExit("Usuário novo: informe --nome e --empresa.")
        emp = Empresa(nome=empresa.strip())
        db.add(emp)
        await db.flush()
        db.add(Usuario(empresa_id=emp.id, email=email, nome=nome.strip(), senha_hash=hash_password(senha), is_admin=admin))
        await db.commit()
        return f"criado: {email} (empresa: {emp.nome}{', operador' if admin else ''})"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", required=True)
    ap.add_argument("--nome")
    ap.add_argument("--empresa", help="nome da empresa (obrigatório para usuário novo)")
    ap.add_argument("--admin", action="store_true", help="operador da plataforma (captação, pipeline, envios globais)")
    args = ap.parse_args()
    email = normalize_email(args.email)
    if not valid_email(email):
        raise SystemExit("E-mail inválido.")
    senha = getpass.getpass("Senha: ")
    if senha != getpass.getpass("Repita a senha: "):
        raise SystemExit("As senhas não coincidem.")
    problema = password_problem(senha)
    if problema:
        raise SystemExit(problema)
    print(asyncio.run(run(email, args.nome, args.empresa, args.admin, senha)))


if __name__ == "__main__":
    main()
