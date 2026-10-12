/** Autenticação no navegador. A sessão vive em um cookie HttpOnly emitido pela API; aqui só se guarda o perfil em memória. */
(function (global) {
  const LOGIN = "/ui/login.html";
  let me = null;

  // Resquício do login de protótipo (guardava a sessão em localStorage).
  try { localStorage.removeItem("licitall_session"); } catch { /* sem acesso ao storage */ }

  async function api(url, options) {
    const res = await fetch(url, {
      credentials: "same-origin",
      ...options,
      headers: { "Content-Type": "application/json", ...((options && options.headers) || {}) },
    });
    const data = res.status === 204 ? null : await res.json().catch(() => ({}));
    if (!res.ok) {
      const d = data && data.detail;
      const err = new Error(typeof d === "string" ? d : Array.isArray(d) ? "Confira os campos informados." : "Erro " + res.status);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  /** Só aceita destinos internos da interface (evita redirecionar o usuário para outro site). */
  function safeNext(value) {
    return typeof value === "string" && /^\/ui\/[A-Za-z0-9_\-./]*(\?[^\s]*)?(#[^\s]*)?$/.test(value) && !value.includes("//")
      ? value
      : "/ui/dashboard.html";
  }

  function goLogin() {
    const next = encodeURIComponent(location.pathname + location.search + location.hash);
    location.replace(LOGIN + "?next=" + next);
  }

  // Sessão expirada em qualquer chamada da página: volta ao login em vez de mostrar erro solto.
  const nativeFetch = global.fetch.bind(global);
  global.fetch = async function (input, init) {
    const res = await nativeFetch(input, init);
    const url = typeof input === "string" ? input : (input && input.url) || "";
    if (res.status === 401 && !url.includes("/auth/") && !location.pathname.endsWith("/login.html") && !location.pathname.endsWith("/cadastro.html")) {
      me = null;
      goLogin();
    }
    return res;
  };

  global.LicitAllAuth = {
    getSession() { return me; },
    safeNext,
    async refresh() {
      try { me = await api("/auth/me"); } catch { me = null; }
      return me;
    },
    async login(email, senha) {
      me = await api("/auth/login", { method: "POST", body: JSON.stringify({ email, senha }) });
      return me;
    },
    async register(dados) {
      me = await api("/auth/register", { method: "POST", body: JSON.stringify(dados) });
      return me;
    },
    async logout() {
      try { await nativeFetch("/auth/logout", { method: "POST", credentials: "same-origin" }); } catch { /* segue para o login */ }
      me = null;
    },
    async config() { return api("/auth/config"); },
    /** true se há sessão válida; senão redireciona ao login. */
    async requireAuth() {
      if (await this.refresh()) return true;
      goLogin();
      return false;
    },
  };
})(window);
