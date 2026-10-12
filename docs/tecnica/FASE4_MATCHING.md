# Fase 4 — Matchmaking Minha Receita

## Objetivo

Conectar o edital estruturado (`TenderSchema`) a empresas **ATIVAS** compatíveis — e o caminho inverso (empresa → oportunidades) — com:

1. **Score explicável** (5 fatores) + recomendação **BID / REVIEW / SKIP**  
2. **Elegibilidade declarativa** (`eligibility_rules.yaml`) — hard fail vs soft warning  
3. **CNAE / geo / porte LC 123** + fit econômico + prazo (Art. 164)

Marco: Lei 14.133/2021 Art. 4º c/c LC 123/2006 Art. 48.

## Componentes

| Módulo | Função |
|--------|--------|
| `src/matching/cnae_map.py` | Heurística objeto → CNAEs |
| `src/matching/scoring.py` | Score 0–100 + breakdown + recomendação |
| `src/matching/eligibility.py` | Motor YAML (hard/soft) |
| `src/matching/eligibility_rules.yaml` | Regras Art. 164 / LC 123 / ATIVA / proximidade |
| `src/matching/service.py` | `match_tender` e `match_company` (inverso) |
| `src/matching/client.py` | API Minha Receita local |
| `matcher` no LangGraph | Preenche `matches` no grafo |

## Score (0–100)

| Fator | Máx. | Critério |
|-------|------|----------|
| CNAE | 35 | Sobreposição principal/secundários |
| Geografia | 20 | UF (+12) + município (+8) |
| Porte / LC 123 | 15 | Exclusividade ME/EPP ou base não exclusiva |
| Fit econômico | 15 | Valor × porte (faixa LC 123 R$ 80 mil) |
| Prazo / Art. 164 | 15 | Folga até abertura/encerramento |

**Recomendação:** BID ≥ 70 · REVIEW 40–69 · SKIP < 40 (ou hard-fail de elegibilidade).

**Ordem do match por empresa:** por tipo de ramo e depois pela nota: CNAE principal (35) → só secundário (28) ou significado (28) → desconhecido (teto 45) → incompatível. Cada oportunidade traz `ramo`.

**Ramo por significado** (`src/matching/ramo_semantico.py`): edital cujo ramo o mapa de palavras-chave não identifica tem o objeto comparado (embeddings, com cache) com a descrição de cada CNAE da empresa. Similaridade ≥ alto → compatível (+28); < baixo → incompatível (SKIP); entre os dois → ramo desconhecido (teto 45, revisar). Limiares por provedor em `LIMIARES_RAMO` (gemini 0,76/0,84, **provisórios**); sem chave de embedding ou sem limiar calibrado, nada muda e a resposta traz um aviso. Calibrar com `scripts/match_empresa_real.py --medir-ramo` e `--limiares`.

Ramo incompatível (CNAE conhecido no edital e na empresa, sem interseção): teto 35, ou seja SKIP. Sem isso, UF + porte + valor + prazo davam até 65 pts a um edital de outro ramo. Edital sem CNAE inferido continua com pontuação parcial (+12) e pode ir para REVIEW.

Demais em lote exclusivo: penalização forte (teto ~35) + hard-fail YAML.

## Elegibilidade (YAML)

| Regra | Severidade |
|-------|------------|
| `empresa_ativa` | hard |
| `lote_exclusivo_me_epp` | hard |
| `proximidade_obrigatoria` | hard |
| `prazo_propostas_aberto` | soft |
| `art_164_janela` | soft |
| `lead_minimo_dias` | soft |

## Endpoints

- `POST /matching/search` — edital → empresas  
- `POST /matching/{id_pncp}` — extrai edital + match  
- `POST /matching/company` — **inverso** CNPJ → oportunidades (`tenders` inline ou `tender_ingest`)  
- `POST /agents/{id}/graph` — inclui matches no nó final  

Body inverso:

```json
{
  "cnpj": "12345678000199",
  "tenders": null,
  "limit": 20,
  "min_score": 40,
  "require_proximity": false,
  "uf": null
}
```

Sem `tenders`, usa editais sincronizados em Postgres (`POST /ingestion/pncp/sync`): só os **ainda abertos** (situação de recebimento e encerramento das propostas no futuro, mesma regra da ingestão), os que encerram primeiro antes, até 5.000. As descrições de `itens_contratacao` entram na inferência de CNAE.

### Teste com uma empresa real

```bash
python -m scripts.match_empresa_real 12345678000199 --uf BA --json resultado.json
# sem a base local (ETL), usa a API pública, de mesmo formato:
python -m scripts.match_empresa_real 12345678000199 --uf BA --minha-receita https://minhareceita.org
```

Com `--sincronizar 7` (exige `--uf`) busca antes no PNCP os editais abertos publicados nos últimos 7 dias. Sem edital aberto no banco, diz quantos editais da UF existem e quantos estão abertos. Mostra a empresa, quantos editais tinham itens e CNAE inferido, a contagem BID/REVIEW/SKIP e o top N com os 5 fatores. Só grava com `--sincronizar`.

## Pré-requisito operacional

A imagem/serviço Minha Receita precisa ter a **base CNPJ carregada** (ETL). Sem dados, a API responde com aviso e lista vazia — o código não inventa empresas.

## Anti-alucinação

- Só empresas com situação ATIVA  
- Exclusividade ME/EPP só se o edital/benefícios indicarem  
- CNAEs inferidos são sugestão de busca, não afirmação jurídica  
- Score e elegibilidade são determinísticos (sem LLM no ranking)
