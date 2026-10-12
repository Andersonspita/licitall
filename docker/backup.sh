#!/bin/sh
# Backup do banco do LicitAll (formato custom do pg_dump, comprimido). Uso, na pasta do projeto:
#   sh docker/backup.sh            # grava em backups/licitall-AAAAMMDD-HHMMSS.dump
#   KEEP_DAYS=14 sh docker/backup.sh   # apaga backups com mais de 14 dias (padrão: 30)
# Agende no cron do servidor, por exemplo todo dia às 03:00:
#   0 3 * * * cd /opt/licitall && sh docker/backup.sh >> backups/backup.log 2>&1
# Restaurar: veja docs/usuario/OPERACAO_DOCKER.md ("Backup e restauração").
set -eu
DIR="${BACKUP_DIR:-backups}"
USER_DB="${POSTGRES_USER:-licitall}"
NAME_DB="${POSTGRES_DB:-licitall}"
KEEP_DAYS="${KEEP_DAYS:-30}"
mkdir -p "$DIR"
umask 077
FILE="$DIR/licitall-$(date +%Y%m%d-%H%M%S).dump"
docker compose exec -T postgres pg_dump -U "$USER_DB" -d "$NAME_DB" -Fc > "$FILE"
# um dump vazio ou truncado não pode passar por backup válido
[ -s "$FILE" ] || { echo "ERRO: backup vazio, removendo $FILE" >&2; rm -f "$FILE"; exit 1; }
docker compose exec -T postgres pg_restore -l < "$FILE" > /dev/null || { echo "ERRO: backup ilegível, removendo $FILE" >&2; rm -f "$FILE"; exit 1; }
find "$DIR" -name 'licitall-*.dump' -mtime +"$KEEP_DAYS" -delete
echo "backup ok: $FILE ($(wc -c < "$FILE") bytes)"
