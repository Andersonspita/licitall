"""Recusa subir em produção com configuração insegura (falha cedo e com mensagem clara)."""

from __future__ import annotations

import sys
from urllib.parse import urlparse

from src.config.settings import Settings, get_settings

_SENHAS_FRACAS = {"", "licitall", "postgres", "password", "123456", "admin", "changeme"}
MIN_SENHA_BANCO = 12


def production_problems(s: Settings) -> list[str]:
    problems: list[str] = []
    if not s.cookie_secure:
        problems.append("COOKIE_SECURE deve ser true: o cookie de sessão só pode trafegar por HTTPS.")
    if s.debug:
        problems.append("DEBUG deve ser false: ele libera /docs e /openapi.json.")
    senha_db = urlparse(s.database_url).password or ""
    if senha_db.lower() in _SENHAS_FRACAS or len(senha_db) < MIN_SENHA_BANCO:
        problems.append(f"A senha do banco (DATABASE_URL) é fraca ou padrão: use ao menos {MIN_SENHA_BANCO} caracteres aleatórios.")
    chave = s.evolution_api_key
    if chave.startswith("licitall-dev") or len(chave) < 20:
        problems.append("EVOLUTION_API_KEY é a chave de desenvolvimento (ou curta): gere uma chave aleatória.")
    if not [e for e in s.admin_emails.split(",") if e.strip()]:
        problems.append("Defina ADMIN_EMAILS: sem operador ninguém consegue captar editais nem operar a plataforma.")
    return problems


def assert_production_ready(s: Settings) -> None:
    """Só atua com APP_ENV=production."""
    if s.app_env.lower() != "production":
        return
    problems = production_problems(s)
    if problems:
        raise RuntimeError("Configuração insegura para produção:\n" + "\n".join(f"  - {p}" for p in problems))


if __name__ == "__main__":  # usado pelo entrypoint do container
    try:
        assert_production_ready(get_settings())
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    print("Configuração de produção verificada.")
