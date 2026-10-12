#!/bin/sh
# Antes de subir a API: recusa configuração insegura (APP_ENV=production) e aplica as migrações do banco.
set -e
python -m src.config.production
python -m src.db.migrate
exec "$@"
