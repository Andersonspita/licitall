# Fase 2 — Parsing Docling e schemas (Lei 14.133/2021)

## Objetivo

Transformar PDFs de Edital/TR em Markdown segmentado e preencher `TenderSchema` **sem inventar** exigências, com citação de página/parágrafo e prazos do **Art. 164** em dias úteis.

## Componentes

| Módulo | Função |
|--------|--------|
| `src/compliance/lei_14133.py` | Art. 164 (3 dúteis), LC 123 (R$ 80 mil / cota 25%), feriados |
| `src/parser/sections.py` | Seções alinhadas aos Arts. 66–69, 33–39, 164 |
| `src/parser/docling_parser.py` | Docling + fallback pypdfium2 + refs |
| `src/parser/service.py` | Parse de arquivos em `data/raw/{id}` |
| `src/agents/extractor.py` | Merge PNCP + texto → `TenderExtractionResult` |
| `src/agents/checklist.py` | Só documentos **citados** no edital |
| `src/agents/legal_rag.py` | Triagem determinística (pré-RAG) |
| `src/agents/pipeline.py` | Orquestra parse → extract → checklist → riscos |
| `src/agents/prompts.py` | Prompts anti-alucinação (LLM opcional) |

## Endpoints

- `POST /parser/{id_pncp}` — gera Markdown/`_parsed`
- `POST /agents/{id_pncp}/extract` — `TenderSchema` + checklist + riscos
- `GET /health` — inclui `docling_available` e `marco_legal`

## Regras de compliance

1. Marco: **Lei 14.133/2021** (não usar 8.666 como base).
2. Impugnação/esclarecimento: se o edital não fixar data, calcular **3 dias úteis antes** da abertura (`limite_impugnacao_fonte=calculado_art_164`).
3. Checklist: zero documentos “padrão” não escritos no edital.
4. ME/EPP: exclusividade/cota só se o texto indicar (LC 123/2006).

## Fluxo sugerido

1. `POST /ingestion/pncp/sync`
2. `POST /ingestion/pncp/{id}/documents`
3. `POST /parser/{id}`
4. `POST /agents/{id}/extract`
