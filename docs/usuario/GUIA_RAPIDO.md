# Guia rápido — operador LicitAll

## O que o sistema faz

1. Busca licitações publicadas no PNCP  
2. Baixa editais e termos de referência  
3. Converte PDFs em texto estruturado e monta um resumo do edital (Lei 14.133/2021)  
4. (Fases seguintes) Encontra empresas elegíveis e envia alertas

## Subir o ambiente (dev)

1. Copie `.env.example` para `.env`  
2. `docker compose up -d`  
3. Ative o venv e rode `uvicorn src.main:app --reload --port 8000`  
4. Abra http://localhost:8000/docs

## Fluxo do dia a dia (Fase 2)

1. **Sincronizar** — `POST /ingestion/pncp/sync` (ex.: `{"uf":"SP","only_open":true}`)  
2. **Baixar anexos** — `POST /ingestion/pncp/{numeroControlePNCP}/documents`  
3. **Parsear** — `POST /parser/{numeroControlePNCP}`  
4. **Extrair** — `POST /agents/{numeroControlePNCP}/extract` (com RAG da Lei 14.133)  
5. **Grafo completo** — `POST /agents/{numeroControlePNCP}/graph`  
6. **Match de empresas** — `POST /matching/{numeroControlePNCP}` (requer Minha Receita com base carregada)  
7. **Kit de minutas** — `POST /advisory/{numeroControlePNCP}/kit`  
8. **WhatsApp (preview)** — `POST /outreach/whatsapp/preview`

Antes, uma vez: `POST /rag/index/lei-14133`.

O resultado traz objeto, itens, checklist, riscos (Lei 14.133), matches e minutas com **disclaimer OAB** (Lei 8.906/1994). Impugnação só usa vícios detectados no edital.

## Próximos passos (operador)

1. Ligar Docker Desktop e `docker compose up -d`  
2. Conectar WhatsApp no Evolution Manager (porta 3000)  
3. Rodar `python scripts/smoke_local.py --api http://127.0.0.1:8000`
