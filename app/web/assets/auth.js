/** Auth local (demo). Trocar por JWT/sessão FastAPI quando houver usuários reais. */
(function (global) {
  const KEY = "licitall_session";
  const DEMO = { email: "admin@licitall.local", password: "licitall", name: "Operador" };

  function read() {
    try {
      return JSON.parse(localStorage.getItem(KEY) || "null");
    } catch {
      return null;
    }
  }

  function write(session) {
    localStorage.setItem(KEY, JSON.stringify(session));
  }

  const Auth = {
    demoCredentials: DEMO,
    getSession() {
      return read();
    },
    isAuthenticated() {
      const s = read();
      return Boolean(s && s.email && s.expiresAt && Date.now() < s.expiresAt);
    },
    login(email, password) {
      const ok =
        (email === DEMO.email && password === DEMO.password) ||
        (String(email || "").includes("@") && String(password || "").length >= 6);
      if (!ok) {
        throw new Error("Credenciais inválidas. Use admin@licitall.local / licitall");
      }
      const session = {
        email: email.trim(),
        name: email === DEMO.email ? DEMO.name : String(email).split("@")[0],
        role: "Especialista em Licitações / GovOps",
        expiresAt: Date.now() + 12 * 60 * 60 * 1000,
      };
      write(session);
      return session;
    },
    logout() {
      localStorage.removeItem(KEY);
    },
    requireAuth(loginUrl) {
      if (!this.isAuthenticated()) {
        const next = encodeURIComponent(location.pathname + location.search + location.hash);
        location.replace((loginUrl || "/ui/login.html") + "?next=" + next);
        return false;
      }
      return true;
    },
  };

  global.LicitAllAuth = Auth;
})(window);
