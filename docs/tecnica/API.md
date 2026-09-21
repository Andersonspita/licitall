# API — Fase 1

Base local: `http://localhost:8000`  
OpenAPI: `/docs`

## UI web

Base: `http://localhost:8000/ui/` · Login: `/ui/login.html` · Dashboard: `/ui/dashboard.html`  
Doc: [INTERFACE_WEB.md](../usuario/INTERFACE_WEB.md)

## `GET /tenders`

Lista editais reais de `tender_ingest`.

Query: `uf`, `status`, `q` (busca textual), `limit` (máx. 200), `offset`.

Resposta: `{ total, limit, offset, items[] }` — cada item inclui `art164` (prazo calculado Art. 164).

## `GET /tenders/stats`

KPIs: `total`, `valor_total_estimado_sum`, `by_status`, `by_uf`, `prazos_criticos` (≤ 3 dias úteis).

## `GET /tenders/{id_pncp}`

Detalhe + `filesystem` (docs/parsed/kit em `data/raw`).

## `GET /health`

Retorna status, versão e paths/URLs configurados.

## `POST /ingestion/pncp/sync/async`

Sync **assíncrono**. Padrão **`uf=BR`** (Brasil): percorre as 27 UFs uma a uma (a API nacional sem UF estoura timeout).  
**Commit a cada página** → `GET /tenders` já lista editais enquanto o job roda.

```json
{ "uf": "BR", "only_open": true }
```

Ou uma UF: `{ "uf": "SP" }`. Janela máx. 7 dias.

## `GET /ingestion/pncp/sync/jobs/{job_id}`

Status do job: `queued | running | succeeded | partial | failed`, `ingested`, `pages_done`, `log[]`.

UI (dashboard/monitor) usa este fluxo com polling.

## `POST /ingestion/pncp/sync`

Sincroniza publicações do PNCP e faz upsert em `tender_ingest` (**síncrono / legado**).  
**UF obrigatória.** Prefira `/sync/async`.

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

LangGraph: ingestion → parser → extractor → legal_analyzer → matcher (score explicável + elegibilidade).

## `POST /rag/index/lei-14133`

Indexa corpus `data/legal/` (Lei 14.133 + seed TCU).

## `GET /rag/search?q=...&top_k=5`

Busca no índice jurídico.

## `POST /matching/search`

Body: `{ "tender": { ...TenderSchema-like }, "limit": 30, "min_score": 40, "require_proximity": false }`.  
Retorna empresas ATIVAS ranqueadas com score explicável, `recommendation` (BID/REVIEW/SKIP) e elegibilidade YAML.

## `POST /matching/company`

Match inverso CNPJ → oportunidades. Body: `{ "cnpj", "tenders"?, "limit", "min_score", "require_proximity", "uf" }`.  
Sem `tenders`, lê `tender_ingest` (Postgres). Ver [FASE4_MATCHING.md](FASE4_MATCHING.md).

## `POST /matching/{id_pncp}`

Extrai o edital e executa o matchmaking (CNAE + geo + porte / LC 123 + prazo/Art. 164).

## `POST /advisory/generate`

Gera kit de minutas a partir de `tender` (+ `company` opcional). Inclui disclaimer Lei 8.906/1994.

## `POST /advisory/{id_pncp}/kit`

Extrai o edital e gera/persiste o kit em `data/raw/.../_kit/`.

## `POST /outreach/whatsapp/preview`

Monta mensagem de oportunidade sem enviar.

## `POST /outreach/whatsapp/opportunity`

Envia via Evolution API (`EVOLUTION_API_URL` / `EVOLUTION_API_KEY` / `EVOLUTION_INSTANCE`).

## `POST /outreach/whatsapp/digest/preview` · `POST /outreach/whatsapp/digest`

Digest top-N oportunidades (score + BID/REVIEW/SKIP).

## `POST /outreach/whatsapp/digest/from-company`

Match inverso + digest (`send: false` = só preview).

