# Operação com Docker — LicitAll

Guia para subir a stack local e validar o fluxo ponta a ponta.

## 1. Pré-requisitos

- Docker Desktop **ligado**
- Python 3.11+ com dependências (`pip install -r requirements.txt`)
- Arquivo `.env` (copie de `.env.example` se existir)

## 2. Subir serviços

```powershell
cd D:\Projetos\licitAll
docker compose up -d
docker compose ps
```

Portas:

| Serviço | URL |
|---------|-----|
| PostgreSQL | `localhost:5433` (padrão; evita conflito com 5432) |
| Redis | `localhost:6380` |
| Minha Receita | http://localhost:8001 (`docker compose --profile full up -d`) |
| Evolution API | http://localhost:8081 |
| Evolution Manager (QR) | http://localhost:3001 |

## 3. API FastAPI

```powershell
uvicorn src.main:app --reload --port 8000
```

Verifique:

```powershell
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/deps
```

## 4. Minha Receita (ETL)

A imagem sobe vazia até carregar dados da Receita Federal.

1. Baixe os dumps oficiais para `data/minha-receita/`
2. Siga a documentação do projeto [Minha Receita](https://github.com/cuducos/minha-receita) para importar no Postgres (`minhareceita`)
3. Teste: `GET http://localhost:8001/12345678000199`

Sem ETL, o matching retorna aviso e lista vazia — o restante do pipeline funciona.

## 5. Evolution (WhatsApp)

1. Abra http://localhost:3000
2. Crie/conecte a instância configurada em `EVOLUTION_INSTANCE` (padrão no `.env`)
3. Escaneie o QR no celular
4. Preview (sem enviar):

```powershell
curl -X POST http://127.0.0.1:8000/outreach/whatsapp/preview -H "Content-Type: application/json" -d "{\"phone\":\"5511999999999\",\"orgao\":\"Teste\",\"objeto\":\"Objeto\",\"valor_total\":1000,\"id_pncp\":\"000/2026\"}"
```

Envio real: `POST /outreach/whatsapp/opportunity` ou pipeline com `"send_whatsapp": true`.

## 6. Pipeline ponta a ponta

Com edital já baixado (ex.: smoke PNCP):

```powershell
curl -X POST "http://127.0.0.1:8000/pipeline/83021808000182-1-000518/2026/run" -H "Content-Type: application/json" -d "{\"download_if_missing\":false,\"persist_kit\":true}"
```

Minutas em `data/raw/{slug}/_kit/*.md`.

## 7. Smoke automatizado

```powershell
python scripts/smoke_compose.py --api http://127.0.0.1:8000
```

Smoke sem Docker (só PNCP/RAG/kit):

```powershell
python scripts/smoke_local.py --api http://127.0.0.1:8000
```

## 8. Troubleshooting

| Sintoma | Ação |
|---------|------|
| `dockerDesktopLinuxEngine` pipe não encontrado | Ligar Docker Desktop |
| Postgres down em `/health/deps` | `docker compose logs postgres` |
| Minha Receita 502 no matching | Carregar ETL ou ignorar com `run_matching: false` |
| Evolution 502 no envio | Conferir QR, API key e instância |

## 9. Publicação em servidor (produção)

Serviços: `api` (a aplicação, só na rede interna), `proxy` (Caddy, HTTPS automático nas portas 80/443), mais Postgres, Redis e Evolution. Postgres, Redis, Minha Receita e Evolution ficam presos a `127.0.0.1`: **não abra essas portas no firewall** (só 80 e 443).

**Antes:** servidor Linux com Docker e Compose v2; um domínio com registro DNS (A) apontando para o IP do servidor.

1. Copie o projeto para o servidor e crie o `.env` a partir de `.env.example`. Preencha, no mínimo:
   - `APP_ENV=production`, `DOMAIN=seu.dominio.com.br`, `COOKIE_SECURE=true`, `DEBUG=false`
   - `POSTGRES_PASSWORD` e `EVOLUTION_API_KEY` com valores **aleatórios longos** (`python -c "import secrets; print(secrets.token_urlsafe(24))"`)
   - `ADMIN_EMAILS=seu@email.com.br` (quem opera captação e pipeline)
   - `POSTGRES_PASSWORD` só vale na **primeira** criação do volume do banco; trocar depois exige `ALTER USER` no Postgres.
2. Suba: `docker compose --profile app up -d --build`. Ao iniciar, a API **recusa subir** (e diz o motivo, veja `docker compose logs api`) se a senha do banco, a chave do Evolution ou o cookie estiverem fracos/padrão, depois aplica as migrações do banco.
3. Crie o primeiro operador (a senha é pedida no terminal, sem eco): `docker compose --profile app exec api python -m scripts.criar_usuario --email seu@email.com.br --nome "Seu Nome" --empresa "Sua Empresa" --admin`
4. Confira: `https://seu.dominio.com.br/health` e entre em `https://seu.dominio.com.br/`. Depois de criar as contas necessárias, considere `AUTH_REGISTRATION_OPEN=false` (cadastro só pelo script).

**Atualizar:** `git pull && docker compose --profile app up -d --build`. As migrações rodam sozinhas. Faça um backup antes. **Desfazer a última migração:** `docker compose --profile app exec api alembic downgrade -1`.

**Banco criado antes do Alembic** (por exemplo o de desenvolvimento): é reconhecido na primeira subida e "adotado" sem perder dados; se o esquema dele divergir dos modelos, em produção a API aborta e explica.

**Teste local do HTTPS:** com `DOMAIN=localhost` o Caddy usa um certificado próprio (o navegador avisa; `curl -k` ignora). Use `HTTP_PORT=8088 HTTPS_PORT=8443` se 80/443 estiverem ocupadas.

### Backup e restauração

- Backup: `sh docker/backup.sh` grava `backups/licitall-AAAAMMDD-HHMMSS.dump`, valida o arquivo e apaga os de mais de 30 dias. Agende no cron (exemplo no cabeçalho do script). Os backups contêm dados de clientes: guarde-os fora do servidor, com acesso restrito.
- Restaurar (substitui o conteúdo atual): `docker compose exec -T postgres pg_restore -U licitall -d licitall --clean --if-exists < backups/ARQUIVO.dump`
- Não estão no dump: as sessões de WhatsApp (volume `evolution_instances`) e os documentos baixados (volume `licitall_data`).

### Antes de abrir para clientes

- Fixe as versões das imagens `evolution-api` e `minha-receita` (hoje `latest`).
- HTTPS é obrigatório (o cookie de sessão só trafega por ele). Mantenha o servidor atualizado e o firewall só com 80/443 e SSH.
- Falta: recuperação de senha por e-mail, limite de uso das rotas com IA, monitoramento/alertas e política de privacidade (LGPD). Veja `docs/fase/STATUS.md`.
