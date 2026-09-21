# Interface web (Fase 6+)

UI estática em `app/web/`, servida pelo FastAPI em **`/ui`**.

## Acesso

1. `uvicorn src.main:app --reload --port 8000`
2. Abrir http://localhost:8000/ → redireciona para `/ui/login.html`
3. Demo: `admin@licitall.local` / `licitall`

## Telas

| Rota | Função | Dados |
|------|--------|-------|
| `/ui/login.html` | Login (sessionStorage local) | — |
| `/ui/dashboard.html` | Dashboard operacional | `GET /tenders` + `/tenders/stats` |
| `/ui/monitor-pncp.html` | Sync PNCP Brasil | `POST /ingestion/pncp/sync/async` (`uf=BR`) |
| `/ui/editais.html` | Lista / filtros UF·status·busca | `GET /tenders` |
| `/ui/edital.html?id=` | Explorador & análise | `GET /tenders/{id}` |
| `/ui/matchmaking.html` | Match BID/REVIEW/SKIP | `POST /matching/*` |
| `/ui/pecas.html?id=` | Hub de minutas + OAB | `POST /advisory/{id}/kit` |
| `/ui/whatsapp.html` | Digest Evolution | editais reais + preview |
| `/ui/rag.html` | Busca corpus Lei 14.133 | `GET /rag/search` |
| `/ui/pipeline.html` | Mapa LangGraph | docs |
| `/ui/logs.html` / `/ui/config.html` | Health e config | `/health*` |

Guia PDF: `docs/usuario/LicitAll_Guia_Usuario.pdf` (script `scripts/gerar_guia_pdf.py`).

Shell compartilhado: `assets/shell.js` + `assets/api.js`.

## Auth

Protótipo local (`assets/auth.js`). Qualquer e-mail com senha ≥ 6 caracteres também entra; o par demo pré-preenche o formulário. Substituir por JWT/sessão real antes de produção.

## Compliance

Rodapé e banners reforçam Lei 14.133/2021 e Lei 8.906/1994 (minutas = suporte de IA, revisão humana).
