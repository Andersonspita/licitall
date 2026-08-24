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
5. **Grafo completo (Fase 3)** — `POST /agents/{numeroControlePNCP}/graph`

Antes, uma vez: `POST /rag/index/lei-14133`.

O resultado traz objeto, itens (PNCP), benefícios ME/EPP (se constarem no edital), checklist só com documentos citados, prazo de impugnação (edital ou Art. 164) e riscos com fundamentação na Lei 14.133/2021.

## Avisos importantes

- Marco legal: **Lei 14.133/2021** (nova lei de licitações).  
- Textos de proposta/impugnação futuros serão **minutas**: revisão humana/advogado (Lei 8.906/1994).  
- O sistema **não inventa** certidões que não estejam no edital.  
- Impugnação: em regra, até **3 dias úteis** antes da abertura (Art. 164), se o edital não fixar outra data válida.
