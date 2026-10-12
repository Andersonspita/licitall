"""Envio agendado do digest por perfil (um horário diário, fuso de Brasília)."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import or_, update
from sqlmodel import select

from src.config import get_settings
from src.matching.digest import send_digest
from src.models.tables import DigestSchedule, InterestProfile

logger = logging.getLogger("licitall.matching.scheduler")

# Brasil não tem horário de verão desde 2019; offset fixo evita depender de tzdata no Windows.
BRT = timezone(timedelta(hours=-3), "BRT")
_HORARIO = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

Sender = Callable[[str, str, str | None], Awaitable[None]]


def parse_horario(value: str) -> tuple[int, int]:
    m = _HORARIO.match((value or "").strip())
    if not m:
        raise ValueError("horario deve ser HH:MM (00:00 a 23:59)")
    return int(m.group(1)), int(m.group(2))


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if not 10 <= len(digits) <= 15:
        raise ValueError("telefone deve ter de 10 a 15 dígitos, com DDI (ex.: 5571999999999)")
    return digits


def is_due(
    *,
    horario: str,
    now: datetime,
    ultimo_envio_dia: date | None,
    ultima_tentativa: datetime | None,
    retry_minutes: int = 15,
) -> bool:
    """True se já passou o horário de hoje, não houve envio hoje e a última tentativa não é recente."""
    hh, mm = parse_horario(horario)
    local = now.astimezone(BRT)
    if (local.hour, local.minute) < (hh, mm):
        return False
    if ultimo_envio_dia == local.date():
        return False
    if ultima_tentativa is not None and now - ultima_tentativa < timedelta(minutes=retry_minutes):
        return False
    return True


def passed_today(horario: str, now: datetime) -> bool:
    """True se o horário de hoje (BRT) já passou; usado para não disparar um envio imediato ao agendar."""
    hh, mm = parse_horario(horario)
    local = now.astimezone(BRT)
    return (local.hour, local.minute) >= (hh, mm)


def next_run(horario: str, now: datetime, ultimo_envio_dia: date | None) -> datetime:
    """Próxima execução prevista (em BRT); se já venceu e não foi enviada hoje, é agora."""
    hh, mm = parse_horario(horario)
    local = now.astimezone(BRT)
    candidate = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if ultimo_envio_dia == local.date():
        return candidate + timedelta(days=1)
    return local if candidate <= local else candidate


async def run_due_digests(
    session_factory: Any,
    *,
    sender: Sender,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Envia os digests vencidos. Seguro com vários processos: cada agendamento é reivindicado por UPDATE atômico."""
    settings = get_settings()
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(BRT).date()
    retry = timedelta(minutes=settings.digest_retry_minutes)
    results: list[dict[str, Any]] = []

    async with session_factory() as session:
        rows = (await session.exec(select(DigestSchedule).where(DigestSchedule.ativo == True))).all()  # noqa: E712
        # Copia para valores simples: após rollback() o ORM expira os objetos e ler atributos
        # dispararia IO síncrono (MissingGreenlet).
        schedules = [
            {
                "perfil_id": r.perfil_id,
                "horario": r.horario,
                "telefone": r.telefone,
                "top_n": r.top_n,
                "instance": r.instance,
                "ultimo_envio_dia": r.ultimo_envio_dia,
                "ultima_tentativa": r.ultima_tentativa,
            }
            for r in rows
        ]
        for sch in schedules:
            pid = sch["perfil_id"]
            if not is_due(
                horario=sch["horario"],
                now=now,
                ultimo_envio_dia=sch["ultimo_envio_dia"],
                ultima_tentativa=sch["ultima_tentativa"],
                retry_minutes=settings.digest_retry_minutes,
            ):
                continue
            claim = await session.execute(
                update(DigestSchedule)
                .where(
                    DigestSchedule.perfil_id == pid,
                    or_(DigestSchedule.ultimo_envio_dia.is_(None), DigestSchedule.ultimo_envio_dia != today),
                    or_(DigestSchedule.ultima_tentativa.is_(None), DigestSchedule.ultima_tentativa < now - retry),
                )
                .values(ultima_tentativa=now)
            )
            await session.commit()
            if claim.rowcount != 1:
                continue  # outro processo pegou

            entry: dict[str, Any] = {"perfil_id": str(pid)}
            try:
                profile = await session.get(InterestProfile, pid)
                if profile is None or not profile.ativo:
                    status, sent = "perfil inativo", False
                else:
                    r = await send_digest(
                        session, profile, phone=sch["telefone"], top_n=sch["top_n"],
                        instance=sch["instance"], sender=sender,
                    )
                    sent = bool(r["sent"])
                    status = "enviado" if sent else "sem novidades"
                await session.execute(
                    update(DigestSchedule)
                    .where(DigestSchedule.perfil_id == pid)
                    .values(ultimo_envio_dia=today, ultimo_status=status)
                )
                await session.commit()
                entry.update(status=status, enviado=sent)
            except Exception as exc:
                await session.rollback()
                msg = f"falha: {type(exc).__name__}: {exc}"[:300]
                logger.warning("Digest agendado %s falhou: %s", pid, msg)
                await session.execute(
                    update(DigestSchedule).where(DigestSchedule.perfil_id == pid).values(ultimo_status=msg)
                )
                await session.commit()
                entry.update(status=msg, enviado=False)
            results.append(entry)
    return results


async def scheduler_loop(session_factory: Any, sender: Sender, interval: float) -> None:
    while True:
        try:
            await run_due_digests(session_factory, sender=sender)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # o laço nunca pode morrer
            logger.warning("Ciclo do agendador falhou: %s", exc)
        await asyncio.sleep(interval)
