# Status de desenvolvimento — LicitAll

> Fonte de verdade da fase atual para IAs e desenvolvedores. Atualizar a cada entrega significativa.

**Última atualização:** 2026-09-21  
**Fase atual:** 6 — integração operacional (pipeline + health deps + smoke Compose)  
**Repositório:** https://github.com/Andersonspita/licitall  
**Marco legal:** Lei Federal nº 14.133/2021 + LC 123/2006 + disclaimer Lei 8.906/1994

---

## Checklist de fases

### Fase 1 — Fundação e ingestão
- [x] Docker, `src/`, PNCP client, API, docs, GitHub
- [x] Smoke PNCP online (`scripts/smoke_local.py`)
- [x] Smoke Compose parcial — Postgres/Redis/Evolution API (portas 5433/6380/8081)
- [x] Publicação em servidor preparada e testada localmente (Dockerfile da API, proxy HTTPS, migrações, backup) — falta executar num servidor real com domínio

### Fase 2 — Parsing Docling e schemas
- [x] Compliance Art. 164 + LC 123, Docling/fallback, extractor, testes, docs
- [x] Smoke parse em PDF real PNCP

### Fase 3 — LangGraph + RAG jurídico
- [x] Corpus Lei 14.133, RAG, grafo, endpoints, docs
- [ ] Expandir corpus / checkpoint Postgres em produção

### Fase 4 — Matchmaking Minha Receita
- [x] Score CNAE/geo/porte, API, LangGraph matcher, docs/testes
- [x] Score explicável 5 fatores + BID/REVIEW/SKIP
- [x] Elegibilidade declarativa YAML (Art. 164 / LC 123 / ATIVA)
- [x] Match inverso `POST /matching/company` (CNPJ → oportunidades)
- [ ] Validar contra base Minha Receita populada (ETL)

### Fase 5 — Peças e WhatsApp
- [x] Kit de minutas + disclaimer OAB + Evolution preview/send APIs
- [x] Digest WhatsApp top-N (`/outreach/whatsapp/digest` + `from-company`)
- [ ] Envio real WhatsApp (Evolution + QR)

### Fase 6 — Integração operacional
- [x] `GET /health/deps` — Postgres, Redis, Minha Receita, Evolution
- [x] `POST /pipeline/{id_pncp}/run` — download → extract → match → kit → preview
- [x] `scripts/smoke_compose.py` + `docs/usuario/OPERACAO_DOCKER.md`
- [x] Testes `tests/test_fase6_pipeline.py`
- [x] Smoke Compose parcial (2026-08-24) — Postgres/Redis/Evolution API OK; Minha Receita off; pipeline 200
- [x] UI web `/ui` — login + dashboard + explorador + peças + matchmaking + WhatsApp (2026-09-21)
- [x] `GET /tenders` + `/tenders/stats` + `/tenders/{id}` — UI sem mocks; PDF guia usuário
- [x] Sync PNCP async — `POST /ingestion/pncp/sync/async` + jobs (retry por página, progresso)
- [x] Sync Brasil (`uf=BR`) — varre 27 UFs; commit por página → `GET /tenders` lista ao vivo

---

## Smoke Compose (2026-08-24)

| Check | Resultado |
|-------|-----------|
| Postgres :5433 | OK |
| Redis :6380 | OK |
| Evolution API :8081 | OK |
| Evolution Manager :3001 | Falha nginx na imagem |
| Minha Receita :8001 | Off (atcr.io 401) |
| `POST /pipeline/{id}/run` | OK — 4 minutas + Art. 164 |
| PNCP sync Postgres | 429 rate limit (retentar) |

Portas alternativas evitam conflito com containers `barbershop-*` em 5432/6379/8080.

---

## Entrega 2026-09-21 — matching + digest

Inspirado em cases (BidPilot / Bandifinder / Licinexus), **sem** robô de lances, chat de pregão ou CRM:

1. Score explicável (CNAE 35 + geo 20 + porte 15 + econômico 15 + prazo 15)  
2. `src/matching/eligibility_rules.yaml` + motor hard/soft  
3. Match inverso empresa → editais  
4. Digest WhatsApp top-N  

Docs: `FASE4_MATCHING.md`, `FASE5_ADVISORY.md`, `API.md`.

