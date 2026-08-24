# AGENTS.md — contexto para IAs e desenvolvedores

## Workspace vs repositório GitHub

- **Workspace local** (`D:\Projetos\licitAll`) pode conter clones de referência na raiz. **Não** clone de novo nem altere o código-fonte deles.
- **Repositório GitHub** versiona **apenas** o produto LicitAll (`src/`, `docker/`, `docs/`, compose, requirements, regras Cursor).

Referências (só locais / Docker / PyPI):

| Pasta / serviço | Uso |
|-----------------|-----|
| Docling | OCR/parse → Markdown |
| LangGraph | Grafo de agentes |
| Minha Receita | CNPJ / CNAE / porte |
| Evolution API | WhatsApp |
| Querido Diário / RAGFlow / CrewAI examples | Padrões e crawlers |

## Código novo

Somente em `src/` (ou `app/`). Stack: Python 3.11+, FastAPI, Pydantic v2, SQLModel async, PostgreSQL 16 + pgvector, Redis.

## Fases (ordem obrigatória)

1. Fundação / PNCP / Docker  
2. Docling + schemas `TenderSchema`  
3. LangGraph + RAG Lei 14.133/TCU  
4. Matchmaking Minha Receita  
5. Peças + Evolution WhatsApp  

Estado oficial: `docs/fase/STATUS.md` (Fase 6 integração operacional).

## Compliance (não negociável)

- **Marco:** Lei Federal nº 14.133/2021. Não usar Lei 8.666 como base do motor.
- LC 123/2006 para ME/EPP (exclusividade / cota 25%).
- Nunca inventar certidões/prazos/empresas/vícios ausentes das fontes.
- Rodapé OAB (Lei 8.906/1994) em toda minuta (`DISCLAIMER_OAB`).
- Impugnação: 3 dias **úteis** antes da abertura (Art. 164).
- Detalhes: `docs/tecnica/COMPLIANCE_14133.md`.

## Documentação a manter atualizada

| Documento | Público | Quando atualizar |
|-----------|---------|------------------|
| `README.md` | Todos | Setup, status, links |
| `docs/fase/STATUS.md` | IA + devs | Toda mudança de fase |
| `docs/tecnica/*` | Devs | Arquitetura, API, fases, compliance |
| `docs/usuario/*` | Operadores | Fluxos de uso |
| `AGENTS.md` / `.cursor/rules/` | IA | Regras de implementação |

## Comandos rápidos

```bash
docker compose up -d
uvicorn src.main:app --reload --port 8000
pytest tests/ -q
```

Fluxo: sync → documents → parser → `rag/index` → extract/graph → matching → `advisory/kit` → WhatsApp preview/send.

Docs de fase: `FASE2_PARSING.md`, `FASE3_RAG.md`, `FASE4_MATCHING.md`, `FASE5_ADVISORY.md`.
