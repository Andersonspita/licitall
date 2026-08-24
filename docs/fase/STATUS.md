# Status de desenvolvimento — LicitAll

> Fonte de verdade da fase atual para IAs e desenvolvedores. Atualizar a cada entrega significativa.

**Última atualização:** 2026-08-24  
**Fase atual:** 5 concluída (núcleo) + **smoke local em andamento**  
**Repositório:** https://github.com/Andersonspita/licitall  
**Marco legal:** Lei Federal nº 14.133/2021 + LC 123/2006 + disclaimer Lei 8.906/1994

---

## Checklist de fases

### Fase 1 — Fundação e ingestão
- [x] Docker, `src/`, PNCP client, API, docs, GitHub
- [x] Smoke PNCP online (`scripts/smoke_local.py`) — 1000+ publicações na janela testada
- [ ] Smoke Compose (Postgres/Redis/Evolution) — **Docker Desktop estava off neste ambiente**
- [ ] Deploy VPS — **adiado**

### Fase 2 — Parsing Docling e schemas
- [x] Compliance Art. 164 + LC 123, Docling/fallback, extractor, testes, docs
- [x] Smoke parse em PDF real PNCP (`83021808000182-1-000518/2026`, 6 anexos via pypdfium2)

### Fase 3 — LangGraph + RAG jurídico
- [x] Corpus Lei 14.133, RAG, grafo, endpoints, docs
- [x] Smoke RAG index (17 chunks) + `POST /rag/index/lei-14133`
- [ ] Expandir corpus / checkpoint Postgres em produção

### Fase 4 — Matchmaking Minha Receita
- [x] Score CNAE/geo/porte, API, LangGraph matcher, docs/testes
- [x] Smoke score heurístico (OK)
- [ ] Validar contra base Minha Receita populada (ETL)

### Fase 5 — Peças e WhatsApp
- [x] Kit de minutas + disclaimer OAB + Evolution preview/send APIs
- [x] Smoke kit em edital real (`POST /advisory/{id}/kit` → `_kit/*.md`)
- [x] Smoke outreach preview (API)
- [ ] Envio real WhatsApp (Evolution + QR)

---

## Resultado do smoke (2026-08-24)

| Check | Resultado |
|-------|-----------|
| PNCP consulta | OK |
| Download anexos | OK (6 PDFs) |
| Parse seções | OK (fallback pypdfium2; Docling não exigido) |
| RAG Lei 14.133 | OK |
| API `/health` | OK (`fase=5-advisory-outreach`) |
| Kit minutas | OK (Art. 164 calculado + disclaimer OAB) |
| Docker Compose | SKIP (daemon off) |
| Minha Receita ETL / Evolution QR | SKIP |

Script: `scripts/smoke_local.py` · Doc: `docs/tecnica/SMOKE_LOCAL.md`

## Próxima ação recomendada

1. Ligar **Docker Desktop** e rodar `docker compose up -d` (Postgres + Redis + Evolution + Minha Receita).  
2. Conectar QR no Evolution e testar `POST /outreach/whatsapp/opportunity`.  
3. Carregar ETL Minha Receita e validar `POST /matching/{id}`.  
4. (Opcional) Instalar Docling completo e reparsear os PDFs.
