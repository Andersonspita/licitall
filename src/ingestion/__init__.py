"""Ingestão PNCP."""

from src.ingestion.client import PncpClient, PncpId, parse_id_pncp

__all__ = ["PncpClient", "PncpId", "parse_id_pncp"]
