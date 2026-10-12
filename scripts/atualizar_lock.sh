#!/usr/bin/env sh
# Regenera requirements.lock (versões exatas, inclusive indiretas) a partir de requirements.txt.
# Rode depois de mudar requirements.txt ou para atualizar bibliotecas de propósito; depois rode os testes.
#   sh scripts/atualizar_lock.sh            # mantém o que já está travado, só resolve o que mudou
#   sh scripts/atualizar_lock.sh --upgrade  # atualiza tudo para a versão mais nova permitida
set -e
cd "$(dirname "$0")/.."
uv pip compile requirements.txt --python-version 3.12 --universal --no-header -o requirements.lock "$@"
