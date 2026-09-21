/** Cliente HTTP da API LicitAll (dados reais). */
(function (global) {
  function qs(params) {
    const sp = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && String(v).trim() !== "") sp.set(k, String(v));
    });
    const s = sp.toString();
    return s ? "?" + s : "";
  }

  async function json(url, options) {
    const res = await fetch(url, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail || data.message || res.statusText || "erro";
      const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function formatBRL(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    const n = Number(value);
    if (n >= 1_000_000) return "R$ " + (n / 1_000_000).toFixed(1).replace(".", ",") + " Mi";
    if (n >= 1_000) return "R$ " + (n / 1_000).toFixed(1).replace(".", ",") + " mil";
    return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function art164Label(art) {
    if (!art || !art.tem_abertura) return { text: "—", critical: false, className: "bg-surface-container text-outline" };
    const d = art.dias_uteis_restantes;
    if (art.vencido || d <= 0) {
      return { text: "Vencido", critical: true, className: "bg-error-container text-on-error-container font-bold" };
    }
    const critical = Boolean(art.critico);
    return {
      text: d + "d úteis",
      critical,
      className: critical
        ? "bg-error-container text-on-error-container font-bold"
        : "bg-surface-container text-on-surface-variant",
    };
  }

  const Api = {
    qs,
    json,
    formatBRL,
    art164Label,
    listTenders(params) {
      return json("/tenders" + qs(params));
    },
    getTender(id) {
      return json("/tenders/" + String(id || "").replace(/^\/+/, ""));
    },
    stats() {
      return json("/tenders/stats");
    },
    syncPncp(body, options) {
      const opts = options || {};
      const controller = new AbortController();
      const ms = opts.timeoutMs || 75000;
      const timer = setTimeout(() => controller.abort(), ms);
      return json("/ingestion/pncp/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || { only_open: true }),
        signal: controller.signal,
      }).finally(() => clearTimeout(timer));
    },
    async syncPncpAsync(body, options) {
      const opts = options || {};
      const pollMs = opts.pollMs || 2000;
      const maxWaitMs = opts.maxWaitMs || 3600000; // até 1h (Brasil × UFs)
      const onProgress = typeof opts.onProgress === "function" ? opts.onProgress : null;
      const payload = Object.assign({ uf: "BR", only_open: true }, body || {});
      const start = await json("/ingestion/pncp/sync/async", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const jobId = start.job_id;
      const pollUrl = start.poll_url || ("/ingestion/pncp/sync/jobs/" + jobId);
      const t0 = Date.now();
      while (Date.now() - t0 < maxWaitMs) {
        const job = await json(pollUrl);
        if (onProgress) await onProgress(job);
        if (["succeeded", "partial", "failed"].includes(job.status)) return job;
        await new Promise((r) => setTimeout(r, pollMs));
      }
      const err = new Error("Tempo esgotado aguardando job PNCP Brasil");
      err.job_id = jobId;
      throw err;
    },
    healthDeps() {
      return json("/health/deps");
    },
  };

  global.LicitAllApi = Api;
})(window);
