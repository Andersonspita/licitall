/** Shell compartilhado: sidebar + topbar do design system LicitAll. */
(function (global) {
  const NAV = [
    {
      group: "Visão geral",
      items: [
        { id: "dashboard-geral", href: "/ui/dashboard.html", label: "Painel", icon: "dashboard" },
      ],
    },
    {
      group: "1. Oportunidades",
      items: [
        { id: "editais-e-trs", href: "/ui/editais.html", label: "Editais abertos", icon: "gavel" },
        { id: "perfis", href: "/ui/perfis.html", label: "Aderência ao perfil", icon: "tune" },
        { id: "matchmaking-b2g", href: "/ui/matchmaking.html", label: "Match por CNPJ", icon: "handshake", note: "CNAE · porte" },
        { id: "monitor-pncp", href: "/ui/monitor-pncp.html", label: "Captação PNCP", icon: "radar", admin: true },
      ],
    },
    {
      group: "2. Análise do edital",
      items: [
        { id: "explorador-analise-edital", href: "/ui/edital.html", label: "Analisar edital", icon: "document_scanner" },
        { id: "rag-lei-14133", href: "/ui/rag.html", label: "Consulta à Lei 14.133", icon: "menu_book" },
        { id: "pecas-minutas", href: "/ui/pecas.html", label: "Impugnações e peças", icon: "policy" },
      ],
    },
    {
      group: "3. Habilitação",
      items: [
        { id: "certidoes", href: "/ui/certidoes.html", label: "Certidões", icon: "verified_user", note: "Validades" },
        { id: "atestados", href: "/ui/atestados.html", label: "Atestados técnicos", icon: "workspace_premium" },
      ],
    },
    {
      group: "4. Proposta e disputa",
      items: [
        { id: "simulador-lance", href: "/ui/simulador.html", label: "Simulador de lance", icon: "calculate", note: "Margem" },
      ],
    },
    {
      group: "5. Alertas",
      items: [
        { id: "disparos-whatsapp", href: "/ui/whatsapp.html", label: "Notificações WhatsApp", icon: "chat", admin: true },
      ],
    },
    {
      group: "Administração",
      admin: true,
      items: [
        { id: "pipeline-langgraph", href: "/ui/pipeline.html", label: "Pipeline de análise", icon: "account_tree" },
        { id: "parser-docling", href: "/ui/parser.html", label: "Leitura de documentos", icon: "description" },
        { id: "logs-microservicos", href: "/ui/logs.html", label: "Status dos serviços", icon: "terminal" },
        { id: "configuracoes", href: "/ui/config.html", label: "Configurações", icon: "settings" },
      ],
    },
  ];

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function navHtml(active, isAdmin) {
    return NAV.filter((group) => isAdmin || !group.admin).map((group) => {
      const links = group.items
        .filter((item) => isAdmin || !item.admin)
        .map((item) => {
          const isActive = item.id === active;
          const cls = isActive
            ? "flex items-center justify-between px-space-sm py-2 rounded transition-colors bg-secondary-container text-on-secondary-container font-semibold shadow-sm"
            : "flex items-center justify-between px-space-sm py-2 rounded text-on-surface-variant hover:bg-surface-container hover:text-on-surface transition-colors";
          const badge = item.badge
            ? `<span class="font-label-sm text-label-sm px-1.5 py-0.5 rounded ${item.badgeClass || ""} font-semibold">${esc(item.badge)}</span>`
            : item.note
              ? `<span class="font-label-sm text-label-sm text-outline">${esc(item.note)}</span>`
              : "";
          return `<a class="${cls}" data-path="${esc(item.id)}" href="${esc(item.href)}"${isActive ? ' aria-current="page"' : ""}>
            <div class="flex items-center gap-2">
              <span class="material-symbols-outlined text-[18px]">${esc(item.icon)}</span>
              <span class="font-label-lg text-label-lg">${esc(item.label)}</span>
            </div>${badge}
          </a>`;
        })
        .join("");
      return `<div class="flex flex-col gap-1">
        <span class="px-space-sm py-1 font-label-sm text-label-sm uppercase tracking-wider text-outline font-bold">${esc(group.group)}</span>
        ${links}
      </div>`;
    }).join("");
  }

  async function mount(options) {
    if (!global.LicitAllAuth || !(await global.LicitAllAuth.requireAuth())) return;
    render(options || {});
  }

  function render(opts) {
    const active = opts.active || "dashboard-geral";
    const session = global.LicitAllAuth.getSession() || {};
    const isAdmin = Boolean(session.admin);
    const root = document.getElementById("app-root");
    if (!root) return;

    const main = root.querySelector("[data-page]") || root.firstElementChild;
    // Tela de operador aberta por quem não é operador: aviso claro em vez de erros 403 soltos.
    const restricted = !isAdmin && NAV.some((g) => g.items.some((i) => i.id === active && (i.admin || g.admin)));
    const mainHtml = restricted
      ? `<div class="max-w-xl bg-surface-container-lowest rounded shadow-sm p-space-lg flex flex-col gap-2">
           <h1 class="font-headline-lg text-headline-lg tracking-tight">Acesso restrito</h1>
           <p class="font-body-md text-on-surface-variant">Esta área é exclusiva do operador da plataforma. Use o menu para voltar às suas oportunidades.</p>
           <a href="/ui/dashboard.html" class="self-start mt-2 px-4 py-2 rounded bg-secondary text-on-secondary font-label-md font-semibold hover:opacity-90">Ir para o painel</a>
         </div>`
      : main ? main.outerHTML : "";

    root.innerHTML = `
<div id="la-overlay" class="hidden fixed inset-0 bg-on-surface/40 z-40 lg:hidden" aria-hidden="true"></div>
<aside id="la-sidebar" aria-label="Menu principal" class="fixed left-0 top-0 h-full w-72 max-w-[85vw] bg-surface-container-lowest border-r border-surface-container z-50 flex flex-col justify-between overflow-y-auto -translate-x-full lg:translate-x-0 transition-transform motion-reduce:transition-none">
  <div class="flex flex-col">
    <div class="h-16 px-space-md flex items-center justify-between gap-2 bg-surface-container-low">
      <div class="flex items-center gap-2 min-w-0">
        <img alt="LicitAll" class="h-9 w-9 shrink-0 object-contain" src="/ui/assets/logo.svg">
        <div class="flex flex-col min-w-0">
          <span class="font-headline-sm text-headline-sm text-on-surface tracking-tight leading-none truncate">LicitAll</span>
          <span class="font-label-sm text-label-sm text-on-surface-variant leading-none mt-1 truncate">GovTech B2G</span>
        </div>
      </div>
      <span class="shrink-0 font-label-sm text-[10px] leading-none px-1.5 py-1 rounded bg-surface-container-high text-on-surface-variant font-semibold whitespace-nowrap">v1.4</span>
    </div>
    <nav class="flex flex-col px-space-sm py-space-sm gap-space-md">${navHtml(active, isAdmin)}</nav>
  </div>
  <div class="p-space-sm bg-surface-container-low flex flex-col gap-2 mt-4">
    <div data-admin-only class="flex items-center justify-between">
      <span class="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant font-bold">Live Health</span>
      <span class="flex h-2 w-2 relative">
        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-tertiary-fixed-dim opacity-75"></span>
        <span class="relative inline-flex rounded-full h-2 w-2 bg-on-tertiary-container"></span>
      </span>
    </div>
    <div id="la-health" data-admin-only class="grid grid-cols-2 gap-1 font-data-mono text-[11px]">
      <div class="flex items-center gap-1.5 text-on-surface"><span class="h-1.5 w-1.5 rounded-full bg-outline"></span>API</div>
      <div class="flex items-center gap-1.5 text-on-surface"><span class="h-1.5 w-1.5 rounded-full bg-outline"></span>Redis</div>
      <div class="flex items-center gap-1.5 text-on-surface"><span class="h-1.5 w-1.5 rounded-full bg-outline"></span>Receita</div>
      <div class="flex items-center gap-1.5 text-on-surface"><span class="h-1.5 w-1.5 rounded-full bg-outline"></span>Evolution</div>
    </div>
    <div class="pt-2 text-center">
      <p class="font-label-sm text-[10px] text-outline leading-tight">Lei 14.133/2021 | OAB 8.906/1994<br>Compliance Institucional Ativo</p>
    </div>
    <button id="la-logout" type="button" class="mt-1 w-full py-1.5 rounded bg-surface-container text-on-surface font-label-sm text-label-sm hover:bg-surface-container-high">Sair</button>
  </div>
</aside>
<div class="lg:pl-72 flex flex-col min-h-screen">
  <header class="fixed top-0 left-0 lg:left-72 right-0 h-16 bg-surface-container-lowest/90 backdrop-blur-md border-b border-surface-container z-30 flex items-center justify-between gap-2 px-gutter lg:px-space-lg">
    <div class="flex items-center gap-2 lg:gap-space-lg flex-1 min-w-0 max-w-2xl">
      <button id="la-menu-btn" type="button" aria-label="Abrir menu" aria-controls="la-sidebar" aria-expanded="false" class="lg:hidden shrink-0 p-2 rounded text-on-surface hover:bg-surface-container">
        <span class="material-symbols-outlined text-[24px]" aria-hidden="true">menu</span>
      </button>
      <div class="relative w-full min-w-0 flex items-center">
        <span class="material-symbols-outlined absolute left-3 text-outline text-[18px]" aria-hidden="true">search</span>
        <input id="la-global-search" name="q" type="search" autocomplete="off" aria-label="Buscar editais por ID PNCP, órgão ou objeto" class="w-full bg-surface-container-low pl-10 pr-4 sm:pr-20 py-2 rounded text-on-surface placeholder:text-outline font-body-sm text-body-sm focus:outline-none focus:bg-surface-container-lowest focus:ring-2 focus:ring-secondary shadow-sm transition-colors" placeholder="Buscar ID PNCP, órgão ou objeto…">
        <kbd class="hidden sm:inline absolute right-3 px-1.5 py-0.5 rounded bg-surface-container-high text-on-surface font-data-mono text-[11px]">Ctrl + K</kbd>
      </div>
      <div data-admin-only class="hidden xl:flex items-center gap-2 px-space-sm py-1.5 rounded bg-surface-container-low whitespace-nowrap">
        <span class="material-symbols-outlined text-[16px] text-secondary">sync</span>
        <span class="font-label-sm text-label-sm text-on-surface font-medium">Fonte: <strong class="font-semibold">PNCP</strong></span>
      </div>
    </div>
    <div class="flex items-center gap-space-md">
      <div data-admin-only class="hidden md:flex items-center gap-2">
        <a href="/ui/monitor-pncp.html" class="flex items-center gap-1.5 px-3 py-1.5 rounded bg-secondary text-on-secondary hover:bg-secondary-container hover:text-on-secondary-container transition-colors font-label-sm text-label-sm font-semibold">
          <span class="material-symbols-outlined text-[16px]" aria-hidden="true">add</span>Capturar editais
        </a>
        <button id="la-test-deps" class="flex items-center gap-1.5 px-3 py-1.5 rounded bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors font-label-sm text-label-sm font-medium" type="button">
          <span class="material-symbols-outlined text-[16px]" aria-hidden="true">cable</span>Verificar serviços
        </button>
      </div>
      <div class="relative flex items-center">
        <button class="p-2 rounded text-on-surface-variant hover:bg-surface-container hover:text-on-surface transition-colors relative" type="button" aria-label="Notificações" title="Notificações">
          <span class="material-symbols-outlined text-[20px]" aria-hidden="true">notifications</span>
        </button>
      </div>
      <div class="flex items-center gap-space-sm pl-2">
        <div class="relative">
          <div class="w-8 h-8 rounded-full bg-secondary-container text-on-secondary-container flex items-center justify-center font-label-sm font-bold">${esc((session.nome || "U").slice(0, 1).toUpperCase())}</div>
          <span class="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full bg-on-tertiary-container ring-2 ring-surface-container-lowest"></span>
        </div>
        <div class="flex flex-col text-left hidden sm:flex">
          <div class="flex items-center gap-1.5">
            <span class="font-label-lg text-label-lg font-bold text-on-surface leading-tight">${esc(session.nome || "Usuário")}</span>
          </div>
          <span class="font-label-sm text-label-sm text-on-surface-variant leading-tight">${esc((session.empresa || {}).nome || "")}</span>
        </div>
      </div>
    </div>
  </header>
  <main class="w-full pt-16 bg-background flex-1 px-gutter lg:px-gutter-desktop py-space-lg">${mainHtml}</main>
</div>`;

    document.getElementById("la-logout")?.addEventListener("click", async () => {
      await global.LicitAllAuth.logout();
      location.href = "/ui/login.html";
    });

    if (!isAdmin) document.querySelectorAll("[data-admin-only]").forEach((el) => el.remove());

    document.getElementById("la-test-deps")?.addEventListener("click", () => refreshHealth(true));

    const sidebar = document.getElementById("la-sidebar");
    const overlay = document.getElementById("la-overlay");
    const menuBtn = document.getElementById("la-menu-btn");
    function setMenu(open) {
      sidebar.classList.toggle("-translate-x-full", !open);
      overlay.classList.toggle("hidden", !open);
      menuBtn.setAttribute("aria-expanded", String(open));
      menuBtn.setAttribute("aria-label", open ? "Fechar menu" : "Abrir menu");
      if (open) sidebar.querySelector("a")?.focus();
    }
    menuBtn?.addEventListener("click", () => setMenu(sidebar.classList.contains("-translate-x-full")));
    overlay?.addEventListener("click", () => setMenu(false));
    sidebar?.addEventListener("click", (ev) => { if (ev.target.closest("a")) setMenu(false); });
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape" && !sidebar.classList.contains("-translate-x-full") && window.matchMedia("(max-width: 1023px)").matches) {
        setMenu(false);
        menuBtn.focus();
      }
    });
    document.getElementById("la-global-search")?.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        const q = ev.target.value.trim();
        if (q) location.href = "/ui/editais.html?q=" + encodeURIComponent(q);
      }
    });

    document.addEventListener("keydown", (ev) => {
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k") {
        ev.preventDefault();
        document.getElementById("la-global-search")?.focus();
      }
    });

    if (isAdmin) refreshHealth(false);
    if (!restricted && typeof opts.onReady === "function") opts.onReady();
  }

    async function refreshHealth(alertOnFail) {
    const box = document.getElementById("la-health");
    if (!box) return;
    try {
      const res = await fetch("/health/deps");
      const data = await res.json();
      const services = data.services || [];
      const byName = Object.fromEntries(
        services.map((s) => [String(s.service || "").toLowerCase(), s.status === "up"])
      );
      // aliases
      if (byName.evolution_api !== undefined) byName.evolution = byName.evolution_api;
      const map = [
        ["API", true],
        ["Postgres", Boolean(byName.postgres)],
        ["Redis", Boolean(byName.redis)],
        ["Receita", Boolean(byName.minha_receita)],
        ["Evolution", Boolean(byName.evolution)],
      ];
      box.innerHTML = map
        .map(
          ([label, ok]) =>
            `<div class="flex items-center gap-1.5 text-on-surface"><span class="h-1.5 w-1.5 rounded-full ${ok ? "bg-on-tertiary-container" : "bg-error"}"></span>${label}</div>`
        )
        .join("");
      if (alertOnFail && map.some(([, ok]) => !ok)) {
        alert("Algumas dependências estão indisponíveis. Veja o Live Health na sidebar.");
      }
    } catch {
      box.innerHTML = `<div class="col-span-2 text-error">Health indisponível</div>`;
      if (alertOnFail) alert("Não foi possível consultar /health/deps");
    }
  }

  global.LicitAllShell = { mount, NAV };
})(window);
