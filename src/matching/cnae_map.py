"""Mapeamento heurístico objeto/CATMAT → CNAEs (Receita Federal).

Não inventa empresas: apenas sugere códigos CNAE para busca na Minha Receita.
Expandir conforme catálogo operacional do LicitAll.
"""

from __future__ import annotations

import re
from typing import Iterable

# (palavras-chave no objeto, CNAEs candidatos)
_CNAE_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("software", "sistema de informação", "ti ", "tecnologia da informação", "informática", "desenvolvimento de sistema"), ("6201501", "6202300", "6203100", "6204000", "6209100")),
    (("limpeza", "conservação predial", " asymmetricio"), ("8121400", "8129000")),
    (("vigilância", "vigilancia", "segurança patrimonial", "monitoramento"), ("8011101", "8011102")),
    (("alimentação", "refeição", "merenda", "canteen", "buffet"), ("5620101", "5611201")),
    (("medicamento", "farmácia", "farmaceutic", "hospitalar"), ("4771701", "4644301")),
    (("material de escritório", "papelaria", "expediente"), ("4761003", "4689399")),
    (("combustível", "diesel", "gasolina", "etanol"), ("4731800", "4682600")),
    (("veículo", "frota", "automóvel", "caminhão", "onibus", "ônibus"), ("4511101", "4921301", "4922102")),
    (("obra", "construção civil", "reforma predial", "engenharia civil"), ("4120400", "4299599", "7112000")),
    (("manutenção predial", "elétrica", "hidráulica", "ar-condicionado"), ("4321500", "4322300", "4329100")),
    (("transporte", "frete", "logística", "mudança"), ("4930201", "4930202", "5212500")),
    (("consultoria", "assessoria", "treinamento", "capacitação"), ("7020400", "8599604")),
    (("uniforme", "vestuário", "confecção"), ("1412601", "4781400")),
    (("mobiliário", "móveis", "cadeira", "mesa"), ("3101200", "4754701")),
    (("equipamento de informática", "notebook", "computador", "servidor", "impressora"), ("4751201", "2621300")),
    (("internet", "link de dados", "telecom", "telefonia"), ("6110801", "6120501", "6190601")),
    (("coleta de lixo", "resíduo", "ambiental"), ("3811400", "3821100")),
    (("jardinagem", "paisagismo", "poda"), ("8130300",)),
)


def infer_cnaes_from_text(text: str, *, limit: int = 8) -> list[str]:
    low = re.sub(r"\s+", " ", (text or "").lower())
    found: list[str] = []
    seen: set[str] = set()
    for keywords, codes in _CNAE_RULES:
        if any(k in low for k in keywords):
            for code in codes:
                if code not in seen:
                    seen.add(code)
                    found.append(code)
                    if len(found) >= limit:
                        return found
    return found


def merge_cnaes(*groups: Iterable[str] | None, limit: int = 12) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        if not group:
            continue
        for raw in group:
            code = re.sub(r"\D", "", str(raw))
            if not code or code in seen:
                continue
            seen.add(code)
            out.append(code)
            if len(out) >= limit:
                return out
    return out
