"""Regras determinísticas da Lei 14.133/2021 e LC 123/2006.

Fontes:
- Lei Federal nº 14.133/2021 (nova lei de licitações e contratos)
- Lei Complementar nº 123/2006 (ME/EPP)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable

# Art. 164, Lei 14.133/2021: impugnação e esclarecimentos até 3 dias úteis
# antes da data de abertura do certame.
ART_164_DIAS_UTEIS = 3

# LC 123/2006, Art. 48 — tratamento diferenciado ME/EPP
LC123_VALOR_EXCLUSIVO_ME_EPP = 80_000.0  # itens/lotes exclusivos até R$ 80 mil
LC123_COTA_RESERVADA_PCT = 0.25  # cota reservada de até 25%

LEI_14133_REF = "Lei Federal nº 14.133/2021"
LC123_REF = "Lei Complementar nº 123/2006"
ART_164_REF = "Art. 164 da Lei nº 14.133/2021"

# Feriados nacionais fixos (MM, DD). Móveis: Carnaval/Corpus Christi aproximados via tabela ano.
_FIXED_HOLIDAYS: tuple[tuple[int, int], ...] = (
    (1, 1),  # Confraternização Universal
    (4, 21),  # Tiradentes
    (5, 1),  # Dia do Trabalho
    (9, 7),  # Independência
    (10, 12),  # N. Sra. Aparecida
    (11, 2),  # Finados
    (11, 15),  # Proclamação da República
    (11, 20),  # Consciência Negra (Lei 14.759/2023 — nacional)
    (12, 25),  # Natal
)


def _easter_sunday(year: int) -> date:
    """Algoritmo de Meeus/Jones/Butcher (Páscoa gregoriana)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def brazilian_national_holidays(year: int) -> set[date]:
    holidays = {date(year, month, day) for month, day in _FIXED_HOLIDAYS}
    easter = _easter_sunday(year)
    holidays.add(easter - timedelta(days=48))  # segunda de Carnaval (aproximação)
    holidays.add(easter - timedelta(days=47))  # terça de Carnaval
    holidays.add(easter - timedelta(days=2))  # Sexta-feira Santa
    holidays.add(easter + timedelta(days=60))  # Corpus Christi
    return holidays


def is_business_day(day: date, extra_holidays: Iterable[date] | None = None) -> bool:
    if day.weekday() >= 5:
        return False
    holidays = brazilian_national_holidays(day.year)
    if extra_holidays:
        holidays = holidays | set(extra_holidays)
    return day not in holidays


def subtract_business_days(
    start: date,
    days: int,
    extra_holidays: Iterable[date] | None = None,
) -> date:
    """Retrocede `days` dias úteis a partir de `start` (não conta o próprio start se for o alvo)."""
    if days < 0:
        raise ValueError("days deve ser >= 0")
    current = start
    remaining = days
    while remaining > 0:
        current -= timedelta(days=1)
        if is_business_day(current, extra_holidays):
            remaining -= 1
    return current


def _as_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def prazo_impugnacao_art_164(
    data_abertura_certame: date | datetime,
    dias_uteis: int = ART_164_DIAS_UTEIS,
    extra_holidays: Iterable[date] | None = None,
) -> date:
    """Último dia útil para impugnação/esclarecimento (Art. 164, Lei 14.133/2021).

    Conta-se até 3 dias úteis *antes* da data de abertura do certame.
    """
    abertura = _as_date(data_abertura_certame)
    return subtract_business_days(abertura, dias_uteis, extra_holidays)


def prazo_impugnacao_datetime(
    data_abertura_certame: date | datetime,
    *,
    end_of_day: bool = True,
) -> datetime:
    limite = prazo_impugnacao_art_164(data_abertura_certame)
    if end_of_day:
        return datetime(limite.year, limite.month, limite.day, 23, 59, 59, tzinfo=timezone.utc)
    return datetime(limite.year, limite.month, limite.day, tzinfo=timezone.utc)


def is_exclusive_me_epp_value(valor: float) -> bool:
    """Indica se o valor está na faixa típica de exclusividade ME/EPP (Art. 48, LC 123)."""
    return 0 < valor <= LC123_VALOR_EXCLUSIVO_ME_EPP


def reserved_quota_value(valor_total: float) -> float:
    """Valor máximo sugerido da cota reservada de 25% (Art. 48, LC 123)."""
    return max(0.0, valor_total * LC123_COTA_RESERVADA_PCT)
