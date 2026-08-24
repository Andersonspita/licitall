# Status de desenvolvimento — LicitAll

> Fonte de verdade da fase atual para IAs e desenvolvedores. Atualizar a cada entrega significativa.

**Última atualização:** 2026-08-24  
**Fase atual:** 4 — Matchmaking Minha Receita (núcleo)  
**Repositório:** https://github.com/Andersonspita/licitall  
**Marco legal:** Lei Federal nº 14.133/2021 + LC 123/2006

---

## Checklist de fases

### Fase 1 — Fundação e ingestão
- [x] Docker, `src/`, PNCP client, API, docs, GitHub
- [ ] Smoke test local compose + sync PNCP
- [ ] Deploy VPS — **adiado**

### Fase 2 — Parsing Docling e schemas
- [x] Compliance Art. 164 + LC 123, Docling, extractor, testes, docs
- [ ] Smoke parse em PDF real do PNCP

### Fase 3 — LangGraph + RAG jurídico
- [x] Corpus Lei 14.133, RAG, grafo, endpoints, docs
- [ ] Expandir corpus / checkpoint Postgres em produção

### Fase 4 — Matchmaking Minha Receita
- [x] Mapa heurístico objeto → CNAE
- [x] Score CNAE + UF/município + porte (só ATIVAS)
- [x] `MatchmakingService` + respeito a exclusividade ME/EPP (LC 123)
- [x] Nó `matcher` no LangGraph
- [x] Endpoints `/matching/search` e `/matching/{id}`
- [x] Testes `tests/test_fase4_matching.py`
- [x] Docs `docs/tecnica/FASE4_MATCHING.md`
- [ ] Validar contra base Minha Receita populada (ETL)

### Fase 5 — Peças e WhatsApp
- [ ] Minutas + disclaimer OAB + Evolution

---

## Próxima ação recomendada

1. Popular Minha Receita (ETL) e testar `POST /matching/{id}`.  
2. Iniciar **Fase 5**: gerador de minutas (Art. 164) + Evolution WhatsApp.
