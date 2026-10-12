# API — Fase 1

Base local: `http://localhost:8000`  
OpenAPI: `/docs`

## Autenticação e permissões

Toda rota exige login, **exceto**: `/` e `/app` (redirecionam), `/health` (só `status` e `versão`), `/ui/*` (arquivos estáticos) e `/auth/login|register|logout|config`. Rota nova nasce protegida (`src/auth/security.py::required_role`).

- `POST /auth/register` `{empresa_nome, nome, email, senha}` → cria a empresa e o primeiro usuário e já abre a sessão (desligue com `AUTH_REGISTRATION_OPEN=false`; então use `python -m scripts.criar_usuario`). Senha: 8 a 128 caracteres.
- `POST /auth/login` `{email, senha}` → cookie **HttpOnly, SameSite=Lax** (`Secure` com `COOKIE_SECURE=true`); resposta 401 idêntica para e-mail inexistente e senha errada; **bloqueio de 15 min após 5 falhas** por e-mail+IP (429 com `Retry-After`; em memória, vale por processo).
- `POST /auth/logout` encerra a sessão no servidor · `GET /auth/me` · `GET /auth/config` (`registro_aberto`).
- Sessões ficam no banco só como SHA-256 do token; senhas com scrypt (N=2^15). Também aceita `Authorization: Bearer <token>`.
- **Isolamento por empresa:** perfis, oportunidades, digests, agendamentos e feedback pertencem à empresa do usuário; acesso a recurso de outra empresa responde **404**. O `empresa_id` enviado pelo cliente é ignorado.
- **Operador** (e-mail em `ADMIN_EMAILS`): `/ingestion/*`, `/pipeline/*`, `/parser/*`, `/outreach/*`, `/rag/index/*`, `/agents/*/graph`, `/matching/reverse/*`, `/matching/digest/run-due`, `/health/deps`, `/health/detail`. Cliente comum recebe 403.
- Pedidos que alteram dados com `Origin` de outro site recebem 403 (defesa extra contra CSRF). `/docs` e `/openapi.json` só com `DEBUG=true`.
- **Limites conhecidos:** sem recuperação de senha por e-mail, sem confirmação de e-mail, sem 2FA, bloqueio de login por processo (não compartilhado entre instâncias), sem limite de uso nas rotas que chamam IA. Exige HTTPS e `COOKIE_SECURE=true` em produção.

## UI web

Base: `http://localhost:8000/ui/` · Login: `/ui/login.html` · Dashboard: `/ui/dashboard.html`  
Doc: [INTERFACE_WEB.md](../usuario/INTERFACE_WEB.md)

## `GET /tenders`

Lista editais reais de `tender_ingest`.

Query: `uf`, `status`, `q` (busca textual), `limit` (máx. 200), `offset`.

Resposta: `{ total, limit, offset, items[] }` — cada item inclui `art164` (prazo calculado Art. 164).

## `GET /tenders/stats`

KPIs: `total`, `valor_total_estimado_sum`, `by_status`, `by_uf`, `prazos_criticos` (≤ 3 dias úteis).

## `GET /tenders/{id_pncp}`

Detalhe + `filesystem` (docs/parsed/kit em `data/raw`).

## `GET /health`

Retorna status, versão e paths/URLs configurados.

## `POST /ingestion/pncp/sync/async`

Sync **assíncrono**. Padrão **`uf=BR`** (Brasil): percorre as 27 UFs uma a uma (a API nacional sem UF estoura timeout).  
**Commit a cada página** → `GET /tenders` já lista editais enquanto o job roda.

```json
{ "uf": "BR", "only_open": true }
```

Ou uma UF: `{ "uf": "SP" }`. Janela máx. 7 dias.

## `GET /ingestion/pncp/sync/jobs/{job_id}`

Status do job: `queued | running | succeeded | partial | failed`, `ingested`, `pages_done`, `log[]`.

UI (dashboard/monitor) usa este fluxo com polling.

## `POST /ingestion/pncp/sync`

Sincroniza publicações do PNCP e faz upsert em `tender_ingest` (**síncrono / legado**).  
**UF obrigatória.** Prefira `/sync/async`.

Body (JSON), todos opcionais:

```json
{
  "data_inicial": "2026-08-23",
  "data_final": "2026-08-24",
  "uf": "SP",
  "only_open": true,
  "modalidades": ["PREGAO_ELETRONICO", "CONCORRENCIA", "DISPENSA_ELETRONICA"]
}
```

Sem datas: usa ontem → hoje. Exige Postgres disponível.

## `POST /ingestion/pncp/{id_pncp}/documents`

