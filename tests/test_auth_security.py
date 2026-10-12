"""Primitivas de autenticação (sem banco)."""

from __future__ import annotations

from src.auth.security import (
    LoginThrottle,
    hash_password,
    hash_token,
    new_session_token,
    normalize_email,
    origin_ok,
    password_problem,
    required_role,
    valid_email,
    verify_password,
)


def test_hash_de_senha_e_verificacao():
    h = hash_password("uma-senha-forte-123")
    assert h.startswith("scrypt$") and "uma-senha-forte-123" not in h
    assert verify_password("uma-senha-forte-123", h)
    assert not verify_password("uma-senha-forte-124", h)
    assert not verify_password("", h)


def test_hash_usa_sal_diferente_a_cada_vez():
    assert hash_password("mesma-senha-123") != hash_password("mesma-senha-123")


def test_hash_corrompido_nao_levanta_excecao():
    for lixo in ("", "abc", "scrypt$1$2", "bcrypt$x$y$z$a$b", "scrypt$a$b$c$zz$yy"):
        assert verify_password("x", lixo) is False


def test_politica_de_senha():
    assert password_problem("curta") is not None
    assert password_problem("a" * 129) is not None
    assert password_problem(" com-espaco-na-borda ") is not None
    assert password_problem("senha-valida-123") is None


def test_token_de_sessao_so_o_hash_vai_ao_banco():
    raw, hashed = new_session_token()
    assert len(raw) >= 40 and hashed == hash_token(raw) and raw not in hashed
    assert new_session_token()[0] != raw


def test_email():
    assert normalize_email("  Ana@Empresa.COM.br ") == "ana@empresa.com.br"
    assert valid_email("ana@empresa.com.br")
    for ruim in ("semarroba", "a@b", "a b@c.com", "@c.com", ""):
        assert not valid_email(ruim)


def test_throttle_bloqueia_apos_5_falhas_e_libera_depois():
    t = [1000.0]
    th = LoginThrottle(clock=lambda: t[0])
    for _ in range(4):
        th.fail("a|1")
    assert th.retry_after("a|1") == 0
    th.fail("a|1")
    assert 0 < th.retry_after("a|1") <= 900
    assert th.retry_after("outro|1") == 0  # chave diferente não é afetada
    t[0] += 901
    assert th.retry_after("a|1") == 0


def test_throttle_sucesso_zera():
    th = LoginThrottle()
    for _ in range(5):
        th.fail("a|1")
    th.success("a|1")
    assert th.retry_after("a|1") == 0


def test_origin_ok():
    assert origin_ok("GET", "http://evil.example", "app.local")
    assert origin_ok("POST", None, "app.local")
    assert origin_ok("POST", "http://app.local", "app.local")
    assert origin_ok("DELETE", "https://APP.local", "app.local")  # esquema e caixa não importam; o host sim
    assert not origin_ok("POST", "http://evil.example", "app.local")
    assert not origin_ok("PUT", "http://app.local.evil.example", "app.local")


def test_matriz_de_papeis():
    for p in ("/", "/health", "/auth/login", "/auth/register", "/auth/config", "/ui/login.html", "/ui/assets/app.css"):
        assert required_role(p) == "public", p
    for p in ("/tenders", "/tenders/x/2026", "/matching/profiles", "/matching/profiles/abc/oportunidades",
              "/auth/me", "/rag/search", "/advisory/generate", "/matching/search", "/agents/x/extract", "/qualquer/coisa/nova"):
        assert required_role(p) == "user", p
    for p in ("/ingestion/pncp/sync", "/ingestion/modalidades", "/pipeline/x/run", "/parser/x", "/agents/x/graph",
              "/outreach/whatsapp/digest", "/rag/index/lei-14133", "/matching/reverse/run",
              "/matching/digest/run-due", "/health/deps", "/health/detail"):
        assert required_role(p) == "admin", p


def test_prefixo_parecido_nao_vira_publico_nem_admin():
    assert required_role("/uiX/secreto") == "user"          # só "/ui" e "/ui/..." são públicos
    assert required_role("/healthy") == "user"
    assert required_role("/ingestionx") == "user"
    assert required_role("//tenders") == "user"
