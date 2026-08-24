# Fase 4 — Matchmaking Minha Receita

## Objetivo

Conectar o edital estruturado (`TenderSchema`) a empresas **ATIVAS** compatíveis por:

1. **CNAE** (principal/secundário) — informados ou inferidos do objeto/itens  
2. **Geografia** — UF e município do órgão executor  
3. **Porte** — ME/EPP vs Demais, conforme LC 123/2006 e exclusividade do edital  

Marco: Lei 14.133/2021 Art. 4º c/c LC 123/2006 Art. 48.

## Componentes

| Módulo | Função |
|--------|--------|
| `src/matching/cnae_map.py` | Heurística objeto → CNAEs |
| `src/matching/scoring.py` | Score 0–100 |
| `src/matching/service.py` | Orquestra busca + ranking |
| `src/matching/client.py` | API Minha Receita local |
| `matcher` no LangGraph | Preenche `matches` no grafo |

## Score

| Critério | Pontos |
|----------|--------|
| CNAE em comum | 60 |
| Mesma UF | 15 |
| Mesmo município | +10 |
| Porte OK (não exclusivo) | 10 |
| ME/EPP em lote exclusivo | 15 |
| Demais em lote exclusivo | penalização forte |

## Endpoints

- `POST /matching/search` — body `{ "tender": {...}, "limit", "min_score", "require_proximity" }`
- `POST /matching/{id_pncp}` — extrai o edital e busca matches
- `POST /agents/{id}/graph` — inclui matches no nó final

## Pré-requisito operacional

A imagem/serviço Minha Receita precisa ter a **base CNPJ carregada** (ETL). Sem dados, a API responde com aviso e lista vazia — o código não inventa empresas.

## Anti-alucinação

- Só empresas com situação ATIVA  
- Exclusividade ME/EPP só se o edital/benefícios indicarem  
- CNAEs inferidos são sugestão de busca, não afirmação jurídica
