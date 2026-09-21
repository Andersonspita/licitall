# Fase 5 — Peças (advisory) e WhatsApp (outreach)

## Objetivo

Gerar **minutas** de participação e alertas WhatsApp, sempre com:

- Marco **Lei 14.133/2021** (Art. 164 para esclarecimento/impugnação)
- Disclaimer **Lei 8.906/1994** (OAB) — revisão humana obrigatória
- Sem inventar vícios ou certidões ausentes do edital

## Minutas do kit

| Arquivo | Conteúdo |
|---------|----------|
| `proposta.md` | Proposta de preços (placeholders de valor) |
| `esclarecimento.md` | Pedido de esclarecimento (Art. 164) |
| `impugnacao.md` | Impugnação com riscos **já detectados** ou estrutura vazia explícita |
| `declaracao.md` | Não emprego de menores, ME/EPP (LC 123), ciência do edital |

Persistência: `data/raw/{slug}/_kit/`.

## Endpoints

- `POST /advisory/generate` — kit a partir de `tender` JSON  
- `POST /advisory/{id_pncp}/kit` — extrai + gera kit  
- `POST /outreach/whatsapp/preview` — monta mensagem de 1 oportunidade sem enviar  
- `POST /outreach/whatsapp/opportunity` — envia 1 oportunidade via Evolution API  
- `POST /outreach/whatsapp/digest/preview` — monta digest top-N sem enviar  
- `POST /outreach/whatsapp/digest` — envia digest top-N  
- `POST /outreach/whatsapp/digest/from-company` — match inverso + digest (preview ou `send: true`)

### Digest (top-N)

Body exemplo:

```json
{
  "phone": "5511999999999",
  "company_name": "LIMPEZA ME LTDA",
  "cnpj": "12345678000199",
  "top_n": 5,
  "opportunities": [
    {
      "id_pncp": "00000000000000-1-000001/2026",
      "orgao": "PREFEITURA X",
      "objeto": "Serviços de limpeza",
      "valor_total": 45000,
      "score": 88,
      "recommendation": "BID",
      "uf": "SP"
    }
  ]
}
```

A mensagem lista BID/REVIEW, score e PNCP, com rodapé Lei 14.133 + Lei 8.906.
## Evolution

Config: `EVOLUTION_API_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE` no `.env`.  
É necessário ter a instância criada/conectada no Evolution Manager (QR).

## Compliance

- Impugnação só lista cláusulas vindas da triagem/RAG; se vazia, avisa para não inventar.  
- Toda peça termina com o disclaimer OAB (`DISCLAIMER_OAB`).
