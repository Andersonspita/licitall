"""RAG jurídico LicitAll. Imports pesados sob demanda via submódulos."""

__all__ = [
    "load_legal_corpus",
    "ensure_legal_index",
    "retrieve_legal_context",
    "get_legal_store",
]


def load_legal_corpus():
    from src.rag.corpus import load_legal_corpus as _load

    return _load()


def get_legal_store():
    from src.rag.retriever import get_legal_store as _get

    return _get()


async def ensure_legal_index() -> int:
    from src.rag.retriever import ensure_legal_index as _ensure

    return await _ensure()


async def retrieve_legal_context(query: str, *, top_k: int = 5):
    from src.rag.retriever import retrieve_legal_context as _retrieve

    return await _retrieve(query, top_k=top_k)
