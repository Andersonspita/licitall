# Compliance — Lei 14.133/2021

Documento de referência rápida para IAs e desenvolvedores.

## Marco legal do LicitAll

| Norma | Papel no sistema |
|-------|------------------|
| **Lei 14.133/2021** | Lei geral de licitações e contratos (nova lei) — base de todas as análises |
| **LC 123/2006** | Tratamento diferenciado ME/EPP (Art. 48: exclusividade até R$ 80 mil; cota até 25%) |
| **Lei 8.906/1994** | Disclaimer: minutas de IA exigem revisão de advogado/responsável |
| Lei 8.666/1993 | **Não** é marco do motor; só citar se o próprio edital ainda referenciar |

## Art. 164 — Impugnação e esclarecimentos

- Prazo: até **3 dias úteis** antes da data de abertura do certame.
- Implementação: `prazo_impugnacao_art_164()` / `prazo_impugnacao_datetime()`.
- Conta feriados nacionais e fins de semana.
- Se o edital trouxer data explícita, ela prevalece (`limite_impugnacao_fonte=edital`).

## Habilitação (referência de classificação)

| Bloco | Artigo Lei 14.133 | Seção no parser |
|-------|-------------------|-----------------|
| Jurídica | Art. 66 | `habilitacao_juridica` |
| Técnica | Art. 67 | `qualificacao_tecnica` |
| Fiscal / trabalhista | Arts. 68–69 | `regularidade_fiscal` |
| Econômico-financeira | Art. 69 | `qualificacao_economico_financeira` |

## Anti-alucinação

- Nunca completar certidões “habituais” ausentes do edital.
- Todo fato sensível deve ter `pagina` / `paragrafo` quando o parser as obtiver.
- Campos faltantes vão em `missing_fields` / `avisos`, não em valores inventados.

## Triagem de risco (heurística atual)

Não substitui RAG/TCU (Fase 3), mas já aponta no texto:

- marca sem similar / direcionamento
- capital social mínimo percentual
- vistoria técnica obrigatória potencialmente restritiva
- prazo de impugnação a conferir vs Art. 164
