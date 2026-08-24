# API — Fase 1

Base local: `http://localhost:8000`  
OpenAPI: `/docs`

## `GET /health`

Retorna status, versão e paths/URLs configurados.

## `POST /ingestion/pncp/sync`

Sincroniza publicações do PNCP e faz upsert em `tender_ingest`.

Body (JSON), todos opcionais:

```json
{
  "data_inicial": "2026-08-23",
  "data_final": "2026-08-24",
  "uf": "SP",
  "only_open": true,
  "modalidades": ["PREGAO_ELETRONICO", "CONCORRENCIA", "DISPENSA_ELETRONICA"]
}
```

Sem datas: usa ontem → hoje. Exige Postgres disponível.

## `POST /ingestion/pncp/{id_pncp}/documents`

Baixa anexos (Edital/TR) para `data/raw/{slug}/`.  
`id_pncp` no formato `CNPJ-1-SEQUENCIAL/ANO` (ex.: `00394452000103-1-000033/2024`).

## `GET /ingestion/pncp/{id_pncp}/itens`

Lista itens da contratação na API core do PNCP.

## `GET /ingestion/modalidades`

Lista modalidades filtradas por padrão na ingestão.

## `POST /parser/{id_pncp}`

Converte anexos em `data/raw/{id}` para Markdown segmentado (Docling ou fallback).  
Persiste metadados em `data/raw/{id}/_parsed/`.

## `POST /agents/{id_pncp}/extract`

Pipeline: parse + `TenderSchema` + checklist + triagem Lei 14.133 com RAG.

## `POST /agents/{id_pncp}/graph`

LangGraph: ingestion → parser → extractor → legal_analyzer → matcher (matcher ainda stub).

## `POST /rag/index/lei-14133`

Indexa corpus `data/legal/` (Lei 14.133 + seed TCU).

## `GET /rag/search?q=...&top_k=5`

Busca no índice jurídico.

## `POST /matching/search`

Body: `{ "tender": { ...TenderSchema-like }, "limit": 30, "min_score": 40, "require_proximity": false }`.  
Retorna empresas ATIVAS ranqueadas (Minha Receita).

## `POST /matching/{id_pncp}`

Extrai o edital e executa o matchmaking (CNAE + UF + porte / LC 123).

