from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from src.agents.prompts import EXTRACTOR_SYSTEM_PROMPT
from src.compliance.lei_14133 import (
    ART_164_REF,
    is_exclusive_me_epp_value,
    prazo_impugnacao_datetime,
)
from src.models.enums import PNCP_CODE_TO_MODALITY, ModalityEnum
from src.models.schemas import (
    CitedText,
    MeEppBenefits,
    TenderExtractionResult,
    TenderItem,
    TenderSchema,
)
from src.parser.docling_parser import ParsedDocument


def _exclusive_me_epp(item: dict[str, Any]) -> bool:
    raw = " ".join(
        str(item.get(key) or "")
        for key in ("beneficioMpeNome", "tipoBeneficioNome", "beneficio")
    ).lower()
    return "exclusiv" in raw or "me/epp" in raw or "me epp" in raw


def items_from_pncp(raw_items: list[dict[str, Any]]) -> list[TenderItem]:
    mapped: list[TenderItem] = []
    for raw in raw_items:
        numero = int(raw.get("numeroItem") or raw.get("numero") or 0)
        valor_total = float(raw.get("valorTotal") or raw.get("valorTotalEstimado") or 0)
        exclusivo = _exclusive_me_epp(raw) or is_exclusive_me_epp_value(valor_total)
        mapped.append(
            TenderItem(
                numero_item=numero,
                descricao=str(raw.get("descricao") or raw.get("descricaoDetalhada") or ""),
                catmat_catser=raw.get("catalogo")
                or raw.get("codigoCatalogo")
                or raw.get("materialOuServico"),
                quantidade=float(raw.get("quantidade") or 0),
                unidade_medida=str(raw.get("unidadeMedida") or raw.get("unidade") or "UN"),
                valor_unitario_estimado=float(raw.get("valorUnitarioEstimado") or 0),
                valor_total_estimado=valor_total,
                exclusivo_me_epp=exclusivo,
            )
        )
    return mapped


def modality_from_pncp(item: dict[str, Any]) -> ModalityEnum:
    code = item.get("modalidadeId") or item.get("codigoModalidadeContratacao")
    if isinstance(code, int) and code in PNCP_CODE_TO_MODALITY:
        return PNCP_CODE_TO_MODALITY[code]
    name = str(item.get("modalidadeNome") or "").lower()
    if "pregão" in name or "pregao" in name:
        return ModalityEnum.PREGAO_ELETRONICO
    if "concorr" in name:
        return ModalityEnum.CONCORRENCIA
    if "dispensa" in name:
        return ModalityEnum.DISPENSA_ELETRONICA
    return ModalityEnum.PREGAO_ELETRONICO


_DATE_PATTERNS = (
    re.compile(
        r"(?P<label>impugna[cç][aã]o|esclarecimento|abertura|sess[aã]o|disputa|proposta)s?"
        r".{0,40}?(?P<d>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        re.I | re.S,
    ),
    re.compile(r"(?P<d>\d{1,2}[/-]\d{1,2}[/-]\d{2,4}).{0,40}?(?P<label>impugna|esclarec|abertura|sess[aã]o)", re.I),
)


def _parse_br_date(raw: str) -> datetime | None:
    raw = raw.strip().replace("-", "/")
    parts = raw.split("/")
    if len(parts) != 3:
        return None
    day, month, year = (int(parts[0]), int(parts[1]), int(parts[2]))
    if year < 100:
        year += 2000
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def _find_cited(refs: list, keywords: tuple[str, ...]) -> CitedText | None:
    for ref in refs:
        low = ref.texto.lower()
        if any(k in low for k in keywords):
            return CitedText(
                texto=ref.texto[:500],
                pagina=ref.pagina,
                paragrafo=ref.paragrafo,
                secao=ref.secao,
            )
    return None


