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
- [x] Smoke Compose parcial — Postgres/Redis/Evolution API (portas 5433/6380/8081)
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
- [x] Smoke Compose parcial (2026-08-24) — Postgres/Redis/Evolution API OK; Minha Receita off; pipeline 200

---

## Smoke Compose (2026-08-24)

| Check | Resultado |
|-------|-----------|
| Postgres :5433 | OK |
| Redis :6380 | OK |
| Evolution API :8081 | OK |
| Evolution Manager :3001 | Falha nginx na imagem |
| Minha Receita :8001 | Off (atcr.io 401) |
| `POST /pipeline/{id}/run` | OK — 4 minutas + Art. 164 |
| PNCP sync Postgres | 429 rate limit (retentar) |

Portas alternativas evitam conflito com containers `barbershop-*` em 5432/6379/8080.

---

## Próxima ação recomendada

1. Minha Receita: `docker compose --profile full up -d` (ou build local do clone) + ETL  
2. Evolution QR: corrigir/pinar imagem do Manager ou usar API em :8081  
3. Retentar `POST /ingestion/pncp/sync` (PNCP pode retornar 429)  
4. Conectar WhatsApp e testar envio real

Script local (sem Docker): `scripts/smoke_local.py` · Doc: `docs/tecnica/SMOKE_LOCAL.md` · Fase 6: `docs/tecnica/FASE6_INTEGRACAO.md`