## Entrega 2026-09-21 — UI web

Front estático em `app/web/` servido em `/ui` (login + dashboard + explorador + peças + matchmaking + WhatsApp).  
Listagem e KPIs usam **dados reais** (`GET /tenders*`). Guia PDF: `docs/usuario/LicitAll_Guia_Usuario.pdf`.
Doc: `docs/usuario/INTERFACE_WEB.md`. Login real com conta por empresa (ver "Autenticação real" abaixo).

## Entrega 2026-10-11 — matching por item, etapa 1

Tabelas `itens_contratacao`, `perfis_interesse`, `regras_palavras_chave`, `regras_catalogo`; hidratação de itens do PNCP; Camada 1 (filtros rígidos) com endpoints de perfil. Testes: `tests/test_etapa1_hard_filters.py`. **Camada 2** (CATMAT + léxico, `src/matching/lexical.py`, `tests/test_etapa2_lexical.py`) entregue em Python puro; endpoint `/matching/profiles/{id}/candidates`. **Camada 3** (embeddings com cache por hash, `src/matching/semantic.py`, endpoint `/matching/profiles/{id}/match`, score 0–100 com alerta ≥ 65) entregue; sem `OPENAI_API_KEY` usa vetor lexical (não semântico). **Validado contra Postgres 16 real (2026-10-11)**: hidratação idempotente (2× → 5 linhas), perfil, filtro, candidatos e funil completo via API, cache reaproveitado na 2ª chamada (5 textos → 0). Achou e corrigiu 1 bug (`created_at` no INSERT do cache). **Pendente:** hierarquia CATMAT (grupo/classe), índices FTS/trigramas/HNSW no banco, DLQ.  
**Busca reversa + digest por edital** entregues e validados no Postgres real (`src/matching/reverse.py`, `digest.py`, tabela `matches_itens`; hook no fim do sync em `ingestion/jobs.py` — esse hook ainda não foi exercitado com o PNCP real). Envio WhatsApp real não testado (Evolution desligado: caminho de falha validado, 502 sem marcar enviado). Endpoint `GET /matching/profiles/{id}/oportunidades` (paginado, filtros, ordenado por nota) validado no Postgres real e ligado à tela ("Ver oportunidades"). Tela de perfis (`app/web/perfis.html`) entregue e testada no navegador contra API+Postgres reais. Feedback relevante/irrelevante com sugestão de termos negativos entregue e validado (API + tela). Envio agendado do digest (`src/matching/scheduler.py`, tabela `digest_agendamentos`) entregue e validado no Postgres real com remetente simulado; **envio real via Evolution ainda não testado**. Anexos do edital (`anexos_contratacao`, `/ingestion/pncp/{id}/anexos*`, links na tela de oportunidades) e seed `scripts/seed_perfis_exemplo.py` entregues e validados no Postgres real; corrigido bug de objetos expirados após rollback na busca reversa. Falta: multiempresa/autenticação real (hoje `empresa_id` = e-mail da sessão).  
Também: UI com menu por etapas e telas Certidões, Atestados e Simulador (Certidões e Atestados agora no banco; ver seção abaixo).

## Validação com o PNCP real (2026-10-11)

Sync real do projeto (DF, pregão eletrônico, 09/10/2026): **33 editais**, UPSERT idempotente (2 rodadas → 33 linhas). Os 12 campos que `map_pncp_item` lê (órgão, CNPJ, UF, município, modalidade, objeto, valor, situação e 3 datas) vieram **100% preenchidos**; "Divulgada no PNCP" é reconhecida como aberta. **Não validado:** itens e arquivos — os endpoints do núcleo estavam fora do ar nesse momento (`/api/pncp/v1/...` sem resposta; `/pncp-api/v1/...` com 503 "no server available"). Portanto continuam **suposições não confirmadas**: o caminho correto do núcleo, o campo do código CATMAT/CATSER (`codigoItem`/`codigoItemCatalogo`/…) e o do tipo do documento (`tipoDocumentoNome`). Repetir a sonda quando o núcleo voltar. Achado e **corrigido**: 1 dos 33 editais "Divulgada" tinha prazo de propostas vencido (2025-04-15, dado da fonte); `is_open_for_proposals` agora exige situação de recebimento **e** `dataEncerramentoProposta` no futuro (horário de Brasília; sem data informada, aceita). Reconferido com o PNCP real: 32 de 33 ingeridos. Editais que vencem *depois* de ingeridos continuam no banco (a regra vale só na entrada).

