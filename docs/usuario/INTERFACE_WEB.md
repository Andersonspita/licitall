# Interface web (Fase 6+)

UI estática em `app/web/`, servida pelo FastAPI em **`/ui`**.

## Acesso

1. `uvicorn src.main:app --reload --port 8000`
2. Abrir http://localhost:8000/ → redireciona para `/ui/login.html`
3. Crie a conta da empresa em `/ui/cadastro.html` (ou peça ao administrador: `python -m scripts.criar_usuario --email ... --nome ... --empresa ...`) e entre com e-mail e senha (mín. 8 caracteres)

## Telas

| Rota | Função | Dados |
|------|--------|-------|
| `/ui/login.html` | Login (sessionStorage local) | — |
| `/ui/dashboard.html` | Dashboard operacional | `GET /tenders` + `/tenders/stats` |
| `/ui/monitor-pncp.html` | Sync PNCP Brasil | `POST /ingestion/pncp/sync/async` (`uf=BR`) |
| `/ui/editais.html` | Lista / filtros UF·status·busca | `GET /tenders` |
| `/ui/edital.html?id=` | Explorador & análise | `GET /tenders/{id}` |
| `/ui/perfis.html` | **Aderência ao perfil**: cadastro de perfis (UFs, faixa de valor, palavras, CATMAT/CATSER), teste com um edital e prévia do digest | `/matching/profiles*` |
| `/ui/matchmaking.html` | Match por CNPJ (BID/REVIEW/SKIP) | `POST /matching/*` |
| `/ui/certidoes.html` · `/ui/atestados.html` · `/ui/simulador.html` | Validade de certidões, banco de atestados e simulador de margem/lance | certidões e atestados salvos na conta da empresa |
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

## Perfis de aderência

O perfil é gravado na API (`/matching/profiles`) e pertence à **empresa** do usuário logado; outras empresas não o enxergam. Sem estados marcados, vale para o Brasil inteiro. Cada perfil precisa de ao menos palavras de interesse, um código CATMAT ou uma descrição. Para testar, escolha um edital já capturado; se ele não tiver itens, a tela oferece buscá-los no PNCP.

## Perfis de exemplo

Para começar com dois perfis prontos (Equipamentos de Informática e Mobiliário Escolar), rode na raiz do projeto: `python -m scripts.seed_perfis_exemplo --email EMAIL_DE_UM_USUARIO` (os perfis vão para a empresa dele; opções: `--ufs BA,SE,AL`, `--remover`). Pode rodar mais de uma vez sem duplicar. Os perfis não trazem códigos CATMAT; cadastre os reais na tela.
