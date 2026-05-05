# ---------------------------------------------------------------------------
# Stage 1: builder — instala dependencias con herramientas de compilación
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
# Install into a prefix so we can copy cleanly to the runtime stage
RUN pip install --upgrade pip \
    && pip install --prefix=/install .

# ---------------------------------------------------------------------------
# Stage 2: runtime — imagen final mínima sin herramientas de build (F-12)
# ---------------------------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY locales ./locales
COPY scripts ./scripts
COPY docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

# Run as non-root for security (F-07)
RUN useradd --system --no-create-home appuser \
    && chown -R appuser:appuser /app /entrypoint.sh
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

ENTRYPOINT ["/entrypoint.sh"]