Baixa anexos (Edital/TR) para `data/raw/{slug}/`.  
`id_pncp` no formato `CNPJ-1-SEQUENCIAL/ANO` (ex.: `00394452000103-1-000033/2024`).

## `GET /ingestion/pncp/{id_pncp}/itens`

Lista itens da contratação na API core do PNCP.

## `POST /ingestion/pncp/{id_pncp}/itens/hydrate`

Busca os itens no PNCP e grava em `itens_contratacao` (UPSERT por `id_pncp` + `numero_item`; republicações atualizam sem duplicar). Retorna `{ "itens_gravados": N }`.

## `POST /ingestion/pncp/{id_pncp}/anexos/hydrate` · `GET /ingestion/pncp/{id_pncp}/anexos`

O `POST` busca no PNCP os arquivos do edital (edital, termo de referência, minuta) e grava **só título, tipo e URL** em `anexos_contratacao` (UPSERT por edital + URL; arquivos sem URL são ignorados; o binário não vai para o banco). O `GET` lista o que já foi gravado, sem consultar o PNCP. A busca reversa hidrata os anexos automaticamente dos editais que renderam ao menos uma oportunidade; falha ali não perde os matches. `GET /matching/profiles/{id}/oportunidades` devolve `edital.anexos[]`, e a tela de perfis mostra os links (só `https://`).

**Regra de "somente abertos" (`only_open`)**: o edital precisa estar numa situação de recebimento ("Divulgada", "Publicado", "Recebendo proposta") **e** ter `dataEncerramentoProposta` no futuro (horário de Brasília). Edital sem data de encerramento informada é aceito. A regra vale na ingestão; editais que vencem depois continuam gravados.

## `GET /ingestion/modalidades`

Lista modalidades filtradas por padrão na ingestão.

## `POST /parser/{id_pncp}`

Converte anexos em `data/raw/{id}` para Markdown segmentado (Docling ou fallback).  
Persiste metadados em `data/raw/{id}/_parsed/`.

## `POST /agents/{id_pncp}/extract`

Pipeline: parse + `TenderSchema` + checklist + triagem Lei 14.133 com RAG.

## `POST /agents/{id_pncp}/graph`

LangGraph: ingestion → parser → extractor → legal_analyzer → matcher (score explicável + elegibilidade).

## `POST /rag/index/lei-14133`

Indexa corpus `data/legal/` (Lei 14.133 + seed TCU).

## `GET /rag/search?q=...&top_k=5`

Busca no índice jurídico.

## Perfis de interesse e filtros rígidos (matching por item, etapa 1)

`POST /matching/profiles` cria um perfil: `empresa_id`, `nome_perfil`, `ufs_permitidas` (vazio = Brasil inteiro), `valor_minimo_item`, `valor_maximo_item`, `apenas_me_epp`, `palavras_obrigatorias|positivas|negativas`, `codigos_catalogo` (CATMAT/CATSER).  
`GET /matching/profiles?empresa_id=...` lista · `DELETE /matching/profiles/{id}` remove (204).  
`POST /matching/profiles/{id}/filter` com `{ "id_pncp": "..." }` aplica a Camada 1 aos itens gravados e devolve `aprovados` e `descartados` (com `motivos`). 404 se perfil/contratação não existe; 409 se a contratação ainda não tem itens (chame `/itens/hydrate`).

Regras: UF fora do perfil; valor unitário (ou total) fora da faixa; `apenas_me_epp` exige item exclusivo ME/EPP; termo negativo na descrição ou no objeto (palavra inteira, sem acento/caixa, plural simples). Valor desconhecido não elimina. Código: `src/matching/hard_filters.py`, `profiles.py`. Palavras obrigatórias/positivas e CATMAT são armazenadas, mas só pontuam nas Camadas 2–3 (ainda não implementadas).

`POST /matching/profiles/{id}/candidates` com `{ "id_pncp": "..." }` roda Camada 1 + **Camada 2** e devolve `candidatos` ordenados por `score_parcial` (máx. 75 de 100; os 25 restantes virão da Camada 3), mais contagens de descartados.  
Camada 2 (`src/matching/lexical.py`): **CATMAT/CATSER** idêntico = 40 pts × peso da regra; **léxico** = até 35 pts; as palavras do perfil são **alternativas**: a 1ª encontrada vale 60%, cada outra +20% (3 = 100%; perfil de 1 palavra encontrada = 100%) (`credito_lexico`), considerando obrigatórios + positivos (plural simples, stopwords licitatórias como SRP/ata/pregão/edital, tolerância a erro de digitação por similaridade de trigramas no estilo pg_trgm, também em palavras coladas/separadas). Palavra **obrigatória** ausente tira o item da lista. Não implementado: 20 pts por "mesmo grupo/classe" do catálogo (o projeto não tem a hierarquia CATMAT/CATSER) e índices GIN `tsvector`/`pg_trgm` no banco (a versão atual roda em Python sobre os itens aprovados na Camada 1).

