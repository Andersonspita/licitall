"""Autenticação e isolamento entre empresas contra um PostgreSQL real.

Pula sozinho se o banco não estiver acessível. URL: TEST_DATABASE_URL (padrão: o Postgres do docker compose, porta 5433).
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest
from sqlalchemy import text

DB_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://licitall:licitall@localhost:5433/licitall")
TAG = uuid.uuid4().hex[:8]
ADMIN_EMAIL = f"itest-admin-{TAG}@teste.com.br"
SENHA = "senha-de-teste-123"


def _email(nome: str) -> str:
    return f"itest-{nome}-{TAG}@teste.com.br"


@pytest.fixture
async def ambiente(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("ADMIN_EMAILS", ADMIN_EMAIL)
    monkeypatch.setenv("AUTH_REGISTRATION_OPEN", "true")
    monkeypatch.setenv("DIGEST_SCHEDULER_ENABLED", "false")

    import src.db as dbmod
    from src.config import get_settings

    get_settings.cache_clear()
    dbmod._engine = None
    dbmod._session_factory = None
    try:
        await dbmod.init_db()
        async with dbmod.get_engine().connect() as c:
            await c.execute(text("select 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL indisponível para o teste de integração: {exc}")

    from src.auth.routes import throttle
    from src.main import app

    throttle._fails.clear()

    def novo_cliente() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")

    yield novo_cliente, dbmod

    async with dbmod.get_session_factory()() as s:
        await s.execute(text("delete from perfis_interesse where empresa_id in (select id::text from empresas where nome like :p)"), {"p": f"ITEST {TAG}%"})
        await s.execute(text("delete from usuarios where email like :p"), {"p": f"itest-%-{TAG}@teste.com.br"})
        await s.execute(text("delete from empresas where nome like :p"), {"p": f"ITEST {TAG}%"})
        await s.commit()
    await dbmod.get_engine().dispose()
    dbmod._engine = None
    dbmod._session_factory = None
    throttle._fails.clear()
    get_settings.cache_clear()


async def _registrar(c: httpx.AsyncClient, nome: str, senha: str = SENHA, email: str | None = None):
    return await c.post("/auth/register", json={
        "empresa_nome": f"ITEST {TAG} {nome}", "nome": f"Usuario {nome}", "email": email or _email(nome), "senha": senha,
    })


PERFIL = {"nome_perfil": "Papelaria", "ufs_permitidas": ["BA"], "palavras_positivas": ["papel"]}


@pytest.mark.asyncio
async def test_rotas_fechadas_sem_login_e_health_enxuto(ambiente):
    novo, _ = ambiente
    async with novo() as c:
        for caminho in ("/tenders", "/tenders/stats", "/matching/profiles", "/auth/me", "/rag/search?q=x"):
            assert (await c.get(caminho)).status_code == 401, caminho
        assert (await c.post("/matching/profiles", json=PERFIL)).status_code == 401
        h = await c.get("/health")
        assert h.status_code == 200 and set(h.json()) == {"status", "version"}  # sem caminhos nem endereços internos
        assert (await c.get("/auth/config")).json() == {"registro_aberto": True}
        assert (await c.get("/ui/login.html")).status_code == 200


@pytest.mark.asyncio
async def test_cadastro_login_logout_e_cookie_seguro(ambiente):
    novo, _ = ambiente
    async with novo() as c:
        assert (await _registrar(c, "x", senha="curta")).status_code == 422
        assert (await _registrar(c, "x", email="sem-arroba")).status_code == 422
        r = await _registrar(c, "a")
        assert r.status_code == 201 and r.json()["email"] == _email("a") and r.json()["admin"] is False
        cookie = r.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
        assert "senha" not in r.text and "hash" not in r.text
        assert (await c.get("/auth/me")).json()["empresa"]["nome"] == f"ITEST {TAG} a"
        assert (await _registrar(c, "a")).status_code == 409  # e-mail repetido

        assert (await c.post("/auth/logout")).status_code == 204
        assert (await c.get("/auth/me")).status_code == 401

    async with novo() as c2:  # login em outro "navegador"
        assert (await c2.post("/auth/login", json={"email": _email("a"), "senha": "senha-errada-123"})).status_code == 401
        assert (await c2.post("/auth/login", json={"email": "ninguem@teste.com.br", "senha": SENHA})).status_code == 401
        ok = await c2.post("/auth/login", json={"email": _email("a").upper(), "senha": SENHA})  # e-mail não diferencia caixa
        assert ok.status_code == 200
        assert (await c2.get("/auth/me")).status_code == 200


@pytest.mark.asyncio
async def test_mensagem_de_erro_nao_revela_se_a_conta_existe(ambiente):
    novo, _ = ambiente
    async with novo() as c:
        await _registrar(c, "b")
    async with novo() as c2:
        a = await c2.post("/auth/login", json={"email": _email("b"), "senha": "errada-errada-1"})
        b = await c2.post("/auth/login", json={"email": "nao-existe@teste.com.br", "senha": "errada-errada-1"})
        assert a.status_code == b.status_code == 401 and a.json() == b.json()


@pytest.mark.asyncio
async def test_bloqueio_apos_varias_senhas_erradas(ambiente):
    novo, _ = ambiente
    async with novo() as c:
        await _registrar(c, "c")
    async with novo() as c2:
        for _ in range(5):
            assert (await c2.post("/auth/login", json={"email": _email("c"), "senha": "errada-errada-1"})).status_code == 401
        r = await c2.post("/auth/login", json={"email": _email("c"), "senha": SENHA})  # até a senha certa é barrada
        assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


@pytest.mark.asyncio
async def test_isolamento_entre_empresas(ambiente):
    novo, dbmod = ambiente
    async with novo() as a, novo() as b:
        await _registrar(a, "dona")
        await _registrar(b, "intrusa")

        # O cliente não escolhe a empresa: um empresa_id forjado no corpo é ignorado.
        r = await a.post("/matching/profiles", json={**PERFIL, "empresa_id": "outra-empresa"})
        assert r.status_code == 201
        pid = r.json()["id"]
        me = (await a.get("/auth/me")).json()
        assert r.json()["empresa_id"] == me["empresa"]["id"]

        assert [p["id"] for p in (await a.get("/matching/profiles")).json()["perfis"]] == [pid]
        # a empresa intrusa não vê nada, nem forçando o parâmetro antigo
        assert (await b.get("/matching/profiles")).json()["perfis"] == []
        assert (await b.get(f"/matching/profiles?empresa_id={me['empresa']['id']}")).json()["perfis"] == []

        # e responde 404 (e não 403) em todo acesso direto ao perfil alheio
        corpo = {"id_pncp": "x"}
        agenda = {"telefone": "5571999999999", "horario": "08:00"}
        tentativas = [
            await b.delete(f"/matching/profiles/{pid}"),
            await b.get(f"/matching/profiles/{pid}/oportunidades"),
            await b.get(f"/matching/profiles/{pid}/digest"),
            await b.post(f"/matching/profiles/{pid}/filter", json=corpo),
            await b.post(f"/matching/profiles/{pid}/candidates", json=corpo),
            await b.post(f"/matching/profiles/{pid}/match", json=corpo),
            await b.post(f"/matching/profiles/{pid}/palavras", json={"termo": "x"}),
            await b.post(f"/matching/profiles/{pid}/digest/send", json={"phone": "5571999999999"}),
            await b.put(f"/matching/profiles/{pid}/agendamento", json=agenda),
            await b.get(f"/matching/profiles/{pid}/agendamento"),
            await b.delete(f"/matching/profiles/{pid}/agendamento"),
        ]
        assert [t.status_code for t in tentativas] == [404] * len(tentativas)

        # feedback em oportunidade de outra empresa
        from src.models.tables import MatchItem

        async with dbmod.get_session_factory()() as s:
            m = MatchItem(perfil_id=uuid.UUID(pid), id_pncp=f"itest-{TAG}", numero_item=1, score_total=80, alerta=True)
            s.add(m)
            await s.commit()
            mid = str(m.id)
        assert (await b.post(f"/matching/matches/{mid}/feedback", json={"relevante": False})).status_code == 404
        assert (await a.post(f"/matching/matches/{mid}/feedback", json={"relevante": True})).status_code == 200

        # nada foi alterado pela intrusa
        assert (await a.get(f"/matching/profiles/{pid}/oportunidades")).status_code == 200
        assert len((await a.get("/matching/profiles")).json()["perfis"]) == 1


@pytest.mark.asyncio
async def test_rotas_de_operador_exigem_admin(ambiente):
    novo, _ = ambiente
    async with novo() as user, novo() as admin:
        await _registrar(user, "comum")
        r = await admin.post("/auth/register", json={
            "empresa_nome": f"ITEST {TAG} operadora", "nome": "Operadora", "email": ADMIN_EMAIL, "senha": SENHA})
        assert r.status_code == 201 and r.json()["admin"] is True

        for caminho in ("/ingestion/modalidades", "/health/deps", "/health/detail"):
            assert (await user.get(caminho)).status_code == 403, caminho
        for caminho in ("/ingestion/pncp/sync", "/matching/reverse/run", "/matching/digest/run-due", "/outreach/whatsapp/digest"):
            assert (await user.post(caminho, json={})).status_code == 403, caminho
        assert (await admin.get("/ingestion/modalidades")).status_code == 200


@pytest.mark.asyncio
async def test_origem_externa_nao_altera_dados_e_sessao_expirada(ambiente):
    novo, dbmod = ambiente
    async with novo() as c:
        await _registrar(c, "csrf")
        r = await c.post("/matching/profiles", json=PERFIL, headers={"Origin": "http://site-malicioso.example"})
        assert r.status_code == 403
        assert (await c.get("/matching/profiles")).json()["perfis"] == []  # nada foi criado
        assert (await c.post("/matching/profiles", json=PERFIL, headers={"Origin": "http://testserver"})).status_code == 201

        async with dbmod.get_session_factory()() as s:  # envelhece a sessão
            await s.execute(text("update sessoes set expires_at = now() - interval '1 minute' where usuario_id = (select id from usuarios where email = :e)"), {"e": _email("csrf")})
            await s.commit()
        assert (await c.get("/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_cadastro_fechado(ambiente, monkeypatch):
    novo, _ = ambiente
    from src.config import get_settings

    monkeypatch.setenv("AUTH_REGISTRATION_OPEN", "false")
    get_settings.cache_clear()
    async with novo() as c:
        assert (await c.get("/auth/config")).json() == {"registro_aberto": False}
        assert (await _registrar(c, "fechado")).status_code == 403