def extract_me_epp_benefits(markdown: str, refs: list | None = None) -> MeEppBenefits:
    low = markdown.lower()
    exclusivo = bool(
        re.search(r"exclusiv[oa].{0,40}(me|epp|microempresa|pequeno porte)", low)
        or re.search(r"(me|epp|microempresa).{0,40}exclusiv", low)
    )
    cota = "25%" in low or "vinte e cinco por cento" in low or "cota reservada" in low
    citacao = _find_cited(refs or [], ("microempresa", "me/epp", "cota reservada", "exclusiv"))
    observacao = None
    if exclusivo or cota:
        observacao = "Benefício identificado no texto do edital (LC 123/2006)."
    return MeEppBenefits(
        exclusivo_me_epp=exclusivo,
        cota_reservada_25=cota,
        observacao=observacao,
        citacao=citacao,
    )


def extract_dates_from_text(markdown: str) -> dict[str, datetime]:
    found: dict[str, datetime] = {}
    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(markdown):
            label = match.group("label").lower()
            dt = _parse_br_date(match.group("d"))
            if not dt:
                continue
            if "impugn" in label:
                found.setdefault("limite_impugnacao", dt)
            elif "esclarec" in label:
                found.setdefault("limite_esclarecimento", dt)
            elif "abertura" in label or "proposta" in label:
                found.setdefault("data_abertura_propostas", dt)
            elif "sess" in label or "disputa" in label:
                found.setdefault("data_sessao_disputa", dt)
    return found


def extract_objeto(parsed: ParsedDocument) -> CitedText | None:
    section = parsed.sections.get("objeto") or ""
    if section.strip():
        return CitedText(texto=section[:800], secao="objeto", pagina=None, paragrafo="secao-objeto")
    return _find_cited(parsed.refs, ("objeto da licitação", "objeto da contratação", "objeto:"))


