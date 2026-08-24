# Fase 3 — LangGraph + RAG jurídico (Lei 14.133/2021)

## Objetivo

Orquestrar o fluxo em grafo determinístico e fundamentar a triagem jurídica com
trechos indexados da **Lei 14.133/2021** e orientações seed do TCU.

## Componentes

| Peça | Função |
|------|--------|
| `data/legal/lei_14133/corpus.md` | Chunks operacionais (Arts. 5, 11, 40–41, 63, 66–69, 164, 4º/LC 123) |
| `data/legal/tcu/orientacoes_seed.md` | Seed de orientação (expandir com acórdãos) |
| `src/rag/` | Corpus, embeddings (OpenAI ou hash), store JSONB/memória, retriever |
| `src/agents/graph.py` | `ingestion → parser → extractor → legal_analyzer → matcher` |
| `src/agents/legal_rag.py` | Heurística + enriquecimento RAG |

## Endpoints

- `POST /rag/index/lei-14133` — (re)indexa o corpus
- `GET /rag/search?q=...` — busca semântica/lexical
- `POST /agents/{id}/extract` — pipeline com RAG
- `POST /agents/{id}/graph` — executa LangGraph completo

## Embeddings

- Com `OPENAI_API_KEY`: modelo `EMBEDDING_MODEL` (default `text-embedding-3-small`)
- Sem chave: embedding hash determinístico (dev/testes), suficiente para smoke do corpus

## Matcher

Nó `matcher` ainda é placeholder da **Fase 4** (Minha Receita).

## Compliance

Marco exclusivo: Lei 14.133/2021. RAG não inventa artigos: só recupera chunks indexados
e anexa à fundamentação dos riscos já detectados no texto do edital.
