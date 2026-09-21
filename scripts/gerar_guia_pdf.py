"""Gera PDF do guia do usuário LicitAll (funcionalidades + como usar)."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


OUT = Path(__file__).resolve().parents[1] / "docs" / "usuario" / "LicitAll_Guia_Usuario.pdf"


def styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleBR",
            parent=base["Title"],
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "h1": ParagraphStyle("H1BR", parent=base["Heading1"], fontSize=13, leading=16, spaceBefore=14, spaceAfter=6),
        "h2": ParagraphStyle("H2BR", parent=base["Heading2"], fontSize=11, leading=14, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle(
            "BodyBR",
            parent=base["Normal"],
            fontSize=9.5,
            leading=13,
            alignment=TA_JUSTIFY,
            spaceAfter=4,
        ),
        "mono": ParagraphStyle("MonoBR", parent=base["Code"], fontSize=8, leading=11, spaceAfter=4),
        "small": ParagraphStyle("SmallBR", parent=base["Normal"], fontSize=8, leading=10, textColor="#444444"),
    }


def bullets(items: list[str], sty) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(i, sty), leftIndent=8, bulletColor="#0051d5") for i in items],
        bulletType="bullet",
        start="•",
        leftIndent=12,
        spaceAfter=6,
    )


def build() -> Path:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    s = styles()
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        title="LicitAll — Guia do Usuário",
        author="LicitAll",
    )
    story = []

    story.append(Paragraph("LicitAll — Guia do Usuário", s["title"]))
    story.append(Paragraph("Plataforma B2G · Governo · Licitações (Lei 14.133/2021)", s["small"]))
    story.append(Paragraph("Como usar todas as funcionalidades com dados reais do PNCP", s["body"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("1. O que o sistema faz", s["h1"]))
    story.append(
        Paragraph(
            "O LicitAll automatiza o ciclo pré-certame: minera publicações no PNCP, baixa editais/TRs, "
            "converte PDFs em texto (Docling), extrai requisitos com agentes (LangGraph), consulta RAG da "
            "Lei 14.133/TCU, ranqueia empresas (Minha Receita), gera minutas com disclaimer OAB e prepara "
            "alertas WhatsApp (Evolution API).",
            s["body"],
        )
    )

    story.append(Paragraph("2. Acesso e login", s["h1"]))
    story.append(
        bullets(
            [
                "Suba dependências: <b>docker compose up -d</b> (Postgres 5433, Redis 6380, Evolution 8081).",
                "API: <b>uvicorn src.main:app --reload --port 8000</b>.",
                "Abra <b>http://127.0.0.1:8000/</b> → login em /ui/login.html.",
                "Credencial local de demo: <b>admin@licitall.local</b> / <b>licitall</b> (ou qualquer e-mail + senha ≥ 6).",
                "Documentação OpenAPI: <b>http://127.0.0.1:8000/docs</b>.",
            ],
            s["body"],
        )
    )

    story.append(Paragraph("3. Fluxo operacional do dia a dia", s["h1"]))
    story.append(
        bullets(
            [
                "<b>Monitor PNCP</b> — sincroniza publicações (POST /ingestion/pncp/sync). Escolha UF e datas.",
                "<b>Editais &amp; TRs</b> — lista real de <b>tender_ingest</b> (GET /tenders). Filtre por UF, status e texto.",
                "<b>Dashboard</b> — KPIs reais (GET /tenders/stats): volume, status, prazos Art. 164.",
                "<b>Baixar documentos</b> — POST /ingestion/pncp/{id}/documents → pasta data/raw/.",
                "<b>Parser Docling</b> — POST /parser/{id} → Markdown segmentado.",
                "<b>Extract / Graph</b> — POST /agents/{id}/extract ou /graph (checklist + riscos).",
                "<b>RAG Lei 14.133</b> — indexar uma vez (POST /rag/index/lei-14133) e buscar (GET /rag/search).",
                "<b>Matchmaking</b> — POST /matching/{id} ou /matching/company (CNPJ → oportunidades).",
                "<b>Peças &amp; Minutas</b> — abra com ?id= e gere kit (POST /advisory/{id}/kit). Revisão OAB obrigatória.",
                "<b>WhatsApp</b> — preview digest (POST /outreach/whatsapp/digest/preview) com editais reais.",
            ],
            s["body"],
        )
    )

    story.append(Paragraph("4. Telas da interface (/ui)", s["h1"]))
    story.append(
        bullets(
            [
                "<b>Dashboard Geral</b> — visão consolidada e sync rápido.",
                "<b>Monitor PNCP</b> — mineração parametrizada.",
                "<b>Editais &amp; TRs</b> — catálogo filtrável (fonte Postgres).",
                "<b>Explorador &amp; Análise</b> — detalhe do edital (?id=), docs locais, extract, RAG.",
                "<b>Pipeline LangGraph</b> — mapa do fluxo de agentes.",
                "<b>Parser &amp; Docling</b> — disparo manual de parse.",
                "<b>RAG Lei 14.133</b> — consulta ao corpus jurídico.",
                "<b>Matchmaking B2G</b> — score BID/REVIEW/SKIP (CNAE, geo, porte, Art. 164, LC 123).",
                "<b>Peças &amp; Minutas</b> — hub jurídico com disclaimer Lei 8.906/1994.",
                "<b>Disparos WhatsApp</b> — preview Evolution (sem inventar oportunidades).",
                "<b>Logs / Config</b> — health das dependências.",
            ],
            s["body"],
        )
    )

    story.append(Paragraph("5. APIs de listagem (dados reais)", s["h1"]))
    story.append(Paragraph("<b>GET /tenders</b> — query: uf, status, q, limit, offset", s["mono"]))
    story.append(Paragraph("<b>GET /tenders/stats</b> — totais, volume, por UF/status, prazos Art. 164", s["mono"]))
    story.append(Paragraph("<b>GET /tenders/{id_pncp}</b> — detalhe + arquivos em data/raw", s["mono"]))
    story.append(
        Paragraph(
            "Sem sync recente a lista fica vazia — isso é esperado. Não há mais dados de demonstração inventados nas telas principais.",
            s["body"],
        )
    )

    story.append(PageBreak())
    story.append(Paragraph("6. Compliance (não negociável)", s["h1"]))
    story.append(
        bullets(
            [
                "Marco: <b>Lei Federal nº 14.133/2021</b> (não usar Lei 8.666 como base do motor).",
                "ME/EPP: <b>LC 123/2006</b> (exclusividade / cota).",
                "Impugnação: <b>Art. 164</b> — até 3 dias <b>úteis</b> antes da abertura.",
                "Nunca inventar certidões, prazos ou vícios ausentes do edital; citar página/parágrafo quando houver parse.",
                "Toda minuta leva rodapé OAB (<b>Lei 8.906/1994</b>) — revisão humana obrigatória.",
            ],
            s["body"],
        )
    )

    story.append(Paragraph("7. Troubleshooting rápido", s["h1"]))
    story.append(
        bullets(
            [
                "Lista vazia → rode sync no Monitor PNCP e confira /health/deps (Postgres up).",
                "Parse falha → baixe documents antes; verifique Docling em /health.",
                "Match vazio → Minha Receita precisa de base populada.",
                "WhatsApp sem envio → conecte QR no Evolution Manager; use preview primeiro.",
                "Smoke: <b>python scripts/smoke_local.py --api http://127.0.0.1:8000</b>.",
            ],
            s["body"],
        )
    )

    story.append(Spacer(1, 16))
    story.append(
        Paragraph(
            "Documento gerado automaticamente pelo LicitAll · Fase 6 integração operacional · "
            "Atualize sempre que novas telas/APIs forem publicadas.",
            s["small"],
        )
    )

    doc.build(story)
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"PDF gerado: {path}")
