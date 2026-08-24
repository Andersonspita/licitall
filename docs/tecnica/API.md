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

Pipeline Fase 2: parse + `TenderSchema` + checklist (só o que está no texto) + triagem Lei 14.133.  
`limite_impugnacao` usa data do edital ou cálculo Art. 164 (3 dias úteis).

