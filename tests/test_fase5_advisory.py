"""Testes Fase 5 — minutas Lei 14.133 + disclaimer OAB + outreach preview."""

from __future__ import annotations

from src.advisory.kit import CompanyContext, build_document_kit, draft_impugnacao
from src.models.enums import LegalAction, ModalityEnum
from src.models.schemas import LegalRiskItem, TenderSchema
from src.outreach.service import OutreachPayload, OutreachService


def _sample_tender(**kwargs) -> TenderSchema:
    base = dict(
        id_pncp="00000000000000-1-000001/2026",
        orgao_comprador="PREFEITURA TESTE",
        cnpj_orgao="00000000000000",
        uf="SP",
        municipio="SAO PAULO",
        modalidade=ModalityEnum.PREGAO_ELETRONICO,
        objeto_resumido="Aquisição de material de limpeza",
        valor_total_estimado=50000,
        riscos_juridicos=[],
        avisos=[],
    )
    base.update(kwargs)
    return TenderSchema(**base)


def test_kit_contains_disclaimer_and_art_164():
    kit = build_document_kit(_sample_tender(), CompanyContext(razao_social="LIMPEZA ME"))
    assert set(kit.minutas) == {"proposta", "esclarecimento", "impugnacao", "declaracao"}
    for content in kit.minutas.values():
        assert "8.906/1994" in content
        assert "MINUTA DE SUPORTE" in content
    assert "Art. 164" in kit.minutas["esclarecimento"]
    assert "14.133" in kit.minutas["impugnacao"]


def test_impugnacao_does_not_invent_risks():
    text = draft_impugnacao(_sample_tender(), CompanyContext())
    assert "não inventa" in text.lower() or "sem inventar" in text.lower() or "Nenhum risco" in text


def test_impugnacao_includes_detected_risk():
    tender = _sample_tender(
        riscos_juridicos=[
            LegalRiskItem(
                clausula="somente da marca XYZ",
                motivo_risco="possível direcionamento",
                fundamentacao_legal="Art. 41 da Lei 14.133/2021",
                sugestao_acao=LegalAction.IMPUGNACAO,
                pagina_referencia=12,
            )
        ]
    )
    text = draft_impugnacao(tender, CompanyContext())
    assert "marca XYZ" in text
    assert "pág. 12" in text


def test_outreach_preview_mentions_lei():
    service = OutreachService()
    text = service.build_message(
        OutreachPayload(
            phone="5511999999999",
            orgao="ORGAO X",
            objeto="Serviços de limpeza",
            valor_total=10000,
            id_pncp="00000000000000-1-000001/2026",
            checklist_resumo=["Habilitação: CNPJ"],
        )
    )
    assert "14.133" in text
    assert "8.906" in text
    assert "ORGAO X" in text
