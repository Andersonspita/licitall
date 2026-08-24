from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlmodel.ext.asyncio.session import AsyncSession

from src.ingestion.client import PncpClient, parse_id_pncp
from src.ingestion.storage import DocumentStorage
from src.models.enums import (
    DEFAULT_INGESTION_MODALITIES,
    PNCP_CODE_TO_MODALITY,
    ModalityEnum,
    TenderStatus,
)
from src.models.tables import TenderIngest

_OPEN_STATUS_HINTS = ("publicado", "recebendo proposta", "divulgada")


def _parse_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _orgao(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("orgaoEntidade") or item.get("orgao") or {}


def _unidade(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("unidadeOrgao") or {}


def map_pncp_item(item: dict[str, Any]) -> dict[str, Any]:
    orgao = _orgao(item)
    unidade = _unidade(item)
    modalidade_id = item.get("modalidadeId") or item.get("codigoModalidadeContratacao")
    modalidade: str | None = None
    if isinstance(modalidade_id, int) and modalidade_id in PNCP_CODE_TO_MODALITY:
        modalidade = PNCP_CODE_TO_MODALITY[modalidade_id].value
    elif item.get("modalidadeNome"):
        modalidade = str(item["modalidadeNome"])
    return {
        "id_pncp": item.get("numeroControlePNCP"),
        "orgao_comprador": orgao.get("razaoSocial") or item.get("orgaoRazaoSocial"),
        "cnpj_orgao": (orgao.get("cnpj") or item.get("cnpjOrgao") or "").replace(".", "").replace("/", "").replace("-", "") or None,
        "uf": unidade.get("ufSigla") or item.get("uf"),
        "municipio": unidade.get("municipioNome") or item.get("municipio"),
        "modalidade": modalidade,
        "objeto_resumido": item.get("objetoCompra") or item.get("objeto"),
        "valor_total_estimado": item.get("valorTotalEstimado"),
        "situacao": item.get("situacaoCompraNome") or item.get("situacao"),
        "data_publicacao": _parse_dt(item.get("dataPublicacaoPncp") or item.get("dataPublicacao")),
        "data_abertura_propostas": _parse_dt(item.get("dataAberturaProposta")),
        "data_encerramento_propostas": _parse_dt(item.get("dataEncerramentoProposta")),
        "payload": item,
        "status": TenderStatus.INGESTED.value,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


def is_open_for_proposals(item: dict[str, Any]) -> bool:
    situacao = str(item.get("situacaoCompraNome") or item.get("situacao") or "").lower()
    if not situacao:
        return True
    return any(hint in situacao for hint in _OPEN_STATUS_HINTS)


async def upsert_tender(session: AsyncSession, mapped: dict[str, Any]) -> None:
    if not mapped.get("id_pncp"):
        return
    stmt = insert(TenderIngest).values(**mapped)
    update_fields = {
        "orgao_comprador": stmt.excluded.orgao_comprador,
        "cnpj_orgao": stmt.excluded.cnpj_orgao,
        "uf": stmt.excluded.uf,
        "municipio": stmt.excluded.municipio,
        "modalidade": stmt.excluded.modalidade,
        "objeto_resumido": stmt.excluded.objeto_resumido,
        "valor_total_estimado": stmt.excluded.valor_total_estimado,
        "situacao": stmt.excluded.situacao,
        "data_publicacao": stmt.excluded.data_publicacao,
        "data_abertura_propostas": stmt.excluded.data_abertura_propostas,
        "data_encerramento_propostas": stmt.excluded.data_encerramento_propostas,
        "payload": stmt.excluded.payload,
        "updated_at": datetime.now(timezone.utc),
    }
    stmt = stmt.on_conflict_do_update(index_elements=["id_pncp"], set_=update_fields)
    await session.execute(stmt)


async def ingest_publicacoes(
    session: AsyncSession,
    client: PncpClient,
    *,
    data_inicial: date | datetime | str,
    data_final: date | datetime | str,
    uf: str | None = None,
    modalidades: tuple[ModalityEnum, ...] = DEFAULT_INGESTION_MODALITIES,
    only_open: bool = True,
) -> int:
    count = 0
    async for item in client.iter_publicacoes(
        data_inicial=data_inicial,
        data_final=data_final,
        uf=uf,
        modalidades=modalidades,
    ):
        if only_open and not is_open_for_proposals(item):
            continue
        await upsert_tender(session, map_pncp_item(item))
        count += 1
    await session.commit()
    return count


async def download_tender_documents(
    client: PncpClient,
    storage: DocumentStorage,
    id_pncp: str,
) -> list[str]:
    parsed = parse_id_pncp(id_pncp)
    arquivos = await client.get_arquivos(parsed)
    saved: list[str] = []
    for index, arquivo in enumerate(arquivos, start=1):
        url = arquivo.get("url") or arquivo.get("uri") or arquivo.get("urlDocumento")
        if not url:
            continue
        content = await client.download_bytes(str(url))
        filename = storage.filename_from_arquivo(arquivo, index)
        path = await storage.save_bytes(parsed, filename, content)
        saved.append(str(path))
    return saved
