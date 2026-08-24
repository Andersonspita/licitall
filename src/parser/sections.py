"""Taxonomia de seções de edital alinhada à Lei 14.133/2021."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SectionSpec:
    key: str
    label: str
    keywords: tuple[str, ...]
    lei_14133_hint: str


# Ordem de prioridade na classificação de headings.
EDITAL_SECTION_SPECS: tuple[SectionSpec, ...] = (
    SectionSpec(
        key="objeto",
        label="Objeto",
        keywords=("objeto", "objeto da licitação", "objeto da contratação"),
        lei_14133_hint="Art. 6º e descrição do objeto (Lei 14.133/2021)",
    ),
    SectionSpec(
        key="participacao",
        label="Condições de Participação",
        keywords=("condições de participação", "participação", "impedimentos"),
        lei_14133_hint="Arts. 14 e seguintes (Lei 14.133/2021)",
    ),
    SectionSpec(
        key="me_epp",
        label="Benefícios ME/EPP",
        keywords=("me/epp", "microempresa", "pequeno porte", "lc 123", "cota reservada", "exclusivo"),
        lei_14133_hint="Art. 4º Lei 14.133 c/c LC 123/2006",
    ),
    SectionSpec(
        key="habilitacao_juridica",
        label="Habilitação Jurídica",
        keywords=("habilitação jurídica", "documentação jurídica"),
        lei_14133_hint="Art. 66 (Lei 14.133/2021)",
    ),
    SectionSpec(
        key="regularidade_fiscal",
        label="Regularidade Fiscal/Social/Trabalhista",
        keywords=(
            "regularidade fiscal",
            "regularidade social",
            "regularidade trabalhista",
            "habilitação fiscal",
            "fgts",
            "inss",
            "trabalhista",
        ),
        lei_14133_hint="Arts. 68 e 69 (Lei 14.133/2021)",
    ),
    SectionSpec(
        key="qualificacao_economico_financeira",
        label="Qualificação Econômico-Financeira",
        keywords=(
            "qualificação econômico",
            "qualificação economico",
            "econômico-financeira",
            "economico-financeira",
            "patrimônio líquido",
            "capital social mínimo",
            "balanço patrimonial",
        ),
        lei_14133_hint="Art. 69 (Lei 14.133/2021)",
    ),
    SectionSpec(
        key="qualificacao_tecnica",
        label="Qualificação Técnica",
        keywords=("qualificação técnica", "qualificacao tecnica", "atestado", "acervo técnico", "vistoria"),
        lei_14133_hint="Art. 67 (Lei 14.133/2021)",
    ),
    SectionSpec(
        key="julgamento",
        label="Critérios de Julgamento",
        keywords=("critério de julgamento", "criterio de julgamento", "julgamento", "menor preço", "técnica e preço"),
        lei_14133_hint="Arts. 33 a 39 (Lei 14.133/2021)",
    ),
    SectionSpec(
        key="proposta",
        label="Proposta e Prazos",
        keywords=(
            "proposta",
            "prazo",
            "abertura",
            "sessão pública",
            "impugnação",
            "impugnacao",
            "esclarecimento",
            "recebimento de propostas",
        ),
        lei_14133_hint="Art. 164 e rito do pregão/concorrência (Lei 14.133/2021)",
    ),
    SectionSpec(
        key="contrato",
        label="Minuta do Contrato",
        keywords=("minuta do contrato", "contrato", "obrigações da contratada", "sanções", "sancoes"),
        lei_14133_hint="Arts. 89 e seguintes (Lei 14.133/2021)",
    ),
)

# Compatibilidade com API anterior
EDITAL_SECTIONS = tuple(spec.label for spec in EDITAL_SECTION_SPECS)


def classify_heading(heading: str) -> SectionSpec | None:
    text = heading.lower().strip()
    text = text.lstrip("#").strip()
    best: SectionSpec | None = None
    best_len = 0
    for spec in EDITAL_SECTION_SPECS:
        for keyword in spec.keywords:
            if keyword in text and len(keyword) > best_len:
                best = spec
                best_len = len(keyword)
    return best
