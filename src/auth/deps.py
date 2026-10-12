"""Guarda global: toda rota exige login, salvo as listadas como públicas em security.required_role."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from src.auth.security import hash_token, origin_ok, required_role
from src.config import get_settings
from src.db import get_session_factory
from src.models.tables import Sessao, Usuario


def token_from_request(request: Request) -> str | None:
    cookie = request.cookies.get(get_settings().session_cookie_name)
    if cookie:
        return cookie
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


async def load_user(raw_token: str) -> Usuario | None:
    async with get_session_factory()() as db:
        row = (
            await db.exec(
                select(Usuario)
                .join(Sessao, Sessao.usuario_id == Usuario.id)
                .where(
                    Sessao.token_hash == hash_token(raw_token),
                    Sessao.expires_at > datetime.now(timezone.utc),
                    Usuario.ativo == True,  # noqa: E712
                )
            )
        ).first()
        return row


async def guard(request: Request) -> None:
    role = required_role(request.url.path)
    if role == "public":
        return
    if not origin_ok(request.method, request.headers.get("origin"), request.headers.get("host")):
        raise HTTPException(status_code=403, detail="Origem não permitida.")
    token = token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Faça login para continuar.")
    try:
        user = await load_user(token)
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível.") from exc
    if user is None:
        raise HTTPException(status_code=401, detail="Sessão expirada. Faça login novamente.")
    if role == "admin" and not user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso restrito ao operador da plataforma.")
    request.state.user = user


def current_user(request: Request) -> Usuario:
    """Usuário autenticado (a guarda global já o validou)."""
    user = getattr(request.state, "user", None)
    if user is None:  # rota pública usando esta dependência por engano
        raise HTTPException(status_code=401, detail="Faça login para continuar.")
    return user


CurrentUser = Depends(current_user)
