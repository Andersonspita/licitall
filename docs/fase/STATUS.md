# Status de desenvolvimento — LicitAll

> Fonte de verdade da fase atual para IAs e desenvolvedores. Atualizar a cada entrega significativa.

**Última atualização:** 2026-08-24  
**Fase atual:** 1 — Fundação do backend e ingestão PNCP  
**Repositório:** https://github.com/Andersonspita/licitall

---

## Checklist de fases

### Fase 1 — Fundação e ingestão
- [x] `docker-compose.yml` (Postgres+pgvector, Redis, Minha Receita, Evolution API)
- [x] Pacote `src/` + `requirements.txt` + settings
- [x] Schemas Pydantic (`TenderSchema`, itens, riscos) e tabela `TenderIngest`
- [x] Client assíncrono PNCP (paginação, UF, modalidades)
- [x] Download/armazenamento em `data/raw/{id_licitacao}`
- [x] API FastAPI (`/health`, sync PNCP, download documentos)
- [x] Documentação inicial (técnica, usuário, fase, AGENTS)
- [ ] Validar `docker compose up` completo em máquina de desenvolvimento
- [ ] Validar sync PNCP real + persistência no Postgres
- [ ] Preparar deploy VPS (ver `docs/tecnica/DEPLOY_VPS.md`)

### Fase 2 — Parsing Docling e schemas
- [ ] Integrar Docling de ponta a ponta nos PDFs baixados
- [ ] Segmentação semântica (Objeto, Habilitação, QT, Julgamento, Contrato)
- [ ] Prompts + preenchimento estrito de `TenderSchema` com citação página/parágrafo

### Fase 3 — LangGraph + RAG jurídico
- [ ] Implementar nós do grafo (hoje esqueleto)
- [ ] Base vetorial pgvector (Lei 14.133 + TCU)
- [ ] Agentes extractor / legal / checklist sem alucinar exigências

### Fase 4 — Matchmaking Minha Receita
- [ ] ETL/carga da base CNPJ (ou apontar API já provisionada)
- [ ] Score CNAE + geo + porte (só ATIVAS)
- [ ] API de matches por edital

### Fase 5 — Peças e WhatsApp
- [ ] Gerador de minutas (proposta, esclarecimento, impugnação) + disclaimer OAB
- [ ] Evolution: instância, templates e envio de alertas

---

## Próxima ação recomendada

1. Publicar este repositório no GitHub (somente pastas do produto).  
2. Subir stack na VPS (`docs/tecnica/DEPLOY_VPS.md`).  
3. Rodar smoke test: `GET /health` + `POST /ingestion/pncp/sync` com janela de 1–2 dias e UF de teste.  
4. Iniciar Fase 2 (Docling) após ingestão estável.
