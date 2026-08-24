# LicitAll

Plataforma B2G de automação do ciclo de vendas públicas: mineração PNCP → parsing → agentes → matchmaking → peças → WhatsApp.

## Status atual

**Fase 5 — Peças e WhatsApp** (núcleo). Marco: **Lei 14.133/2021** + disclaimer **Lei 8.906/1994**.

Detalhes: [STATUS](docs/fase/STATUS.md) · [Fase 5](docs/tecnica/FASE5_ADVISORY.md) · [Compliance](docs/tecnica/COMPLIANCE_14133.md) · [Usuário](docs/usuario/GUIA_RAPIDO.md) · [AGENTS](AGENTS.md)


## O que entra neste repositório

| Incluído | Excluído (referências locais no workspace) |
|----------|--------------------------------------------|
| `src/`, `docker/`, `docs/`, `docker-compose.yml`, `requirements.txt` | `DS4SD.Docling`, `langgraph`, `crewAI-examples`, `ragflow`, `minha-receita`, `querido-diario`, `evolution-api` |

## Subir localmente

```powershell
copy .env.example .env
docker compose up -d
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
```

- API: http://localhost:8000/health  
- Docs OpenAPI: http://localhost:8000/docs  
- Postgres+pgvector: `5432` · Redis: `6379` · Minha Receita: `8001` · Evolution: `8080`

## Endpoints úteis

- `GET /health`
- `POST /ingestion/pncp/sync` — sincroniza publicações PNCP
- `POST /ingestion/pncp/{id_pncp}/documents` — baixa Edital/TR em `data/raw/`
- `GET /ingestion/pncp/{id_pncp}/itens`
- `POST /parser/{id_pncp}` — Markdown segmentado (Docling)
- `POST /agents/{id_pncp}/extract` — `TenderSchema` + checklist + Art. 164 + RAG
- `POST /agents/{id_pncp}/graph` — LangGraph completo (inclui matches)
- `POST /rag/index/lei-14133` / `GET /rag/search` — base jurídica
- `POST /matching/search` / `POST /matching/{id_pncp}` — empresas ATIVAS (CNAE/geo/porte)
- `POST /advisory/generate` / `POST /advisory/{id}/kit` — minutas + disclaimer OAB
- `POST /outreach/whatsapp/preview` / `opportunity` — alerta Evolution

## Deploy na VPS

Adiado. Guia: [docs/tecnica/DEPLOY_VPS.md](docs/tecnica/DEPLOY_VPS.md).

## Compliance

Marco: **Lei 14.133/2021**. Peças futuras são minutas (Lei 8.906/1994). Extrações citam página/parágrafo; impugnação em **dias úteis** (Art. 164). Ver [docs/tecnica/COMPLIANCE_14133.md](docs/tecnica/COMPLIANCE_14133.md).
