# Guia do usuário — funcionalidades e como usar

PDF gerado: **[`LicitAll_Guia_Usuario.pdf`](./LicitAll_Guia_Usuario.pdf)**  
Regenerar: `python scripts/gerar_guia_pdf.py`

## Acesso

1. `docker compose up -d`
2. `uvicorn src.main:app --reload --port 8000`
3. http://127.0.0.1:8000/ → login (`admin@licitall.local` / `licitall`)

## Dados reais

- Lista / filtros: `GET /tenders?uf=&status=&q=&limit=&offset=`
- KPIs: `GET /tenders/stats`
- Detalhe: `GET /tenders/{id_pncp}`
- Fonte: Postgres `tender_ingest` (após sync PNCP). Sem sync, a UI mostra vazio — **não há mais mocks**.

## Fluxo recomendado

1. **Monitor PNCP** → sync  
2. **Editais & TRs** → filtrar / abrir  
3. Documents → Parser → Extract/Graph  
4. Matchmaking → Peças (`?id=`) → WhatsApp preview  

Detalhes de API: `docs/usuario/GUIA_RAPIDO.md` · Telas: `INTERFACE_WEB.md`.
