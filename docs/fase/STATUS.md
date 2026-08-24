# Status de desenvolvimento — LicitAll

> Fonte de verdade da fase atual para IAs e desenvolvedores. Atualizar a cada entrega significativa.

**Última atualização:** 2026-08-24  
**Fase atual:** 6 — integração operacional (pipeline + health deps + smoke Compose)  
**Repositório:** https://github.com/Andersonspita/licitall  
**Marco legal:** Lei Federal nº 14.133/2021 + LC 123/2006 + disclaimer Lei 8.906/1994

---

## Checklist de fases

### Fase 1 — Fundação e ingestão
- [x] Docker, `src/`, PNCP client, API, docs, GitHub
- [x] Smoke PNCP online (`scripts/smoke_local.py`)
- [ ] Smoke Compose (Postgres/Redis/Evolution) — **Docker Desktop off neste ambiente**
- [ ] Deploy VPS — **adiado**

### Fase 2 — Parsing Docling e schemas
- [x] Compliance Art. 164 + LC 123, Docling/fallback, extractor, testes, docs
- [x] Smoke parse em PDF real PNCP

### Fase 3 — LangGraph + RAG jurídico
- [x] Corpus Lei 14.133, RAG, grafo, endpoints, docs
- [ ] Expandir corpus / checkpoint Postgres em produção

### Fase 4 — Matchmaking Minha Receita
- [x] Score CNAE/geo/porte, API, LangGraph matcher, docs/testes
- [ ] Validar contra base Minha Receita populada (ETL)

### Fase 5 — Peças e WhatsApp
- [x] Kit de minutas + disclaimer OAB + Evolution preview/send APIs
- [ ] Envio real WhatsApp (Evolution + QR)

### Fase 6 — Integração operacional
- [x] `GET /health/deps` — Postgres, Redis, Minha Receita, Evolution
- [x] `POST /pipeline/{id_pncp}/run` — download → extract → match → kit → preview
- [x] `scripts/smoke_compose.py` + `docs/usuario/OPERACAO_DOCKER.md`
- [x] Testes `tests/test_fase6_pipeline.py`
- [ ] Executar smoke Compose com Docker ligado

---

## Próxima ação recomendada

1. Ligar **Docker Desktop** → `docker compose up -d`  
2. `uvicorn src.main:app --port 8000`  
3. `python scripts/smoke_compose.py`  
4. ETL Minha Receita + QR Evolution para matching/envio reais

Script local (sem Docker): `scripts/smoke_local.py` · Doc: `docs/tecnica/SMOKE_LOCAL.md` · Fase 6: `docs/tecnica/FASE6_INTEGRACAO.md`
