"""Certidões e atestados da empresa (habilitação). Tudo isolado pela empresa do usuário logado."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.auth.deps import current_user
from src.db import get_session
from src.habilitacao.logic import (
    AVISO_PADRAO,
    CERTIDOES_PADRAO,
    MAX_ATESTADOS,
    MAX_CERTIDOES,
    hoje_brt,
    limpar,
    situacao_certidao,
    validar_data_emissao,
    validar_quantidade,
    validar_validade,
)
from src.models.tables import Atestado, Certidao, Usuario

certidoes_router = APIRouter(prefix="/certidoes", tags=["habilitacao"])
atestados_router = APIRouter(prefix="/atestados", tags=["habilitacao"])


def _422(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


# ---------------------------------------------------------------- certidões
class CertidaoNova(BaseModel):
    nome: str = Field(min_length=2, max_length=200)


class CertidaoEdicao(BaseModel):
    validade: date | None = None
    observacao: str | None = Field(default=None, max_length=500)


async def _garantir_padrao(db: AsyncSession, empresa_id: uuid.UUID) -> None:
    """Cria as certidões da lista oficial que faltam (idempotente, seguro com acessos simultâneos)."""
    agora = datetime.now(timezone.utc)
    for nome in CERTIDOES_PADRAO:
        await db.execute(
            pg_insert(Certidao)
            .values(id=uuid.uuid4(), empresa_id=empresa_id, nome=nome, padrao=True, created_at=agora, updated_at=agora)
            .on_conflict_do_nothing(constraint="unq_certidao_empresa_nome")
        )
    await db.commit()


def _cert_view(c: Certidao, hoje: date, aviso: int) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "nome": c.nome,
        "validade": c.validade.isoformat() if c.validade else None,
        "observacao": c.observacao,
        "padrao": c.padrao,
        **situacao_certidao(c.validade, hoje, aviso),
    }


def _resumo(itens: list[dict[str, Any]]) -> dict[str, Any]:
    cont = {"valida": 0, "vence_em_breve": 0, "vencida": 0, "sem_data": 0}
    for i in itens:
        cont[i["situacao"]] += 1
    atencao = sorted((i for i in itens if i["situacao"] in ("vencida", "vence_em_breve")), key=lambda i: i["dias"])
    return {**cont, "total": len(itens), "atencao": atencao[:5]}


async def _listar_certidoes(db: AsyncSession, user: Usuario, aviso: int) -> list[dict[str, Any]]:
    await _garantir_padrao(db, user.empresa_id)
    rows = (
        await db.exec(select(Certidao).where(Certidao.empresa_id == user.empresa_id).order_by(Certidao.padrao.desc(), Certidao.nome))
    ).all()
    hoje = hoje_brt()
    return [_cert_view(c, hoje, aviso) for c in rows]


async def _certidao_da_empresa(db: AsyncSession, user: Usuario, certidao_id: uuid.UUID) -> Certidao:
    c = await db.get(Certidao, certidao_id)
    if c is None or c.empresa_id != user.empresa_id:
        raise HTTPException(status_code=404, detail="Certidão não encontrada.")
    return c


@certidoes_router.get("")
async def listar_certidoes(
    aviso_dias: int = Query(AVISO_PADRAO, ge=1, le=90),
    db: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> dict[str, Any]:
    itens = await _listar_certidoes(db, user, aviso_dias)
    return {"hoje": hoje_brt().isoformat(), "aviso_dias": aviso_dias, "itens": itens, "resumo": _resumo(itens)}


@certidoes_router.get("/resumo")
async def resumo_certidoes(
    aviso_dias: int = Query(AVISO_PADRAO, ge=1, le=90),
    db: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> dict[str, Any]:
    return _resumo(await _listar_certidoes(db, user, aviso_dias))


@certidoes_router.post("", status_code=201)
async def criar_certidao(
    body: CertidaoNova,
    db: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> dict[str, Any]:
    nome = limpar(body.nome)
    if not nome or len(nome) < 2:
        raise HTTPException(status_code=422, detail="Informe o nome do documento.")
    await _garantir_padrao(db, user.empresa_id)
    total = (await db.exec(select(func.count()).select_from(Certidao).where(Certidao.empresa_id == user.empresa_id))).one()
    if total >= MAX_CERTIDOES:
        raise HTTPException(status_code=409, detail=f"Limite de {MAX_CERTIDOES} documentos atingido.")
    c = Certidao(empresa_id=user.empresa_id, nome=nome, padrao=False)
    db.add(c)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Já existe um documento com esse nome.") from exc
    await db.refresh(c)
    return _cert_view(c, hoje_brt(), AVISO_PADRAO)


@certidoes_router.put("/{certidao_id}")
async def atualizar_certidao(
    certidao_id: uuid.UUID,
    body: CertidaoEdicao,
    db: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> dict[str, Any]:
    c = await _certidao_da_empresa(db, user, certidao_id)
    try:
        validar_validade(body.validade, hoje_brt())
    except ValueError as exc:
        raise _422(exc) from exc
    c.validade = body.validade
    c.observacao = limpar(body.observacao)
    c.updated_at = datetime.now(timezone.utc)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return _cert_view(c, hoje_brt(), AVISO_PADRAO)


@certidoes_router.delete("/{certidao_id}", status_code=204, response_class=Response)
async def remover_certidao(
    certidao_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> Response:
    c = await _certidao_da_empresa(db, user, certidao_id)
    if c.padrao:
        raise HTTPException(status_code=409, detail="Documentos da lista oficial não podem ser removidos.")
    await db.delete(c)
    await db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- atestados
class AtestadoEntrada(BaseModel):
    objeto: str = Field(min_length=2, max_length=300)
    contratante: str = Field(min_length=2, max_length=200)
    data_emissao: date | None = None
    quantidade: float | None = None
    unidade: str | None = Field(default=None, max_length=20)
    registro: str | None = Field(default=None, max_length=120)


def _at_view(a: Atestado) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "objeto": a.objeto,
        "contratante": a.contratante,
        "data_emissao": a.data_emissao.isoformat() if a.data_emissao else None,
        "quantidade": a.quantidade,
        "unidade": a.unidade,
        "registro": a.registro,
    }


def _aplicar(a: Atestado, body: AtestadoEntrada) -> None:
    objeto, contratante = limpar(body.objeto), limpar(body.contratante)
    if not objeto or not contratante:
        raise HTTPException(status_code=422, detail="Informe o objeto e o contratante do atestado.")
    try:
        validar_data_emissao(body.data_emissao, hoje_brt())
        validar_quantidade(body.quantidade)
    except ValueError as exc:
        raise _422(exc) from exc
    a.objeto, a.contratante = objeto, contratante
    a.data_emissao, a.quantidade = body.data_emissao, body.quantidade
    a.unidade, a.registro = limpar(body.unidade), limpar(body.registro)


async def _atestado_da_empresa(db: AsyncSession, user: Usuario, atestado_id: uuid.UUID) -> Atestado:
    a = await db.get(Atestado, atestado_id)
    if a is None or a.empresa_id != user.empresa_id:
        raise HTTPException(status_code=404, detail="Atestado não encontrado.")
    return a


@atestados_router.get("")
async def listar_atestados(
    q: str | None = Query(default=None, max_length=100),
    db: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> dict[str, Any]:
    stmt = select(Atestado).where(Atestado.empresa_id == user.empresa_id)
    termo = limpar(q)
    if termo:
        like = f"%{termo.replace('%', '').replace('_', '')}%"
        stmt = stmt.where(Atestado.objeto.ilike(like) | Atestado.contratante.ilike(like))
    rows = (await db.exec(stmt.order_by(Atestado.created_at.desc()).limit(MAX_ATESTADOS))).all()
    total = (await db.exec(select(func.count()).select_from(Atestado).where(Atestado.empresa_id == user.empresa_id))).one()
    return {"total": int(total), "itens": [_at_view(a) for a in rows]}


@atestados_router.post("", status_code=201)
async def criar_atestado(
    body: AtestadoEntrada,
    db: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> dict[str, Any]:
    total = (await db.exec(select(func.count()).select_from(Atestado).where(Atestado.empresa_id == user.empresa_id))).one()
    if total >= MAX_ATESTADOS:
        raise HTTPException(status_code=409, detail=f"Limite de {MAX_ATESTADOS} atestados atingido.")
    a = Atestado(empresa_id=user.empresa_id, objeto="", contratante="")
    _aplicar(a, body)
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return _at_view(a)


@atestados_router.put("/{atestado_id}")
async def atualizar_atestado(
    atestado_id: uuid.UUID,
    body: AtestadoEntrada,
    db: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> dict[str, Any]:
    a = await _atestado_da_empresa(db, user, atestado_id)
    _aplicar(a, body)
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return _at_view(a)


@atestados_router.delete("/{atestado_id}", status_code=204, response_class=Response)
async def remover_atestado(
    atestado_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: Usuario = Depends(current_user),
) -> Response:
    a = await _atestado_da_empresa(db, user, atestado_id)
    await db.delete(a)
    await db.commit()
    return Response(status_code=204)
