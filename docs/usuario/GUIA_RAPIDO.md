# Guia rápido — operador LicitAll

## O que o sistema faz

1. Busca licitações publicadas no PNCP  
2. Baixa editais e termos de referência  
3. (Fases seguintes) Analisa documentos, encontra empresas elegíveis e envia alertas

Hoje (Fase 1) você já consegue **sincronizar** e **baixar** documentos.

## Subir o ambiente (dev)

1. Copie `.env.example` para `.env`  
2. `docker compose up -d`  
3. Ative o venv e rode `uvicorn src.main:app --reload --port 8000`  
4. Abra http://localhost:8000/docs

## Sincronizar editais

No Swagger, use `POST /ingestion/pncp/sync` ou:

```bash
curl -X POST http://localhost:8000/ingestion/pncp/sync ^
  -H "Content-Type: application/json" ^
  -d "{\"uf\":\"SP\",\"only_open\":true}"
```

## Baixar anexos de uma licitação

Use o `numeroControlePNCP` retornado na sync, por exemplo:

`POST /ingestion/pncp/00394452000103-1-000033/2024/documents`

Arquivos ficam em `data/raw/...`.

## Avisos importantes

- Textos de proposta/impugnação gerados depois serão **minutas**: precisam de revisão humana/advogado (Lei 8.906/1994).  
- O sistema não deve inventar exigências que não estejam no edital.  
- Minha Receita só encontra empresas depois que a base CNPJ estiver carregada no serviço.
