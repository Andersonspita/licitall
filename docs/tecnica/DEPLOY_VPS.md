# Deploy na VPS

Guia mínimo para subir o LicitAll em uma VPS Linux (Docker). Ajuste domínio, firewall e secrets antes de produção.

## Pré-requisitos

- Ubuntu 22.04+ (ou similar)
- Docker Engine + Compose plugin
- Portas: `80/443` (proxy), e internamente `5432`, `6379`, `8000`, `8001`, `8080` conforme exposição
- Repositório: `https://github.com/Andersonspita/licitall.git`

## 1. Clone (somente este repo)

```bash
sudo mkdir -p /opt/licitall && sudo chown $USER:$USER /opt/licitall
cd /opt/licitall
git clone https://github.com/Andersonspita/licitall.git .
```

Não é necessário clonar Docling/LangGraph/etc. na VPS: use PyPI (`requirements.txt`) e imagens Docker do Compose.

## 2. Ambiente

```bash
cp .env.example .env
nano .env   # senhas fortes: POSTGRES_PASSWORD, EVOLUTION_API_KEY, OPENAI_API_KEY
```

Gere uma `EVOLUTION_API_KEY` longa e única. Não commite `.env`.

## 3. Infra

```bash
docker compose up -d
docker compose ps
```

Confirme Postgres healthy e Evolution em `8080`.

## 4. API

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Docling é pesado; na VPS pode instalar sob demanda na Fase 2
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Produção recomendada: systemd ou container próprio + Caddy/Nginx com TLS.

Exemplo unit systemd (`/etc/systemd/system/licitall.service`):

```ini
[Unit]
Description=LicitAll API
After=network.target docker.service

[Service]
WorkingDirectory=/opt/licitall
EnvironmentFile=/opt/licitall/.env
ExecStart=/opt/licitall/.venv/bin/uvicorn src.main:app --host 127.0.0.1 --port 8000
Restart=always
User=www-data

[Install]
WantedBy=multi-user.target
```

## 5. Proxy reverso (exemplo Caddy)

```
api.seudominio.com {
  reverse_proxy 127.0.0.1:8000
}
```

## 6. Smoke test

```bash
curl -s https://api.seudominio.com/health
curl -s -X POST https://api.seudominio.com/ingestion/pncp/sync \
  -H 'Content-Type: application/json' \
  -d '{"uf":"SP","only_open":true}'
```

## 7. Minha Receita e Evolution

- **Minha Receita:** a imagem sobe vazia até carregar o ETL da Receita (processo pesado). Em produção, use volume persistente ou serviço já populado.
- **Evolution:** abra o manager (`:3000` ou via proxy), crie a instância `licitall` e escaneie o QR.

## Checklist de segurança

- [ ] Senhas e API keys trocadas em relação ao `.env.example`
- [ ] Postgres/Redis **não** expostos publicamente (bind interno ou firewall)
- [ ] TLS no reverse proxy
- [ ] Backup do volume `licitall_pgdata`
- [ ] Atualizações: `git pull` + `docker compose pull` + restart controlado
