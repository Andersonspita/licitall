# syntax=docker/dockerfile:1
# API do LicitAll. Build: docker compose --profile app build api
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Docling (OCR) é opcional e pesado (puxa torch, GBs). Sem ele o parser usa o texto do PDF (pypdfium2).
# Para incluir: docker compose build --build-arg INSTALL_DOCLING=true api
# requirements.lock fixa todas as versões (inclusive indiretas): a imagem não muda sozinha com uma biblioteca nova.
ARG INSTALL_DOCLING=false
COPY requirements.txt requirements.lock ./
RUN if [ "$INSTALL_DOCLING" = "true" ]; then pip install -r requirements.txt -c requirements.lock; \
    else grep -viE '^docling' requirements.txt > /tmp/requirements.txt && pip install -r /tmp/requirements.txt -c requirements.lock; fi

COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src
COPY scripts ./scripts
COPY app ./app
COPY docker/api-entrypoint.sh /usr/local/bin/api-entrypoint.sh

# Usuário sem privilégios; só /app/data (documentos baixados) é gravável.
RUN useradd --system --uid 10001 --home-dir /app/data licitall \
    && mkdir -p /app/data/raw \
    && chown -R licitall /app/data \
    && chmod 0555 /usr/local/bin/api-entrypoint.sh
USER licitall

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

ENTRYPOINT ["api-entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