def build_tender_from_sources(
    *,
    id_pncp: str,
    pncp_payload: dict[str, Any] | None = None,
    pncp_itens: list[dict[str, Any]] | None = None,
    parsed_docs: list[ParsedDocument] | None = None,
) -> TenderExtractionResult:
    """Mescla metadados PNCP + texto Docling. Não inventa campos ausentes."""
    pncp_payload = pncp_payload or {}
    parsed_docs = parsed_docs or []
    avisos: list[str] = []
    missing: list[str] = []

    orgao = (pncp_payload.get("orgaoEntidade") or pncp_payload.get("orgao") or {})
    unidade = pncp_payload.get("unidadeOrgao") or {}

    orgao_nome = orgao.get("razaoSocial") or pncp_payload.get("orgaoRazaoSocial") or ""
    cnpj = re.sub(r"\D", "", str(orgao.get("cnpj") or pncp_payload.get("cnpjOrgao") or ""))
    uf = unidade.get("ufSigla") or pncp_payload.get("uf") or ""
    municipio = unidade.get("municipioNome") or pncp_payload.get("municipio") or ""
    objeto = pncp_payload.get("objetoCompra") or pncp_payload.get("objeto") or ""
    valor = float(pncp_payload.get("valorTotalEstimado") or 0)
    modalidade = modality_from_pncp(pncp_payload) if pncp_payload else ModalityEnum.PREGAO_ELETRONICO

    combined_md = "\n\n".join(doc.markdown for doc in parsed_docs)
    all_refs = [ref for doc in parsed_docs for ref in doc.refs]
    sections_found = sorted({key for doc in parsed_docs for key in doc.sections})

    objeto_citacao = None
    for doc in parsed_docs:
        objeto_citacao = extract_objeto(doc)
        if objeto_citacao:
            if not objeto:
                objeto = objeto_citacao.texto[:500]
            break

    dates = extract_dates_from_text(combined_md)
    abertura = dates.get("data_abertura_propostas")
    sessao = dates.get("data_sessao_disputa") or abertura
    limite = dates.get("limite_impugnacao")
    limite_fonte = "edital" if limite else None

    # Datas PNCP prevalecem se o edital não trouxe
    if not abertura and pncp_payload.get("dataAberturaProposta"):
        try:
            abertura = datetime.fromisoformat(
                str(pncp_payload["dataAberturaProposta"]).replace("Z", "+00:00")
            )
        except ValueError:
            pass
    if not sessao and pncp_payload.get("dataEncerramentoProposta"):
        try:
            sessao = datetime.fromisoformat(
                str(pncp_payload["dataEncerramentoProposta"]).replace("Z", "+00:00")
            )
        except ValueError:
            pass

    # Art. 164: só calcula se houver data de abertura conhecida
    if not limite and (sessao or abertura):
        base = sessao or abertura
        assert base is not None
        limite = prazo_impugnacao_datetime(base)
        limite_fonte = "calculado_art_164"
        avisos.append(
            f"limite_impugnacao calculado por {ART_164_REF} "
            f"(3 dias úteis antes de {base.date().isoformat()}), "
            "pois o edital não fixou data explícita no texto analisado."
        )

    beneficios = extract_me_epp_benefits(combined_md, all_refs) if combined_md else None
    itens = items_from_pncp(pncp_itens or [])

    for field_name, value in (
        ("orgao_comprador", orgao_nome),
        ("cnpj_orgao", cnpj),
        ("uf", uf),
        ("municipio", municipio),
        ("objeto_resumido", objeto),
        ("data_abertura_propostas", abertura),
        ("data_sessao_disputa", sessao),
        ("limite_impugnacao", limite),
    ):
        if value in (None, ""):
            missing.append(field_name)

    tender = TenderSchema(
        id_pncp=id_pncp,
        orgao_comprador=orgao_nome or "NÃO INFORMADO NO TEXTO/PNCP",
        cnpj_orgao=cnpj or "00000000000000",
        uf=uf or "NA",
        municipio=municipio or "NÃO INFORMADO",
        modalidade=modalidade,
        objeto_resumido=objeto or "Objeto não localizado no edital/PNCP — não inventado.",
        data_abertura_propostas=abertura,
        data_sessao_disputa=sessao,
        limite_impugnacao=limite,
        limite_impugnacao_fonte=limite_fonte,
        valor_total_estimado=valor,
        itens=itens,
        beneficios_me_epp=beneficios,
        objeto_citacao=objeto_citacao,
        avisos=avisos,
    )

    return TenderExtractionResult(
        tender=tender,
        missing_fields=missing,
        sections_found=sections_found,
        engine="heuristic+pncp",
        source_files=[str(doc.source_path) for doc in parsed_docs],
    )


def extract_from_markdown(markdown: str, *, id_pncp: str = "UNKNOWN") -> TenderExtractionResult:
    parsed = ParsedDocument(
        source_path=__import__("pathlib").Path("inline.md"),
        markdown=markdown,
        sections={},
        refs=[],
        engine="inline",
    )
    from src.parser.docling_parser import refs_from_markdown, split_sections

    parsed.sections = split_sections(markdown)
    parsed.refs = refs_from_markdown(markdown)
    return build_tender_from_sources(id_pncp=id_pncp, parsed_docs=[parsed])


async def extract_with_llm(markdown: str) -> dict[str, Any]:
    """Opcional: LLM estruturado. Só usa trechos fornecidos; ver EXTRACTOR_SYSTEM_PROMPT."""
    from src.config import get_settings

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY não configurada; use a extração heurística.")

    from langchain_openai import ChatOpenAI
    from pydantic import BaseModel

    class PartialExtraction(BaseModel):
        objeto_resumido: str | None = None
        documentos_mencionados: list[str] = []
        avisos: list[str] = []

    llm = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=0)
    structured = llm.with_structured_output(PartialExtraction)
    prompt = (
        EXTRACTOR_SYSTEM_PROMPT
        + "\n\nTEXTO DO EDITAL (não complete lacunas):\n"
        + markdown[:120_000]
    )
    result = await structured.ainvoke(prompt)
    return result.model_dump()


TenderExtractionAgent = extract_from_markdown
