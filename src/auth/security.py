"""Primitivas de autenticação sem dependências externas (stdlib): hash de senha, token, limite de tentativas."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from urllib.parse import urlparse

# scrypt (OWASP: N=2^15, r=8, p=1) — ~32 MB e ~0,1 s por verificação.
_N, _R, _P = 2**15, 8, 1
_MAXMEM = 64 * 1024 * 1024
MIN_PASSWORD = 8
MAX_PASSWORD = 128


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, maxmem=_MAXMEM, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(digest_hex)
        got = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p),
            maxmem=_MAXMEM, dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, expected)


_DUMMY_HASH = hash_password("senha-fantasma-para-igualar-o-tempo")


def burn_verify(password: str) -> None:
    """Gasta o mesmo tempo de uma verificação real quando o e-mail não existe (evita revelar contas pelo tempo)."""
    verify_password(password, _DUMMY_HASH)


def password_problem(password: str) -> str | None:
    if len(password) < MIN_PASSWORD:
        return f"A senha deve ter pelo menos {MIN_PASSWORD} caracteres."
    if len(password) > MAX_PASSWORD:
        return f"A senha deve ter no máximo {MAX_PASSWORD} caracteres."
    if password.strip() != password or not password.strip():
        return "A senha não pode começar nem terminar com espaço."
    return None


def new_session_token() -> tuple[str, str]:
    """(token para o cookie, hash para o banco)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


class LoginThrottle:
    """Bloqueia por 15 min após 5 falhas em 15 min, por (e-mail, IP). Em memória: vale por processo."""

    def __init__(self, max_failures: int = 5, window: int = 900, clock=time.monotonic) -> None:
        self.max_failures, self.window, self._clock = max_failures, window, clock
        self._fails: dict[str, list[float]] = {}

    def _recent(self, key: str) -> list[float]:
        now = self._clock()
        fails = [t for t in self._fails.get(key, []) if now - t < self.window]
        if fails:
            self._fails[key] = fails
        else:
            self._fails.pop(key, None)
        return fails

    def retry_after(self, key: str) -> int:
        """Segundos até poder tentar de novo (0 = liberado)."""
        fails = self._recent(key)
        if len(fails) < self.max_failures:
            return 0
        return max(1, int(self.window - (self._clock() - fails[0])))

    def fail(self, key: str) -> None:
        self._fails.setdefault(key, []).append(self._clock())
        if len(self._fails) > 10_000:  # limite de memória
            self._fails.pop(next(iter(self._fails)))

    def success(self, key: str) -> None:
        self._fails.pop(key, None)


def origin_ok(method: str, origin: str | None, host: str | None) -> bool:
    """Defesa extra contra CSRF: requisição que altera dados e traz Origin de outro site é recusada."""
    if method.upper() in ("GET", "HEAD", "OPTIONS") or not origin:
        return True
    return urlparse(origin).netloc.lower() == (host or "").lower()


_PUBLIC_EXACT = {"/", "/app", "/health", "/auth/login", "/auth/register", "/auth/logout", "/auth/config"}
_PUBLIC_PREFIX = ("/ui",)
_ADMIN_PREFIX = (
    "/ingestion", "/pipeline", "/parser", "/outreach", "/rag/index",
    "/matching/reverse", "/matching/digest/run-due", "/health/deps", "/health/detail",
)


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def required_role(path: str) -> str:
    """'public' | 'user' | 'admin'. O que não está listado exige login (seguro por padrão)."""
    path = "/" + path.strip("/") if path != "/" else path
    if path in _PUBLIC_EXACT or any(_under(path, p) for p in _PUBLIC_PREFIX):
        return "public"
    if any(_under(path, p) for p in _ADMIN_PREFIX):
        return "admin"
    # "Reprocessar" do cliente (extract) é de usuário; o grafo completo, que baixa e processa, é do operador.
    if path.startswith("/agents/") and path.endswith("/graph"):
        return "admin"
    return "user"


_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def valid_email(email: str) -> bool:
    return bool(_EMAIL.match(email)) and len(email) <= 254
