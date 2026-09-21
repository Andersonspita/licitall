/** Shell compartilhado: sidebar + topbar do design system LicitAll. */
(function (global) {
  const NAV = [
    {
      group: "1. Operacional",
      items: [
        { id: "dashboard-geral", href: "/ui/dashboard.html", label: "Dashboard Geral", icon: "dashboard" },
        { id: "monitor-pncp", href: "/ui/monitor-pncp.html", label: "Monitor PNCP", icon: "radar", note: "Sync" },
        { id: "editais-e-trs", href: "/ui/editais.html", label: "Editais & TRs", icon: "gavel", note: "PNCP" },
      ],
    },
    {
      group: "2. Inteligência IA",
      items: [
        { id: "explorador-analise-edital", href: "/ui/edital.html", label: "Explorador & Análise", icon: "document_scanner" },
        { id: "pipeline-langgraph", href: "/ui/pipeline.html", label: "Pipeline LangGraph", icon: "account_tree", note: "Grafo" },
        { id: "parser-docling", href: "/ui/parser.html", label: "Parser & Docling", icon: "document_scanner", note: "OCR/MD" },
        { id: "rag-lei-14133", href: "/ui/rag.html", label: "RAG Lei 14.133", icon: "menu_book", badge: "Jurisprudência", badgeClass: "bg-surface-container text-on-surface" },
      ],
    },
    {
      group: "3. Negócios & Outreach",
      items: [
        { id: "matchmaking-b2g", href: "/ui/matchmaking.html", label: "Matchmaking B2G", icon: "handshake", note: "CNAE/Porte" },
        { id: "pecas-minutas", href: "/ui/pecas.html", label: "Peças & Minutas", icon: "policy", note: "OAB Compliant" },
        { id: "disparos-whatsapp", href: "/ui/whatsapp.html", label: "Disparos WhatsApp", icon: "chat", note: "Evolution" },
      ],
    },
    {
      group: "4. Sistema & DevOps",
      items: [
        { id: "logs-microservicos", href: "/ui/logs.html", label: "Logs & Microserviços", icon: "terminal" },
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

  function navHtml(active) {
    return NAV.map((group) => {
      const links = group.items
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

  function mount(options) {
    const opts = options || {};
    const active = opts.active || "dashboard-geral";
    if (!global.LicitAllAuth || !global.LicitAllAuth.requireAuth("/ui/login.html")) return;

    const session = global.LicitAllAuth.getSession() || {};
    const root = document.getElementById("app-root");
    if (!root) return;

    const main = root.querySelector("[data-page]") || root.firstElementChild;
    const mainHtml = main ? main.outerHTML : "";

    root.innerHTML = `
<aside class="fixed left-0 top-0 h-full w-72 bg-surface-container-lowest border-r border-surface-container z-50 flex flex-col justify-between overflow-y-auto">
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
    <nav class="flex flex-col px-space-sm py-space-sm gap-space-md">${navHtml(active)}</nav>
  </div>
  <div class="p-space-sm bg-surface-container-low flex flex-col gap-2 mt-4">
    <div class="flex items-center justify-between">
      <span class="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant font-bold">Live Health</span>
      <span class="flex h-2 w-2 relative">
        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-tertiary-fixed-dim opacity-75"></span>
        <span class="relative inline-flex rounded-full h-2 w-2 bg-on-tertiary-container"></span>
      </span>
    </div>
    <div id="la-health" class="grid grid-cols-2 gap-1 font-data-mono text-[11px]">
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
<div class="pl-72 flex flex-col min-h-screen">
  <header class="fixed top-0 left-72 right-0 h-16 bg-surface-container-lowest/90 backdrop-blur-md border-b border-surface-container z-40 flex items-center justify-between px-space-lg">
    <div class="flex items-center gap-space-lg flex-1 max-w-2xl">
      <div class="relative w-full flex items-center">
        <span class="material-symbols-outlined absolute left-3 text-outline text-[18px]">search</span>
        <input id="la-global-search" class="w-full bg-surface-container-low pl-10 pr-16 py-2 rounded text-on-surface placeholder:text-outline font-body-sm text-body-sm focus:outline-none focus:bg-surface-container-lowest shadow-sm transition-all" placeholder="Buscar por ID PNCP, Órgão, Objeto ou CNAE..." type="text">
        <kbd class="absolute right-3 px-1.5 py-0.5 rounded bg-surface-container-high text-on-surface font-data-mono text-[11px]">Ctrl + K</kbd>
      </div>
      <div class="hidden xl:flex items-center gap-2 px-space-sm py-1.5 rounded bg-surface-container-low whitespace-nowrap">
        <span class="material-symbols-outlined text-[16px] text-secondary">sync</span>
        <span class="font-label-sm text-label-sm text-on-surface font-medium">PNCP Sync: <strong class="font-semibold">ao vivo</strong> · API :8000</span>
      </div>
    </div>
    <div class="flex items-center gap-space-md">
      <div class="flex items-center gap-2">
        <a href="/ui/monitor-pncp.html" class="flex items-center gap-1.5 px-3 py-1.5 rounded bg-secondary text-on-secondary hover:bg-secondary-container hover:text-on-secondary-container transition-all font-label-sm text-label-sm font-semibold">
          <span class="material-symbols-outlined text-[16px]">add</span>Nova Mineração PNCP
        </a>
        <button id="la-test-deps" class="flex items-center gap-1.5 px-3 py-1.5 rounded bg-surface-container text-on-surface hover:bg-surface-container-high transition-all font-label-sm text-label-sm font-medium" type="button">
          <span class="material-symbols-outlined text-[16px]">cable</span>Testar Conexões
        </button>
      </div>
      <div class="relative flex items-center">
        <button class="p-2 rounded text-on-surface-variant hover:bg-surface-container hover:text-on-surface transition-colors relative" type="button" title="Notificações">
          <span class="material-symbols-outlined text-[20px]">notifications</span>
          <span class="absolute top-1 right-1 h-2 w-2 rounded-full bg-error"></span>
        </button>
      </div>
      <div class="flex items-center gap-space-sm pl-2">
        <div class="relative">
          <div class="w-8 h-8 rounded-full bg-secondary-container text-on-secondary-container flex items-center justify-center font-label-sm font-bold">${esc((session.name || "U").slice(0, 1).toUpperCase())}</div>
          <span class="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full bg-on-tertiary-container ring-2 ring-surface-container-lowest"></span>
        </div>
        <div class="flex flex-col text-left hidden sm:flex">
          <div class="flex items-center gap-1.5">
            <span class="font-label-lg text-label-lg font-bold text-on-surface leading-tight">${esc(session.name || "Operador")}</span>
            <span class="font-label-sm text-[10px] px-1 py-0.2 rounded bg-tertiary-fixed text-on-tertiary-fixed font-bold leading-none">ONLINE</span>
          </div>
          <span class="font-label-sm text-label-sm text-on-surface-variant leading-tight">${esc(session.role || "GovOps")}</span>
        </div>
      </div>
    </div>
  </header>
  <main class="w-full pt-16 bg-background flex-1 px-gutter-desktop py-space-lg">${mainHtml}</main>
</div>`;

    document.getElementById("la-logout")?.addEventListener("click", () => {
      global.LicitAllAuth.logout();
      location.href = "/ui/login.html";
    });

    document.getElementById("la-test-deps")?.addEventListener("click", () => refreshHealth(true));
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

    refreshHealth(false);
    if (typeof opts.onReady === "function") opts.onReady();
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
