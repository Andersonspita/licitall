# Smoke test local

## Pré-requisitos

1. Python 3.11+ com `pip install -r requirements.txt` (ou deps mínimas do smoke)
2. Opcional: Docker Desktop ligado + `docker compose up -d`
3. Opcional: `uvicorn src.main:app --port 8000`

## Comando

```powershell
python scripts/smoke_local.py
python scripts/smoke_local.py --api http://127.0.0.1:8000
```

## O que valida

| Check | Dependência |
|-------|-------------|
| PNCP `contratacoes/publicacao` | Internet |
| RAG corpus Lei 14.133 | Disco `data/legal/` |
| Kit de minutas + disclaimer OAB | Código |
| Preview WhatsApp | Código |
| Matching score / CNAE | Código |
| Docker daemon | Docker Desktop |
| API `/health`, `/rag/index`, outreach preview | uvicorn |

## Limitações conhecidas

- Sync PNCP → Postgres exige Compose (Postgres)
- Match real de CNPJ exige Minha Receita com ETL
- Envio WhatsApp real exige Evolution com QR conectado
- Parse Docling de PDF exige `docling` instalado e anexos baixados
