"""Consulta e estatísticas de editais ingeridos (tender_ingest)."""

from src.tenders.service import (
    get_tender,
    list_tenders,
    serialize_tender,
    tender_stats,
)

__all__ = ["get_tender", "list_tenders", "serialize_tender", "tender_stats"]
