"""Testes unitários — compliance Lei 14.133/2021 (sem dependências pesadas)."""

from __future__ import annotations

from datetime import date, datetime

from src.agents.checklist import build_checklist
from src.agents.extractor import extract_from_markdown, extract_me_epp_benefits
from src.agents.legal_rag import analyze_legal_risks
from src.compliance.lei_14133 import (
    ART_164_DIAS_UTEIS,
    is_business_day,
    is_exclusive_me_epp_value,
    prazo_impugnacao_art_164,
    subtract_business_days,
)


def test_art_164_three_business_days_before_monday():
    # Abertura na segunda 2026-08-24 → 3 dúteis antes = quarta 2026-08-19
    abertura = date(2026, 8, 24)
    assert abertura.weekday() == 0
    limite = prazo_impugnacao_art_164(abertura)
    assert limite == date(2026, 8, 19)
    assert ART_164_DIAS_UTEIS == 3


def test_business_day_skips_weekend():
    friday = date(2026, 8, 21)
    assert is_business_day(friday)
    assert subtract_business_days(date(2026, 8, 24), 1) == date(2026, 8, 21)


def test_lc123_exclusive_threshold():
    assert is_exclusive_me_epp_value(80_000)
    assert is_exclusive_me_epp_value(79_999.99)
    assert not is_exclusive_me_epp_value(80_000.01)
    assert not is_exclusive_me_epp_value(0)


def test_extractor_does_not_invent_certidoes():
    md = """
# Objeto
Aquisição de material de escritório.

# Habilitação Jurídica
Contrato social e cartão CNPJ.
"""
    result = extract_from_markdown(md, id_pncp="00000000000000-1-000001/2026")
    assert "fgts" not in " ".join(result.tender.documentos_exigidos).lower()
    assert result.tender.marco_legal.startswith("Lei Federal nº 14.133")


def test_me_epp_only_when_stated():
    bare = extract_me_epp_benefits("Pregão eletrônico para serviços de limpeza.")
    assert not bare.exclusivo_me_epp
    rich = extract_me_epp_benefits(
        "Item exclusivo para ME/EPP conforme LC 123, com cota reservada de 25%."
    )
    assert rich.exclusivo_me_epp
    assert rich.cota_reservada_25


def test_checklist_only_mentions_found_docs():
    checklist = build_checklist(
        "Exigir-se-á certidão conjunta da Receita Federal e FGTS. Atestado de capacidade técnica."
    )
    flat = " ".join(checklist.as_flat_list()).lower()
    assert "fgts" in flat or "receita" in flat
    assert "atestado" in flat
    # Não inventa CNDT se não citado
    assert "cndt" not in flat


def test_legal_screening_marca():
    risks = analyze_legal_risks(
        "O produto deverá ser somente da marca XYZ, sem similar."
    )
    assert risks
    assert "14.133" in risks[0].fundamentacao_legal


def test_impugnacao_calculated_when_abertura_present():
    md = """
# Proposta e Prazos
Data de abertura das propostas: 24/08/2026
Data da sessão pública: 24/08/2026
"""
    result = extract_from_markdown(md, id_pncp="00000000000000-1-000001/2026")
    assert result.tender.limite_impugnacao is not None
    assert result.tender.limite_impugnacao_fonte == "calculado_art_164"
    assert result.tender.limite_impugnacao.date() == date(2026, 8, 19)
