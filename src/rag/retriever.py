from __future__ import annotations

from src.rag.store import LegalStore, RetrievedChunk

_store: LegalStore | None = None


def get_legal_store() -> LegalStore:
    global _store
    if _store is None:
        _store = LegalStore()
    return _store


async def retrieve_legal_context(query: str, *, top_k: int = 5) -> list[RetrievedChunk]:
    return await get_legal_store().search(query, top_k=top_k)


async def ensure_legal_index() -> int:
    store = get_legal_store()
    if store._memory:
        return len(store._memory)
    return await store.index_corpus()
