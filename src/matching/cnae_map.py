"""Mapeamento heurístico objeto/CATMAT → CNAEs (Receita Federal).

Não inventa empresas: apenas sugere códigos CNAE para busca na Minha Receita.
Expandir conforme catálogo operacional do LicitAll.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

# (palavras-chave no objeto, CNAEs candidatos). Casam como PALAVRA INTEIRA, sem acento e sem caixa, aceitando plural
# ("computador" casa "computadores"). Termos ambíguos só com contexto: "servidor" sozinho é servidor público,
# "confecção" sozinha pode ser de próteses, "obra" sozinha aparece em "mão de obra", "cadeira" em "braçadeira".
_CNAE_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("software", "sistema de informação", "sistemas de informação", "tecnologia da informação", "informática",
      "desenvolvimento de sistema"), ("6201501", "6202300", "6203100", "6204000", "6209100")),
    (("limpeza", "conservação predial"), ("8121400", "8129000")),
    (("vigilância", "segurança patrimonial", "videomonitoramento", "monitoramento eletrônico", "cftv"), ("8011101", "8011102")),
    (("alimentação", "refeição", "merenda", "buffet"), ("5620101", "5611201")),
    # Fornecimento de alimentos (atacado), diferente de servir refeições (restaurante/fornecimento de refeições).
    (("gêneros alimentícios", "gênero alimentício", "produtos alimentícios", "hortifruti", "hortifrutigranjeiro"), ("4639701", "4691500")),
    (("medicamento", "farmácia", "farmacêutico", "hospitalar"), ("4771701", "4644301")),
    # 4647801: atacado de artigos de escritório e papelaria (distribuidoras); 4761003: varejo de papelaria.
    (("material de escritório", "materiais de escritório", "artigos de escritório", "papelaria", "material de expediente",
      "materiais de expediente", "expediente", "material escolar", "materiais escolares", "kit escolar", "resma",
      "papel a4", "papel sulfite", "caneta esferográfica"), ("4647801", "4761003", "4689399")),
    (("combustível", "diesel", "gasolina", "etanol"), ("4731800", "4682600")),
    (("veículo", "frota", "automóvel", "caminhão", "ônibus"), ("4511101", "4921301", "4922102")),
    (("obras de", "execução de obra", "obra pública", "construção civil", "reforma predial", "engenharia civil", "pavimentação"),
     ("4120400", "4299599", "7112000")),
    (("manutenção predial", "instalação elétrica", "instalações elétricas", "hidráulica", "ar-condicionado", "ar condicionado"),
     ("4321500", "4322300", "4329100")),
    (("transporte", "frete", "logística", "mudança"), ("4930201", "4930202", "5212500")),
    (("consultoria", "assessoria", "treinamento", "capacitação"), ("7020400", "8599604")),
    # Só expressões de contratação: "advocacia"/"advogado" soltos aparecem em nomes de lugar (Escola Superior da Advocacia).
    (("assessoria jurídica", "consultoria jurídica", "serviços jurídicos", "serviços advocatícios", "serviços de advocacia",
      "escritório de advocacia", "sociedade de advogados", "representação judicial", "patrocínio judicial"), ("6911701",)),
    (("contábil", "contabilidade", "auditoria independente"), ("6920601", "6920602")),
    (("uniforme", "fardamento", "vestuário", "confecção de uniforme", "confecção de roupa"), ("1412601", "4781400")),
    (("mobiliário", "móveis", "cadeira", "mesa", "armário", "estante"), ("3101200", "4754701")),
    (("equipamento de informática", "equipamentos de informática", "notebook", "computador", "servidor de rede", "servidores de rede",
      "impressora", "tablet"), ("4751201", "2621300")),
    (("internet", "link de dados", "telecom", "telefonia"), ("6110801", "6120501", "6190601")),
    (("coleta de lixo", "resíduos sólidos", "coleta de resíduo", "limpeza urbana"), ("3811400", "3821100")),
    (("jardinagem", "paisagismo", "poda"), ("8130300",)),
)


def _sem_acento(text: str) -> str:
    base = unicodedata.normalize("NFKD", text.lower())
    return re.sub(r"\s+", " ", "".join(c for c in base if not unicodedata.combining(c)))


def _padrao(keywords: tuple[str, ...]) -> re.Pattern[str]:
    alternativas = "|".join(re.escape(_sem_acento(k)) for k in sorted(keywords, key=len, reverse=True))
    return re.compile(rf"(?<![a-z0-9])(?:{alternativas})(?:e?s)?(?![a-z0-9])")


_REGRAS = tuple((_padrao(keywords), codes) for keywords, codes in _CNAE_RULES)


def infer_cnaes_from_text(text: str, *, limit: int = 8) -> list[str]:
    low = _sem_acento(text or "")
    found: list[str] = []
    seen: set[str] = set()
    for padrao, codes in _REGRAS:
        if padrao.search(low):
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
