from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.models.schemas import DocumentRef, RequiredDocument
from src.parser.docling_parser import ParsedDocument


@dataclass
class DocumentChecklist:
    habilitacao_juridica: list[RequiredDocument] = field(default_factory=list)
    regularidade_fiscal_social_trabalhista: list[RequiredDocument] = field(default_factory=list)
    qualificacao_economico_financeira: list[RequiredDocument] = field(default_factory=list)
    qualificacao_tecnica: list[RequiredDocument] = field(default_factory=list)

    def as_flat_list(self) -> list[str]:
        buckets = (
            ("Habilitação Jurídica (Art. 66, Lei 14.133/2021)", self.habilitacao_juridica),
            (
                "Regularidade Fiscal/Social/Trabalhista (Arts. 68-69, Lei 14.133/2021)",
                self.regularidade_fiscal_social_trabalhista,
            ),
            (
                "Qualificação Econômico-Financeira (Art. 69, Lei 14.133/2021)",
                self.qualificacao_economico_financeira,
            ),
            ("Qualificação Técnica (Art. 67, Lei 14.133/2021)", self.qualificacao_tecnica),
        )
        items: list[str] = []
        for label, values in buckets:
            for doc in values:
                cite = ""
                if doc.pagina is not None:
                    cite = f" [pág. {doc.pagina}"
                    if doc.paragrafo:
                        cite += f", {doc.paragrafo}"
                    cite += "]"
                items.append(f"{label}: {doc.descricao}{cite}")
        return items


# Padrões só disparam se a expressão aparecer no edital (não são lista inventada).
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("juridica", re.compile(r"contrato social|estatuto|ato constitutiv|procura[cç][aã]o|rg do s[oó]cio|cnpj", re.I)),
    ("fiscal", re.compile(r"certid[aã]o.{0,40}(federal|fazenda|municipal|estadual)|cndt|fgts|inss|receita federal|dívida ativa|divida ativa", re.I)),
    ("economico_financeira", re.compile(r"balan[cç]o patrimonial|patrim[oô]nio l[ií]quido|capital social m[ií]nimo|[ií]ndice de liquidez|certid[aã]o negativa de fal[eê]ncia", re.I)),
    ("tecnica", re.compile(r"atestado de capacidade t[eé]cnica|acervo t[eé]cnico|registro no conselho|crea|cau|vistoria t[eé]cnica|prova de conceito", re.I)),
)


def _bucket(categoria: str, checklist: DocumentChecklist) -> list[RequiredDocument]:
    return {
        "juridica": checklist.habilitacao_juridica,
        "fiscal": checklist.regularidade_fiscal_social_trabalhista,
        "economico_financeira": checklist.qualificacao_economico_financeira,
        "tecnica": checklist.qualificacao_tecnica,
    }[categoria]


def build_checklist_from_refs(refs: list[DocumentRef]) -> DocumentChecklist:
    """Lista apenas exigências que aparecem no texto — sem completar com 'padrão de mercado'."""
    checklist = DocumentChecklist()
    seen: set[str] = set()
    for ref in refs:
        for categoria, pattern in _PATTERNS:
            for match in pattern.finditer(ref.texto):
                descricao = match.group(0).strip()
                key = f"{categoria}:{descricao.lower()}"
                if key in seen:
                    continue
                seen.add(key)
                _bucket(categoria, checklist).append(
                    RequiredDocument(
                        categoria=categoria,
                        descricao=descricao,
                        pagina=ref.pagina,
                        paragrafo=ref.paragrafo,
                    )
                )
    return checklist


def build_checklist(markdown: str) -> DocumentChecklist:
    from src.parser.docling_parser import refs_from_markdown

    return build_checklist_from_refs(refs_from_markdown(markdown))


def build_checklist_from_parsed(docs: list[ParsedDocument]) -> DocumentChecklist:
    refs = [ref for doc in docs for ref in doc.refs]
    if not refs:
        from src.parser.docling_parser import refs_from_markdown

        refs = refs_from_markdown("\n\n".join(doc.markdown for doc in docs))
    return build_checklist_from_refs(refs)
