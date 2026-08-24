from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DocumentChecklist:
    habilitacao_juridica: list[str] = field(default_factory=list)
    regularidade_fiscal_social_trabalhista: list[str] = field(default_factory=list)
    qualificacao_economico_financeira: list[str] = field(default_factory=list)
    qualificacao_tecnica: list[str] = field(default_factory=list)

    def as_flat_list(self) -> list[str]:
        buckets = (
            ("Habilitação Jurídica", self.habilitacao_juridica),
            ("Regularidade Fiscal/Social/Trabalhista", self.regularidade_fiscal_social_trabalhista),
            ("Qualificação Econômico-Financeira", self.qualificacao_economico_financeira),
            ("Qualificação Técnica", self.qualificacao_tecnica),
        )
        items: list[str] = []
        for label, values in buckets:
            items.extend(f"{label}: {item}" for item in values)
        return items


def build_checklist(_markdown: str) -> DocumentChecklist:
    """Stub da Fase 3: matriz de documentos exigidos extraída do edital (sem alucinar)."""
    raise NotImplementedError(
        "DocumentChecklistAgent só lista exigências presentes no edital, com página/parágrafo."
    )
