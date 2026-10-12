from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.auth.deps import token_from_request
from src.auth.security import (
    LoginThrottle,
    burn_verify,
    hash_password,
    hash_token,
    new_session_token,
    normalize_email,
    password_problem,
    valid_email,
    verify_password,
)
from src.config import get_settings
from src.db import get_session
from src.models.tables import Empresa, Sessao, Usuario

router = APIRouter(prefix="/auth", tags=["auth"])
throttle = LoginThrottle()


class RegisterRequest(BaseModel):
    empresa_nome: str = Field(min_length=2, max_length=200)
    nome: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=254)
    senha: str = Field(max_length=200)


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    senha: str = Field(max_length=200)


def _is_admin_email(email: str) -> bool:
    return email in {normalize_email(e) for e in get_settings().admin_emails.split(",") if e.strip()}


def _me(user: Usuario, empresa: Empresa | None) -> dict[str, Any]:
    return {
        "email": user.email,
        "nome": user.nome,
        "admin": user.is_admin,
        "empresa": {"id": str(user.empresa_id), "nome": empresa.nome if empresa else None},
    }


async def _open_session(db: AsyncSession, user: Usuario, response: Response) -> None:
    settings = get_settings()
    raw, hashed = new_session_token()
    now = datetime.now(timezone.utc)
    await db.exec(delete(Sessao).where(Sessao.expires_at < now))  # limpeza barata de sessões vencidas
    db.add(Sessao(token_hash=hashed, usuario_id=user.id, expires_at=now + timedelta(hours=settings.session_ttl_hours)))
    user.ultimo_login = now
    db.add(user)
    await db.commit()
    response.set_cookie(
        settings.session_cookie_name, raw,
        max_age=settings.session_ttl_hours * 3600, httponly=True, samesite="lax",
        secure=settings.cookie_secure, path="/",
    )


@router.get("/config")
async def auth_config() -> dict[str, bool]:
    return {"registro_aberto": get_settings().auth_registration_open}


@router.post("/register", status_code=201)
async def register(body: RegisterRequest, response: Response, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    if not get_settings().auth_registration_open:
        raise HTTPException(status_code=403, detail="Cadastro fechado. Peça a criação da conta ao administrador.")
    email = normalize_email(body.email)
    if not valid_email(email):
        raise HTTPException(status_code=422, detail="Informe um e-mail válido.")
    problem = password_problem(body.senha)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    empresa = Empresa(nome=body.empresa_nome.strip())
    user = Usuario(
        empresa_id=empresa.id, email=email, nome=body.nome.strip(),
        senha_hash=hash_password(body.senha), is_admin=_is_admin_email(email),
    )
    try:
        db.add(empresa)
        await db.flush()
        db.add(user)
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Já existe uma conta com este e-mail.") from exc
    await _open_session(db, user, response)
    return _me(user, empresa)


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    email = normalize_email(body.email)
    key = f"{email}|{request.client.host if request.client else '?'}"
    wait = throttle.retry_after(key)
    if wait:
        raise HTTPException(
            status_code=429, headers={"Retry-After": str(wait)},
            detail=f"Muitas tentativas. Tente novamente em {max(1, wait // 60)} min.",
        )
    user = (await db.exec(select(Usuario).where(Usuario.email == email, Usuario.ativo == True))).first()  # noqa: E712
    ok = verify_password(body.senha, user.senha_hash) if user else (burn_verify(body.senha) or False)
    if not ok or user is None:
        throttle.fail(key)
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    throttle.success(key)
    await _open_session(db, user, response)
    return _me(user, await db.get(Empresa, user.empresa_id))


@router.post("/logout", status_code=204, response_class=Response)
async def logout(request: Request, db: AsyncSession = Depends(get_session)) -> Response:
    token = token_from_request(request)
    if token:
        await db.exec(delete(Sessao).where(Sessao.token_hash == hash_token(token)))
        await db.commit()
    resp = Response(status_code=204)
    resp.delete_cookie(get_settings().session_cookie_name, path="/")
    return resp


@router.get("/me")
async def me(request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    from src.auth.deps import current_user

    user = current_user(request)
    return _me(user, await db.get(Empresa, user.empresa_id))
