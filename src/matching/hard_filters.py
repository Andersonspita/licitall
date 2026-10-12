"""Camada 1 do funil de matching: filtros rígidos (eliminatórios) por item.

Funções puras: não acessam banco nem rede. Valor desconhecido (None/0) não elimina,
para não descartar item por dado ausente na fonte.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable


def normalize_text(text: str | None) -> str:
    """Minúsculas, sem acentos e com espaços colapsados."""
    decomposed = unicodedata.normalize("NFD", str(text or "").lower())
    plain = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", plain).strip()


def term_matches(term: str, normalized_text: str) -> bool:
    """Termo inteiro (palavra ou expressão), aceitando plural simples (s/es)."""
    norm = normalize_text(term)
    if not norm:
        return False
    pattern = r"(?<!\w)" + re.escape(norm) + r"(?:s|es)?(?!\w)"
    return re.search(pattern, normalized_text) is not None


@dataclass(frozen=True)
class ProfileFilters:
    ufs_permitidas: tuple[str, ...] = ()
    valor_minimo_item: float = 0.0
    valor_maximo_item: float | None = None
    apenas_me_epp: bool = False
    termos_negativos: tuple[str, ...] = ()


@dataclass
class HardFilterResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)


def _item_value(item: dict[str, Any]) -> float | None:
    for key in ("valor_unitario_estimado", "valor_total_estimado"):
        value = item.get(key)
        if value:
            return float(value)
    return None


def evaluate_hard_filters(
    item: dict[str, Any],
    profile: ProfileFilters,
    *,
    uf: str | None = None,
    extra_text: str | None = None,
) -> HardFilterResult:
    """Avalia um item contra o perfil. `uf` e `extra_text` (objeto da compra) vêm da contratação."""
    reasons: list[str] = []

    ufs = {u.upper() for u in profile.ufs_permitidas if u}
    if ufs and (uf or "").upper() not in ufs:
        reasons.append(f"UF {uf or 'desconhecida'} fora das UFs do perfil")

    value = _item_value(item)
    if value is not None:
        if value < profile.valor_minimo_item:
            reasons.append("valor abaixo do mínimo do perfil")
        if profile.valor_maximo_item is not None and value > profile.valor_maximo_item:
            reasons.append("valor acima do máximo do perfil")

    if profile.apenas_me_epp and not item.get("exclusivo_me_epp"):
        reasons.append("ampla concorrência (perfil opera só itens exclusivos ME/EPP)")

    text = normalize_text(f"{item.get('descricao') or ''} {extra_text or ''}")
    hits = [t for t in profile.termos_negativos if term_matches(t, text)]
    if hits:
        reasons.append("termo negativo: " + ", ".join(sorted(set(hits))))

    return HardFilterResult(passed=not reasons, reasons=reasons)


def filter_items(
    items: Iterable[dict[str, Any]],
    profile: ProfileFilters,
    *,
    uf: str | None = None,
    extra_text: str | None = None,
) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], list[str]]]]:
    """Separa itens aprovados dos descartados (com os motivos)."""
    kept: list[dict[str, Any]] = []
    dropped: list[tuple[dict[str, Any], list[str]]] = []
    for item in items:
        result = evaluate_hard_filters(item, profile, uf=uf, extra_text=extra_text)
        if result.passed:
            kept.append(item)
        else:
            dropped.append((item, result.reasons))
    return kept, dropped
