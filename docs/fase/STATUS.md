# Status de desenvolvimento — LicitAll

> Fonte de verdade da fase atual para IAs e desenvolvedores. Atualizar a cada entrega significativa.

**Última atualização:** 2026-08-24  
**Fase atual:** 5 — Peças e WhatsApp (núcleo)  
**Repositório:** https://github.com/Andersonspita/licitall  
**Marco legal:** Lei Federal nº 14.133/2021 + LC 123/2006 + disclaimer Lei 8.906/1994

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
- [x] Score CNAE/geo/porte, API, LangGraph matcher, docs/testes
- [ ] Validar contra base Minha Receita populada (ETL)

### Fase 5 — Peças e WhatsApp
- [x] Kit de minutas (proposta, esclarecimento, impugnação, declarações) + disclaimer OAB
- [x] Impugnação só com riscos detectados (anti-alucinação)
- [x] Persistência em `data/raw/{id}/_kit/`
- [x] Outreach Evolution (preview + send)
- [x] Endpoints `/advisory/*` e `/outreach/whatsapp/*`
- [x] Testes `tests/test_fase5_advisory.py`
- [x] Docs `docs/tecnica/FASE5_ADVISORY.md`
- [ ] Validar envio real com instância Evolution conectada (QR)

---

## Próxima ação recomendada

1. Smoke ponta a ponta local (compose + um edital PNCP + kit + preview WhatsApp).  
2. Conectar Evolution (QR) e testar `POST /outreach/whatsapp/opportunity`.  
3. Ciclo de polish: corpus TCU, ETL Minha Receita, export PDF das minutas.
