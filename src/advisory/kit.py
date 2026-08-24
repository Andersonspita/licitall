from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.advisory.generator import DISCLAIMER_OAB, render_minuta
from src.compliance.lei_14133 import ART_164_REF, LEI_14133_REF, LC123_REF
from src.models.enums import LegalAction
from src.models.schemas import LegalRiskItem, TenderSchema

MinutaKind = Literal["proposta", "esclarecimento", "impugnacao", "declaracao"]


class CompanyContext(BaseModel):
    razao_social: str = "EMPRESA EXEMPLO LTDA"
    cnpj: str = "00.000.000/0001-00"
    endereco: str = "[endereço da empresa — preencher]"
    email: str = "[e-mail — preencher]"
    telefone: str = "[telefone — preencher]"
    representante: str = "[nome do representante legal — preencher]"
    porte: str | None = "ME"  # ME | EPP | DEMAIS


class DocumentKit(BaseModel):
    id_pncp: str
    gerado_em: datetime
    minutas: dict[str, str] = Field(default_factory=dict)
    avisos: list[str] = Field(default_factory=list)
    marco_legal: str = LEI_14133_REF
    disclaimer: str = DISCLAIMER_OAB


def _tender_from_dict(data: dict[str, Any]) -> TenderSchema:
    if isinstance(data, TenderSchema):
        return data
    # riscos podem vir como dicts
    payload = dict(data)
    risks = []
    for item in payload.get("riscos_juridicos") or []:
        if isinstance(item, LegalRiskItem):
            risks.append(item)
        elif isinstance(item, dict):
            risks.append(LegalRiskItem(**item))
    payload["riscos_juridicos"] = risks
    return TenderSchema.model_validate(payload)


def draft_proposta(tender: TenderSchema, company: CompanyContext) -> str:
    linhas = []
    if tender.itens:
        for item in tender.itens:
            linhas.append(
                f"| {item.numero_item} | {item.descricao[:80]} | {item.quantidade} | "
                f"{item.unidade_medida} | R$ ____ | R$ ____ |"
            )
    else:
        linhas.append("| 1 | [descrever conforme edital] | ____ | UN | R$ ____ | R$ ____ |")

    body = f"""
À {tender.orgao_comprador}

**Proponente:** {company.razao_social}  
**CNPJ:** {company.cnpj}  
**Endereço:** {company.endereco}  
**Contato:** {company.email} / {company.telefone}

Apresentamos proposta comercial para o objeto abaixo, nos termos do edital e da {LEI_14133_REF}.

**Objeto:** {tender.objeto_resumido}

| Item | Descrição | Qtd | Und | Valor unit. | Valor total |
|------|-----------|-----|-----|-------------|-------------|
{chr(10).join(linhas)}

**Validade da proposta:** ____ dias  
**Prazo de entrega/execução:** conforme edital  

Declaramos ciência das condições do instrumento convocatório.

_______________________________  
{company.representante}  
Representante legal
""".strip()
    return render_minuta("proposta", tender, body)


def draft_esclarecimento(
    tender: TenderSchema,
    company: CompanyContext,
    perguntas: list[str] | None = None,
) -> str:
    qs = perguntas or [
        "Solicita-se esclarecer o trecho do edital indicado abaixo, à luz do "
        f"{ART_164_REF}, indicando página/item correspondente.",
    ]
    lista = "\n".join(f"{i}. {q}" for i, q in enumerate(qs, start=1))
    limite = (
        tender.limite_impugnacao.isoformat()
        if tender.limite_impugnacao
        else "[calcular Art. 164 — 3 dias úteis antes da abertura]"
    )
    body = f"""
À Comissão/Agente de Contratação — {tender.orgao_comprador}

**Requerente:** {company.razao_social} (CNPJ {company.cnpj})

**Assunto:** Pedido de esclarecimento — {ART_164_REF}

Com fulcro no {ART_164_REF} (prazo de até 3 dias úteis antes da abertura do certame),
requer-se esclarecimento sobre os seguintes pontos do edital/TR:

{lista}

**Limite de impugnação/esclarecimento considerado pelo sistema:** {limite}  
**Fonte do prazo:** {tender.limite_impugnacao_fonte or "não informada"}

Requer-se resposta em sítio eletrônico oficial, nos termos da lei.

_______________________________  
{company.representante}
""".strip()
    return render_minuta("esclarecimento", tender, body)