## Auditoria de interface com navegador real (2026-10-12)

Varredura de 17 telas em desktop (1440 px) e celular (390 px) com Playwright CLI + regras da skill `web-design-guidelines`. **Corrigido:** (1) `GET /tenders/{id}` retornava 503 para qualquer edital (`DocumentStorage` recebia um `Path`; o `except` genérico escondia o erro como "Postgres indisponível") — agora 200, com teste de regressão; (2) menu lateral fixo de 288 px tornava as telas ilegíveis no celular — virou gaveta abaixo de 1024 px (botão, Esc, clique fora); estouro horizontal caiu de 16 telas para 0; (3) 60 campos sem nome acessível → 0; (4) foco visível global, `prefers-reduced-motion`, `tabular-nums`, `transition-all` removido; (5) números inventados no painel (capacidade 68%, "3 PDFs", "fila de 2") e ponto vermelho fixo no sino removidos. **Em aberto (decisão de produto):** painel ainda técnico demais para cliente (Pipeline LangGraph/Docling, saúde de Redis/Receita/Evolution), credenciais de demonstração visíveis na tela de login, ~20 `alert()/confirm()` nativos, alvos de toque < 32 px em tabelas, sem `theme-color`, `GET /tenders/{id}` cria pastas vazias em `data/raw`.

## Painel do cliente e login sem credenciais (2026-10-12)

`dashboard.html` reescrito para o cliente: oportunidades novas (dos perfis), editais abertos, encerram em 7 dias, certidões a vencer, melhores oportunidades, editais que encerram primeiro e atalhos. Saíram do painel (continuam no menu Administração): pipeline LangGraph/Docling, saúde de serviços e feed de WhatsApp. Login: removidas as credenciais de demonstração (campos vazios, sem caixa "Demo", sem senha na mensagem de erro); a autenticação segue de **protótipo** (aceita qualquer e-mail válido + senha de 6+ caracteres, sem verificação). `seed_perfis_exemplo --empresa` agora é obrigatório. **Art. 164 corrigido (autorizado pelo usuário em 2026-10-12):** o prazo de impugnação era contado a partir de `data_abertura_propostas`, que no PNCP é o *início* do recebimento, e marcava como "vencido" editais com prazo real à frente (tela Editais, nota de prazo do matching). Agora `data_abertura_certame()` (`src/compliance/lei_14133.py`) usa: data do certame explícita > **encerramento das propostas** > início do recebimento (último recurso, antecipa o prazo). Aplicado em `tenders/service.py`, `matching/scoring.py` e `matching/eligibility.py`. Limite: o PNCP não informa a data da sessão pública; confirme com o advogado se a disputa de fato abre no encerramento das propostas para os seus editais (plataformas podem abrir em outro horário).

## Autenticação real e isolamento por empresa (2026-10-12)

Tabelas `empresas`, `usuarios`, `sessoes`; login/cadastro/logout/me (`src/auth/`); cookie HttpOnly+SameSite; senha scrypt; bloqueio após 5 falhas; guarda global (rota nova nasce fechada); operador via `ADMIN_EMAILS`; perfis/oportunidades/digests/agendamentos/feedback isolados por empresa (404 em recurso alheio); `empresa_id` do cliente ignorado; defesa de `Origin` contra CSRF; `/health` enxuto; docs da API só com `DEBUG=true`. UI: `cadastro.html`, login assíncrono, menu de operador oculto para clientes, aviso de acesso restrito. Testes: `tests/test_auth_security.py` (11) e `tests/test_auth_integration.py` (8, contra Postgres real; pulam sem banco). Verificado no navegador real (cliente A × B × operador). **Pendência de modelagem:** `perfis_interesse.empresa_id` é texto sem chave estrangeira para `empresas` (excluir uma empresa deixa perfis órfãos); corrigir junto com as migrações (Alembic). **Pendente para produção:** HTTPS (`COOKIE_SECURE=true`), recuperação de senha e confirmação de e-mail, limite de uso nas rotas com IA, bloqueio de login compartilhado entre instâncias (Redis), política de privacidade/LGPD. Scripts de smoke agora usam `SMOKE_EMAIL`/`SMOKE_PASSWORD`.

