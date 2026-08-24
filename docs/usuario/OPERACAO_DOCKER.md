# Operação com Docker — LicitAll

Guia para subir a stack local e validar o fluxo ponta a ponta.

## 1. Pré-requisitos

- Docker Desktop **ligado**
- Python 3.11+ com dependências (`pip install -r requirements.txt`)
- Arquivo `.env` (copie de `.env.example` se existir)

## 2. Subir serviços

```powershell
cd D:\Projetos\licitAll
docker compose up -d
docker compose ps
```

Portas:

| Serviço | URL |
|---------|-----|
| PostgreSQL | `localhost:5433` (padrão; evita conflito com 5432) |
| Redis | `localhost:6380` |
| Minha Receita | http://localhost:8001 (`docker compose --profile full up -d`) |
| Evolution API | http://localhost:8081 |
| Evolution Manager (QR) | http://localhost:3001 |

## 3. API FastAPI

```powershell
uvicorn src.main:app --reload --port 8000
```

Verifique:

```powershell
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/deps
```

## 4. Minha Receita (ETL)

A imagem sobe vazia até carregar dados da Receita Federal.

1. Baixe os dumps oficiais para `data/minha-receita/`
2. Siga a documentação do projeto [Minha Receita](https://github.com/cuducos/minha-receita) para importar no Postgres (`minhareceita`)
3. Teste: `GET http://localhost:8001/12345678000199`

Sem ETL, o matching retorna aviso e lista vazia — o restante do pipeline funciona.

## 5. Evolution (WhatsApp)

1. Abra http://localhost:3000
2. Crie/conecte a instância configurada em `EVOLUTION_INSTANCE` (padrão no `.env`)
3. Escaneie o QR no celular
4. Preview (sem enviar):

```powershell
curl -X POST http://127.0.0.1:8000/outreach/whatsapp/preview -H "Content-Type: application/json" -d "{\"phone\":\"5511999999999\",\"orgao\":\"Teste\",\"objeto\":\"Objeto\",\"valor_total\":1000,\"id_pncp\":\"000/2026\"}"
```

Envio real: `POST /outreach/whatsapp/opportunity` ou pipeline com `"send_whatsapp": true`.

## 6. Pipeline ponta a ponta

Com edital já baixado (ex.: smoke PNCP):

```powershell
curl -X POST "http://127.0.0.1:8000/pipeline/83021808000182-1-000518/2026/run" -H "Content-Type: application/json" -d "{\"download_if_missing\":false,\"persist_kit\":true}"
```

Minutas em `data/raw/{slug}/_kit/*.md`.

## 7. Smoke automatizado

```powershell
python scripts/smoke_compose.py --api http://127.0.0.1:8000
```

Smoke sem Docker (só PNCP/RAG/kit):

```powershell
python scripts/smoke_local.py --api http://127.0.0.1:8000
```

## 8. Troubleshooting

| Sintoma | Ação |
|---------|------|
| `dockerDesktopLinuxEngine` pipe não encontrado | Ligar Docker Desktop |
| Postgres down em `/health/deps` | `docker compose logs postgres` |
| Minha Receita 502 no matching | Carregar ETL ou ignorar com `run_matching: false` |
| Evolution 502 no envio | Conferir QR, API key e instância |