def draft_impugnacao(
    tender: TenderSchema,
    company: CompanyContext,
    riscos: list[LegalRiskItem] | None = None,
) -> str:
    risks = riscos if riscos is not None else list(tender.riscos_juridicos)
    actionable = [
        r
        for r in risks
        if str(r.sugestao_acao) in {LegalAction.IMPUGNACAO.value, LegalAction.PEDIDO_ESCLARECIMENTO.value, "IMPUGNACAO", "PEDIDO_ESCLARECIMENTO"}
    ]
    avisos = []
    if not actionable:
        avisos.append(
            "Nenhum risco com sugestão IMPUGNACAO/ESCLARECIMENTO foi identificado no texto. "
            "A minuta abaixo é estrutura formal — **não inventa vícios**. Preencha com trechos do edital."
        )
        pontos = (
            "1. [Indicar cláusula, página e fundamento na Lei 14.133/2021 — sem inventar irregularidade]\n"
        )
    else:
        blocos = []
        for i, risk in enumerate(actionable, start=1):
            cite = ""
            if risk.pagina_referencia is not None:
                cite = f" (pág. {risk.pagina_referencia}"
                if risk.paragrafo_referencia:
                    cite += f", {risk.paragrafo_referencia}"
                cite += ")"
            blocos.append(
                f"{i}. **Cláusula/trecho:** {risk.clausula}{cite}\n"
                f"   **Motivo:** {risk.motivo_risco}\n"
                f"   **Fundamento:** {risk.fundamentacao_legal}\n"
                f"   **Pedido:** {risk.sugestao_acao}"
            )
        pontos = "\n\n".join(blocos)

    limite = (
        tender.limite_impugnacao.isoformat()
        if tender.limite_impugnacao
        else "[Art. 164 — 3 dias úteis antes da abertura]"
    )
    nota = ("\n\n**Avisos do sistema:**\n- " + "\n- ".join(avisos)) if avisos else ""

    body = f"""
À Autoridade Competente / Agente de Contratação — {tender.orgao_comprador}

**Impugnante:** {company.razao_social} (CNPJ {company.cnpj})

**Assunto:** Impugnação ao edital — {ART_164_REF}

Vem respeitosamente impugnar o instrumento convocatório da contratação PNCP `{tender.id_pncp}`,
com fundamento na {LEI_14133_REF}, especialmente no {ART_164_REF}, pelos pontos abaixo
**extraídos da análise do edital** (sem inclusão de vícios não documentados):

{pontos}

**Pedido:** seja acolhida a presente impugnação para correção/anulação do(s) trecho(s) impugnado(s),
preservando-se a competitividade e a legalidade do certame.

**Prazo considerado:** {limite}
{nota}

_______________________________  
{company.representante}  
[OAB, se advogado constituído]
""".strip()
    return render_minuta("impugnacao", tender, body)


def draft_declaracoes(tender: TenderSchema, company: CompanyContext) -> str:
    porte = company.porte or "ME"
    me_epp_clause = ""
    if porte.upper() in {"ME", "EPP", "MICRO EMPRESA", "EMPRESA DE PEQUENO PORTE"}:
        me_epp_clause = f"""
### Declaração de enquadramento ME/EPP ({LC123_REF})

Declaramos, sob as penas da lei, que a empresa {company.razao_social} enquadra-se como
**{porte}**, nos termos da {LC123_REF}, c/c Art. 4º da {LEI_14133_REF}.
"""
    body = f"""
À {tender.orgao_comprador}

**Declarante:** {company.razao_social} — CNPJ {company.cnpj}

### Declaração de não emprego de menores

Declaramos que não empregamos menor de dezoito anos em trabalho noturno, perigoso ou insalubre
e não empregamos menor de dezesseis anos, salvo na condição de aprendiz, a partir de quatorze anos,
conforme legislação vigente e exigências do edital (quando houver).

### Declaração de cumprimento do Art. 63 / propostas

Declaramos que a proposta econômica compreende a integralidade dos custos para atendimento
dos direitos trabalhistas assegurados na Constituição Federal, nas leis trabalhistas,
nas normas infralegais, nas convenções coletivas e nos termos do edital, quando aplicável
à modalidade (referência: princípios e regras da {LEI_14133_REF}).
{me_epp_clause}
### Ciência do edital

Declaramos ter pleno conhecimento do edital e seus anexos relativos ao PNCP `{tender.id_pncp}`.

_______________________________  
{company.representante}
""".strip()
    return render_minuta("declaracao", tender, body)


def build_document_kit(
    tender_data: dict[str, Any] | TenderSchema,
    company: CompanyContext | None = None,
    *,
    perguntas_esclarecimento: list[str] | None = None,
) -> DocumentKit:
    tender = _tender_from_dict(tender_data) if not isinstance(tender_data, TenderSchema) else tender_data
    company = company or CompanyContext()
    avisos = list(tender.avisos)
    avisos.append("Todas as peças são minutas de suporte de IA — revisão humana obrigatória (Lei 8.906/1994).")
    return DocumentKit(
        id_pncp=tender.id_pncp,
        gerado_em=datetime.now(timezone.utc),
        minutas={
            "proposta": draft_proposta(tender, company),
            "esclarecimento": draft_esclarecimento(tender, company, perguntas_esclarecimento),
            "impugnacao": draft_impugnacao(tender, company),
            "declaracao": draft_declaracoes(tender, company),
        },
        avisos=avisos,
    )
