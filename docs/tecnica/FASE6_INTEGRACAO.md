# Fase 6 — Integração operacional

Orquestração ponta a ponta e verificação de dependências Docker.

## Objetivo

Unificar o fluxo manual (`sync` → `parser` → `extract` → `matching` → `kit` → WhatsApp) em um único endpoint e preparar smoke com Compose.

## Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/health/deps` | Ping Postgres, Redis, Minha Receita, Evolution |
| POST | `/pipeline/{id_pncp}/run` | Pipeline completo para uma contratação |

### `POST /pipeline/{id_pncp}/run`

Corpo JSON (opcional):

```json
{
  "company": {
    "razao_social": "Empresa Exemplo LTDA",
    "cnpj": "12345678000199"
  },
  "download_if_missing": true,
  "persist_kit": true,
  "run_matching": true,
  "whatsapp_phone": "5511999999999",
  "send_whatsapp": false
}
```

Etapas executadas:

1. Index RAG Lei 14.133 (se necessário)
2. Download PNCP (se não houver PDFs em `data/raw/{slug}`)
3. Parse + extração + checklist + riscos (RAG)
4. Matchmaking Minha Receita (empresas ATIVAS)
5. Kit de minutas com disclaimer OAB
6. Preview WhatsApp (envio só com `send_whatsapp=true`)

## Smoke Compose

```powershell
docker compose up -d
uvicorn src.main:app --reload --port 8000
python scripts/smoke_compose.py --api http://127.0.0.1:8000
```

O script:

- Sobe o Compose (se Docker estiver disponível)
- Aguarda `/health/deps` com todos os serviços up
- Testa `POST /ingestion/pncp/sync` (Postgres)
- Roda `POST /pipeline/{id}/run` na licitação de smoke

## Pré-requisitos operacionais

| Serviço | Porta | Observação |
|---------|-------|------------|
| PostgreSQL + pgvector | 5432 | Sync PNCP + embeddings RAG |
| Redis | 6379 | Evolution cache |
| Minha Receita | 8001 | ETL da base CNPJ em `data/minha-receita` |
| Evolution API | 8080 | WhatsApp transacional |
| Evolution Manager | 3000 | QR code da instância |

Guia passo a passo: `docs/usuario/OPERACAO_DOCKER.md`.

## Compliance

- Não envia WhatsApp sem `send_whatsapp=true` e número válido.
- Minutas sempre com rodapé OAB; impugnação só para riscos detectados no edital.
- Matchmaking restrito a empresas **ATIVAS**; ME/EPP conforme LC 123.