`POST /matching/profiles/{id}/match` com `{ "id_pncp": "..." }` roda o **funil completo** (Camadas 1–3) e devolve `candidatos` com `score_catmat` (0–40), `score_lexico` (0–35), `score_semantico` (0–25), `score_total` (0–100) e `alerta` (verdadeiro a partir de 65). **Sem CATMAT comparável** (perfil sem códigos ou item sem código no PNCP) a camada de catálogo não conta: `score_total = (léxico + semântico) ÷ 60 × 100`; por isso, nesse caso, o total não é a soma das três notas parciais. Com código diferente do perfil o item continua perdendo os 40 pontos. O criar-perfil aceita `descricao_sintetica` (texto livre que vira o vetor do perfil; sem ele usa nome + termos).  
Camada 3 (`src/matching/semantic.py`): texto do item sanitizado (remove `ITEM n`, `CONFORME…`, `PROCESSO…`, limite 500 caracteres) → SHA-256 → cache `embeddings_cache` (chave: hash + backend). Textos já vistos nunca vão ao provedor; os inéditos seguem em lotes de 100. Embedding só para itens aprovados na Camada 1. Provedor: OpenAI `text-embedding-3-small` em **512 dimensões** quando há `OPENAI_API_KEY`; **sem chave, cai num vetor lexical determinístico** (`backend: "hash:512"`), que mede sobreposição de palavras, não semântica real — a resposta informa o backend usado. O vetor do item usa só a descrição (sem o objeto) para o cache valer entre órgãos. Vetores ficam em JSONB e o cosseno é calculado em Python (sem índice HNSW/pgvector ainda). Não implementado: Dead Letter Queue para itens que falham repetidamente, worker com buffer por tempo (2 s) e tabela `matches_itens` de resultados.

### Oportunidades do perfil

`GET /matching/profiles/{id}/oportunidades` lista os matches gravados pela busca reversa, **da maior para a menor nota** (desempate: mais recente). Parâmetros: `pagina` (1), `tamanho` (20, máx. 100), `status` (`NOVO`/`ENVIADO`/`DESCARTADO`/`FAVORITO`; outro valor → 422), `apenas_alerta` (nota ≥ 65), `desde` (data), `uf`. Resposta: `total`, `pagina`, `paginas` e `itens[]` com `edital` (órgão, UF, objeto, encerramento), `item` (descrição, quantidade, valor unitário, CATMAT), as três notas parciais, `score_total`, `alerta` e `status`. Perfil inexistente → 404. Usado pela tela de perfis ("Ver oportunidades").

### Envio agendado do digest

`PUT /matching/profiles/{id}/agendamento` (`{ "telefone": "5571999999999", "horario": "08:00", "top_n": 5, "ativo": true }`) agenda **um envio diário** por WhatsApp (Evolution), no horário de Brasília. `GET` consulta (próxima execução, último resultado) e `DELETE` remove. `POST /matching/digest/run-due` executa na hora o que estiver vencido.  
**Como roda:** um laço em segundo plano na própria API (`src/matching/scheduler.py`, iniciado no `lifespan`) verifica a cada 60 s (`DIGEST_SCHEDULER_INTERVAL_SECONDS`; desligue com `DIGEST_SCHEDULER_ENABLED=false`). Regras: só envia se houver matches `NOVO` com alerta (senão registra "sem novidades" e **não** manda mensagem); no máximo um envio por dia; falha de envio mantém os matches como `NOVO` e tenta de novo após 15 min (`DIGEST_RETRY_MINUTES`); cada agendamento é reivindicado por `UPDATE` atômico, então dois processos da API não enviam em duplicidade; ao criar ou mudar o horário depois de ele já ter passado hoje, o primeiro envio é amanhã. Fuso fixo UTC−3 (sem horário de verão). Se a API estiver parada no horário, o envio sai assim que ela voltar (no mesmo dia). Telefone: 10 a 15 dígitos com DDI (símbolos são removidos). Excluir o perfil remove o agendamento.

### Feedback do cliente (relevante / irrelevante)

