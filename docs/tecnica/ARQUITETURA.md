# Arquitetura técnica — LicitAll

## Visão

```
PNCP / (Querido Diário futuro)
        │
        ▼
  [1 ingestion] ── PDFs → data/raw/{id}
        │
        ▼
  [2 parser Docling] → Markdown segmentado
        │
        ▼
  [3 agents LangGraph]
      extractor │ legal RAG │ checklist
        │
        ▼
  [4 matching] ← Minha Receita (CNAE, UF, porte, ATIVA)
        │
        ▼
  [5 advisory] → minutas + disclaimer OAB
        │
        ▼
  [6 outreach] → Evolution API (WhatsApp)
```

## Layout do repositório

```
src/
  config/       # Settings (pydantic-settings)
  db/           # Engine async SQLModel
  models/       # Enums, Pydantic, SQLModel
  ingestion/    # Client PNCP + storage + sync
  parser/       # Wrapper Docling
  agents/       # Grafo LangGraph (esqueleto Fase 3)
  matching/     # Client Minha Receita + score
  advisory/     # Minutas + disclaimer
  outreach/     # Evolution client
  main.py       # FastAPI
docker/
  postgres/init.sql
  evolution.env
docs/
  tecnica/  usuario/  fase/
```

## Serviços Docker

| Serviço | Porta host | Função |
|---------|------------|--------|
| postgres | 5432 | DBs `licitall`, `minhareceita`, `evolution` + pgvector |
| redis | 6379 | Cache / filas leves / Evolution |
| minha-receita | 8001 | API CNPJ |
| evolution-api | 8080 | WhatsApp |
| evolution-frontend | 3000 | Manager QR |

A API FastAPI **não** roda no Compose por padrão: `uvicorn src.main:app --port 8000`.

## PNCP

- Consulta: `https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao`
- Obrigatórios: `dataInicial`, `dataFinal` (AAAAMMDD), `codigoModalidadeContratacao`, `pagina`
- Modalidades default: 6 (Pregão Eletrônico), 4 (Concorrência Eletrônica), 8 (Dispensa)
- Arquivos: API core `/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos`

## Dados principais

- `TenderSchema` / `TenderItem` / `LegalRiskItem` — domínio semântico (Pydantic)
- `TenderIngest` — payload bruto PNCP + metadados (Postgres JSONB)

## Integrações (URLs default)

Ver `.env.example`: `DATABASE_URL`, `REDIS_URL`, `MINHA_RECEITA_BASE_URL`, `EVOLUTION_API_URL`, chaves LLM.
