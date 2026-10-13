# Deploy na VPS

Sobe tudo em containers: Postgres (pgvector), Redis, Evolution (WhatsApp), a API e o Caddy (HTTPS automático).
Só as portas 80, 443 e SSH ficam abertas; o resto escuta em `127.0.0.1`. Detalhes de operação e backup:
`docs/usuario/OPERACAO_DOCKER.md`, seção 9.

## Pré-requisitos

- VPS Ubuntu 22.04 ou 24.04, **2 GB de RAM** ou mais (o build da imagem e o Evolution pesam), 20 GB de disco.
- Um **domínio** (ou subdomínio) com registro **A** apontando para o IP da VPS. O HTTPS é obrigatório: o cookie de
  sessão só trafega por ele. Sem domínio próprio, para teste: `DOMAIN=<IP-com-hífens>.sslip.io`
  (ex.: `203-0-113-10.sslip.io`).
- Acesso SSH com usuário que tenha `sudo`.

## 1. Sistema, firewall e Docker

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install git ufw openssl
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw --force enable
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
exit   # saia e entre de novo no SSH para o grupo docker valer
```

Ao voltar: `docker --version && docker compose version`.

## 2. Código

```bash
sudo mkdir -p /opt/licitall && sudo chown $USER:$USER /opt/licitall
git clone https://github.com/Andersonspita/licitall.git /opt/licitall
cd /opt/licitall
```

## 3. Arquivo `.env` (criado do zero, com segredos gerados aqui)

Troque `licitall.seudominio.com.br`, o e-mail e a chave do Gemini antes de colar:

```bash
cd /opt/licitall
cat > .env <<EOF
APP_ENV=production
DOMAIN=licitall.seudominio.com.br
ADMIN_EMAILS=seu@email.com.br
COOKIE_SECURE=true
DEBUG=false
AUTH_REGISTRATION_OPEN=true

POSTGRES_USER=licitall
POSTGRES_DB=licitall
POSTGRES_PASSWORD=$(openssl rand -hex 24)
EVOLUTION_API_KEY=$(openssl rand -hex 32)
EVOLUTION_SERVER_URL=http://localhost:8081

GEMINI_API_KEY=COLE_SUA_CHAVE_AQUI
MINHA_RECEITA_PROD_URL=https://minhareceita.org
INSTALL_DOCLING=false
EOF
chmod 600 .env
```

- `POSTGRES_PASSWORD` só vale na **primeira** criação do banco. Não troque depois sem `ALTER USER` no Postgres.
- Guarde uma cópia do `.env` fora do servidor (gerenciador de senhas). Sem ele, os backups não restauram com a mesma
  senha.

## 4. Subir

```bash
cd /opt/licitall
docker compose --profile app up -d --build
docker compose --profile app ps
docker compose --profile app logs -f api   # Ctrl+C para sair
```

O primeiro build leva alguns minutos. Nos logs da API deve aparecer `Configuração de produção verificada.`,
`migrações: ok` e o Uvicorn escutando. Se a API recusar subir, o log diz qual variável está fraca ou faltando.
O Caddy emite o certificado na primeira visita: confira com `docker compose --profile app logs proxy`.

## 5. Primeiro operador e teste

```bash
docker compose --profile app exec api python -m scripts.criar_usuario \
  --email seu@email.com.br --nome "Seu Nome" --empresa "Sua Empresa" --admin
curl -s https://licitall.seudominio.com.br/health
```

Entre em `https://licitall.seudominio.com.br/ui/login.html`. Depois de criar as contas necessárias, considere
`AUTH_REGISTRATION_OPEN=false` no `.env` e `docker compose --profile app up -d` (cadastro só pelo script).

## 6. Editais

Pela tela (menu de operador) ou pelo terminal, por exemplo os abertos da BA dos últimos 7 dias:

```bash
docker compose --profile app exec api python -m scripts.match_empresa_real 05195608000132 --uf BA --sincronizar 7
```

## 7. WhatsApp (Evolution), quando for usar

O Evolution escuta só em `127.0.0.1:8081` da VPS. Do seu computador, abra um túnel SSH e use o gerenciador:

```bash
ssh -L 8081:127.0.0.1:8081 usuario@IP_DA_VPS
# no navegador do seu computador: http://localhost:8081/manager  (chave: EVOLUTION_API_KEY do .env da VPS)
```

Crie a instância `licitall` e leia o QR Code com o celular.

## 8. Backup diário

```bash
cd /opt/licitall && sh docker/backup.sh
(crontab -l 2>/dev/null; echo "0 3 * * * cd /opt/licitall && sh docker/backup.sh >> backups/backup.log 2>&1") | crontab -
```

Copie a pasta `backups/` para fora do servidor com regularidade: ela contém dados de clientes.

## Atualizar

```bash
cd /opt/licitall && sh docker/backup.sh && git pull && docker compose --profile app up -d --build
```

As migrações rodam sozinhas na subida da API.
