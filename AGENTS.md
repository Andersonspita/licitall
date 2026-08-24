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
| Querido Diário / RAGFlow / CrewAI examples | Padrões e crawlers (fases futuras) |

## Código novo

Somente em `src/` (ou `app/`). Stack: Python 3.11+, FastAPI, Pydantic v2, SQLModel async, PostgreSQL 16 + pgvector, Redis.

## Fases (ordem obrigatória)

1. Fundação / PNCP / Docker  
2. Docling + schemas `TenderSchema`  
3. LangGraph + RAG Lei 14.133/TCU  
4. Matchmaking Minha Receita  
5. Peças + Evolution WhatsApp  

Estado oficial: `docs/fase/STATUS.md`. Atualize esse arquivo e o README ao concluir ou iniciar uma fase.

## Compliance (não negociável)

- Lei 14.133/2021 e LC 123/2006  
- Nunca inventar certidões/prazos ausentes do edital; citar página/parágrafo  
- Rodapé OAB (Lei 8.906/1994) em toda minuta  
- Impugnação: até 3 dias **úteis** antes da abertura (Art. 164)

## Documentação a manter atualizada

| Documento | Público | Quando atualizar |
|-----------|---------|------------------|
| `README.md` | Todos | Setup, status, links |
| `docs/fase/STATUS.md` | IA + devs | Toda mudança de fase/tarefa |
| `docs/tecnica/*` | Devs | Arquitetura, API, deploy |
| `docs/usuario/*` | Operadores | Fluxos de uso |
| `AGENTS.md` / `.cursor/rules/` | IA | Regras de implementação |

## Comandos rápidos

```bash
docker compose up -d
uvicorn src.main:app --reload --port 8000
```

PNCP modalidades default: Pregão Eletrônico (6), Concorrência Eletrônica (4), Dispensa (8).
