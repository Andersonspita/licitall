# Status de desenvolvimento — LicitAll

> Fonte de verdade da fase atual para IAs e desenvolvedores. Atualizar a cada entrega significativa.

**Última atualização:** 2026-08-24  
**Fase atual:** 2 — Parsing Docling e schemas (Lei 14.133/2021) — núcleo implementado  
**Repositório:** https://github.com/Andersonspita/licitall  
**Marco legal:** Lei Federal nº 14.133/2021 (nova lei) + LC 123/2006

---

## Checklist de fases

### Fase 1 — Fundação e ingestão
- [x] `docker-compose.yml` (Postgres+pgvector, Redis, Minha Receita, Evolution API)
- [x] Pacote `src/` + `requirements.txt` + settings
- [x] Schemas Pydantic e tabela `TenderIngest`
- [x] Client assíncrono PNCP + download em `data/raw/`
- [x] API FastAPI + documentação + GitHub (só produto)
- [ ] Validar `docker compose up` + sync PNCP real (smoke test local)
- [ ] Deploy VPS — **adiado**

### Fase 2 — Parsing Docling e schemas
- [x] Compliance Art. 164 (dias úteis) + LC 123 (`src/compliance/lei_14133.py`)
- [x] Segmentação de seções alinhada à Lei 14.133 (`src/parser/sections.py`)
- [x] Docling + fallback pypdfium2 + refs página/parágrafo
- [x] Extração `TenderSchema` sem inventar exigências (`extractor` + `pipeline`)
- [x] Checklist só com o que está no texto; triagem jurídica heurística
- [x] Endpoints `POST /parser/{id}` e `POST /agents/{id}/extract`
- [x] Testes `tests/test_lei_14133_fase2.py` (8 passed)
- [x] Docs `docs/tecnica/FASE2_PARSING.md` e `COMPLIANCE_14133.md`
- [ ] Rodar parse em PDF real baixado do PNCP (smoke com Docling instalado)

### Fase 3 — LangGraph + RAG jurídico
- [ ] Implementar nós do grafo (esqueleto existe)
- [ ] Base vetorial pgvector (texto Lei 14.133 + súmulas TCU)
- [ ] Substituir/ enriquecer triagem heurística por RAG com citação

### Fase 4 — Matchmaking Minha Receita
- [ ] ETL/carga CNPJ + score CNAE/geo/porte (só ATIVAS)

### Fase 5 — Peças e WhatsApp
- [ ] Minutas + disclaimer OAB + Evolution

---

## Próxima ação recomendada

1. Smoke test local: baixar um edital PNCP → `POST /parser/...` → `POST /agents/.../extract`.  
2. Iniciar **Fase 3**: indexar Lei 14.133 no pgvector e ligar os nós do LangGraph.  
3. VPS permanece adiada.