`POST /matching/matches/{match_id}/feedback` com `{ "relevante": true|false }`: relevante → status `FAVORITO`; irrelevante → `DESCARTADO` e a resposta traz `sugestoes_negativas` (até 5 palavras da descrição do item que o cliente pode bloquear). A sugestão ignora palavras que o perfil já usa (interesse, obrigatórias, negativas, por raiz), palavras presentes em itens que o cliente já marcou como relevantes, números/códigos, palavras curtas e stopwords. Match inexistente → 404.  
`POST /matching/profiles/{id}/palavras` com `{ "tipo": "NEGATIVA", "termo": "locação" }` acrescenta a palavra ao perfil (tipo padrão `NEGATIVA`; repetida, sem distinguir acento/caixa, devolve `adicionada: false`; tipo inválido → 422). Vale para as próximas avaliações: oportunidades já gravadas **não** são removidas retroativamente. Código: `src/matching/feedback.py`. Na tela de perfis, "Ver oportunidades" tem os botões Relevante/Irrelevante e as sugestões clicáveis.

### Busca reversa e digest por edital

`POST /matching/reverse/run` (`{ "id_pncps": [...] }` ou, vazio, os editais ingeridos nas últimas `since_hours`, padrão 24) avalia cada edital contra **todos os perfis ativos** e grava em `matches_itens` (itens com score ≥ 40; `alerta` a partir de 65). Só avalia editais cuja UF algum perfil aceita (perfil sem UFs aceita o Brasil), hidrata os itens do PNCP se faltarem e respeita o teto `REVERSE_MATCH_MAX_TENDERS` (200). Reprocessar atualiza as notas e **não desfaz** `ENVIADO/DESCARTADO/FAVORITO`.  
**Automático:** ao concluir um sync (`/ingestion/pncp/sync/async`, status `succeeded` ou `partial`), os editais ingeridos passam pela busca reversa (`REVERSE_MATCH_ENABLED`, padrão ligado; sem perfis ativos não faz nada). Falha na busca reversa vai para o log do job e nunca derruba o sync.  
`GET /matching/profiles/{id}/digest` → matches `NOVO` com alerta agrupados por edital + mensagem pronta ("Prefeitura X (BA) — 23 itens compatíveis"). `POST /matching/profiles/{id}/digest/send` (`{ "phone": "55…" }`) envia pelo Evolution e só depois marca como `ENVIADO` (falha de envio → 502 e nada é marcado).  
Não implementado: agendamento por dias da semana ou várias vezes ao dia.

## Certidões e atestados (por empresa, exige login)

| Método e rota | Função |
|---------------|--------|
| `GET /certidoes?aviso_dias=1..90` | Lista (cria a lista oficial se faltar) com `situacao` e `dias` + `resumo` |
| `GET /certidoes/resumo` | Contagens e até 5 itens que pedem atenção |
| `POST /certidoes` `{nome}` | Documento próprio (409 se repetido ou no limite de 200) |
| `PUT /certidoes/{id}` `{validade, observacao}` | Atualiza a validade (422 fora do intervalo plausível) |
| `DELETE /certidoes/{id}` | Remove documento próprio (409 para os da lista oficial) |
| `GET /atestados?q=` | Lista e filtra por objeto/contratante |
| `POST /atestados` · `PUT /atestados/{id}` · `DELETE /atestados/{id}` | CRUD (limite de 2000); recurso de outra empresa responde 404 |

## `POST /matching/search`

Body: `{ "tender": { ...TenderSchema-like }, "limit": 30, "min_score": 40, "require_proximity": false }`.  
Retorna empresas ATIVAS ranqueadas com score explicável, `recommendation` (BID/REVIEW/SKIP) e elegibilidade YAML.

## `POST /matching/company`

Match inverso CNPJ → oportunidades. Body: `{ "cnpj", "tenders"?, "limit", "min_score", "require_proximity", "uf" }`.  
Sem `tenders`, lê os editais **ainda abertos** de `tender_ingest` (Postgres), com os itens do banco na inferência de CNAE. Ver [FASE4_MATCHING.md](FASE4_MATCHING.md).

## `POST /matching/{id_pncp}`

Extrai o edital e executa o matchmaking (CNAE + geo + porte / LC 123 + prazo/Art. 164).

## `POST /advisory/generate`

Gera kit de minutas a partir de `tender` (+ `company` opcional). Inclui disclaimer Lei 8.906/1994.

## `POST /advisory/{id_pncp}/kit`

Extrai o edital e gera/persiste o kit em `data/raw/.../_kit/`.

## `POST /outreach/whatsapp/preview`

Monta mensagem de oportunidade sem enviar.

## `POST /outreach/whatsapp/opportunity`

Envia via Evolution API (`EVOLUTION_API_URL` / `EVOLUTION_API_KEY` / `EVOLUTION_INSTANCE`).

## `POST /outreach/whatsapp/digest/preview` · `POST /outreach/whatsapp/digest`

Digest top-N oportunidades (score + BID/REVIEW/SKIP).

## `POST /outreach/whatsapp/digest/from-company`

Match inverso + digest (`send: false` = só preview).

