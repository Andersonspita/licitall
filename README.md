# LicitAll

Plataforma B2G de automação do ciclo de vendas públicas: mineração PNCP → parsing → agentes → matchmaking → peças → WhatsApp.

## Status atual

**Fase 1 — Fundação e ingestão PNCP** (em andamento / bootstrap concluído).

Detalhes: [docs/fase/STATUS.md](docs/fase/STATUS.md) · Técnica: [docs/tecnica/ARQUITETURA.md](docs/tecnica/ARQUITETURA.md) · Usuário: [docs/usuario/GUIA_RAPIDO.md](docs/usuario/GUIA_RAPIDO.md) · Devs/IA: [AGENTS.md](AGENTS.md)

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

## Endpoints úteis (Fase 1)

- `GET /health`
- `POST /ingestion/pncp/sync` — sincroniza publicações PNCP
- `POST /ingestion/pncp/{id_pncp}/documents` — baixa Edital/TR em `data/raw/`
- `GET /ingestion/pncp/{id_pncp}/itens`

## Deploy na VPS

Ver [docs/tecnica/DEPLOY_VPS.md](docs/tecnica/DEPLOY_VPS.md).

## Compliance

Peças geradas são **minutas de suporte de IA** (Lei 8.906/1994): exigem revisão humana. Extrações devem citar página/parágrafo do edital; prazos de impugnação em dias úteis (Art. 164, Lei 14.133/2021).