## Publicação e migrações (2026-10-12)

**Migrações (Alembic):** `alembic.ini`, `migrations/`, baseline `0001` (14 tabelas + extensão `vector`). `python -m src.db.migrate` aplica e **adota bancos criados antes do Alembic** (carimba a base e confere o esquema; em produção aborta se divergir). `AUTO_CREATE_TABLES=false` em produção. **Container:** `Dockerfile` (Python 3.12, usuário sem privilégios, Docling opcional via `INSTALL_DOCLING`), `docker/api-entrypoint.sh` (verifica configuração → migra → sobe), serviços `api` e `proxy` (Caddy, HTTPS automático) no perfil `app` do compose; `docker/backup.sh`. **Segurança:** portas internas (Postgres, Redis, Evolution, Minha Receita) agora só em `127.0.0.1` (antes em todas as interfaces, inclusive Redis sem senha); com `APP_ENV=production` a API **recusa subir** com senha do banco/chave do Evolution fracas, `COOKIE_SECURE` falso, `DEBUG` ligado ou sem `ADMIN_EMAILS` (`src/config/production.py`). **Testado:** migração em banco vazio e idempotente; adoção de cópia do banco real (32 editais preservados, sem divergência); recusa com config padrão; subida com segredos fortes pelo compose; HTTPS com HSTS e cookie `Secure`; HTTP→HTTPS; operador × cliente (200 × 403); isolamento (404); reinício mantém sessão e dados; API não acessível direto (8000). **Falta:** rodar num servidor real (DNS, certificado Let's Encrypt de verdade, firewall); fixar versões das imagens `evolution-api` e `minha-receita` (hoje `latest`); `perfis_interesse.empresa_id` ainda sem chave estrangeira (próxima migração `0002`); CI; monitoramento; recuperação de senha.

## Certidões e atestados no banco (2026-10-12)

Tabelas `certidoes` e `atestados` (migração `0002`), por empresa: todos os usuários da empresa veem os mesmos dados; outra empresa recebe 404. A lista oficial de 7 certidões é criada sob demanda (idempotente); documentos próprios podem ser adicionados e removidos. A situação (válida / vence em breve / vencida / sem data) é calculada no servidor com a data de Brasília. Telas `certidoes.html` e `atestados.html` e o painel usam a API; dados antigos do navegador (`localStorage`) são oferecidos para importação e só são apagados depois de importados sem erro. Testes: `test_habilitacao_logic.py` e `test_habilitacao_integration.py`. Limite: a conferência de exigência do edital continua no navegador, sobre a lista da empresa.

## Integração contínua (2026-10-12)

`.github/workflows/ci.yml`: a cada push/PR sobe PostgreSQL com pgvector e roda `pytest tests` com `REQUIRE_DB=1` (sem banco o teste **falha**, em vez de pular). A primeira execução, com as dependências mais recentes, revelou duas incompatibilidades, já corrigidas: testes de ordem de rotas (agora usam `tests/_rotas.py`) e falso positivo do `schema_diff` com `UTCDateTime` do SQLModel novo. Localmente, sem `REQUIRE_DB`, os testes de banco continuam pulando se o Postgres estiver desligado. Limite: `requirements.txt` usa versões mínimas, então uma biblioteca nova pode quebrar a CI (e a imagem) sem mudança no código.

---

## Próxima ação recomendada

1. Sync Brasil: `POST /ingestion/pncp/sync/async` com `{ "uf": "BR", "only_open": true }` (Dashboard já usa BR)  
2. Minha Receita: `docker compose --profile full up -d` + ETL  
3. Evolution QR: conectar instância e testar digest real  
4. Loop end-to-end com 1 edital no Postgres

Script local (sem Docker): `scripts/smoke_local.py` · Doc: `docs/tecnica/SMOKE_LOCAL.md` · Fase 6: `docs/tecnica/FASE6_INTEGRACAO.md`
