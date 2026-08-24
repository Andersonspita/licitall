# Status de desenvolvimento — LicitAll

> Fonte de verdade da fase atual para IAs e desenvolvedores. Atualizar a cada entrega significativa.

**Última atualização:** 2026-08-24  
**Fase atual:** 3 — LangGraph + RAG Lei 14.133/2021 (núcleo em andamento)  
**Repositório:** https://github.com/Andersonspita/licitall  
**Marco legal:** Lei Federal nº 14.133/2021 (nova lei) + LC 123/2006

---

## Checklist de fases

### Fase 1 — Fundação e ingestão
- [x] Docker, `src/`, PNCP client, API, docs, GitHub
- [ ] Smoke test local compose + sync PNCP
- [ ] Deploy VPS — **adiado**

### Fase 2 — Parsing Docling e schemas
- [x] Compliance Art. 164 + LC 123
- [x] Docling/fallback, extractor, checklist, endpoints, testes, docs
- [ ] Smoke parse em PDF real do PNCP

### Fase 3 — LangGraph + RAG jurídico
- [x] Corpus Lei 14.133 + seed TCU em `data/legal/`
- [x] `src/rag/` (embeddings, store, retriever)
- [x] Triagem legal enriquecida com RAG
- [x] Grafo LangGraph: ingestion → parser → extractor → legal → matcher
- [x] Endpoints `/rag/index/lei-14133`, `/rag/search`, `/agents/{id}/graph`
- [x] Docs `docs/tecnica/FASE3_RAG.md`
- [ ] Expandir corpus com texto integral / mais acórdãos TCU
- [ ] Checkpoint Postgres do LangGraph em produção
- [ ] Matcher real (Fase 4)

### Fase 4 — Matchmaking Minha Receita
- [ ] ETL/carga CNPJ + score CNAE/geo/porte (só ATIVAS)

### Fase 5 — Peças e WhatsApp
- [ ] Minutas + disclaimer OAB + Evolution

---

## Próxima ação recomendada

1. `POST /rag/index/lei-14133` e validar `GET /rag/search?q=artigo+164`.  
2. Rodar `POST /agents/{id}/graph` após baixar um edital.  
3. Expandir corpus TCU e ligar Fase 4 (matching).
