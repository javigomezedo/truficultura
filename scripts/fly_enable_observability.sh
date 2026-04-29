#!/usr/bin/env bash
set -euo pipefail

APP_NAME="${1:-truficultura-dev}"

if ! command -v fly >/dev/null 2>&1; then
  echo "Error: flyctl no esta instalado o no esta en PATH."
  exit 1
fi

echo "[1/4] Configurando secrets de observabilidad para ${APP_NAME}..."
fly secrets set \
  METRICS_ENABLED=1 \
  LOG_LEVEL=INFO \
  LOG_JSON=1 \
  --app "${APP_NAME}"

echo "[2/4] Eliminando METRICS_TOKEN para permitir scrape gestionado por Fly (si existe)..."
fly secrets unset METRICS_TOKEN --app "${APP_NAME}" || true

echo "[3/4] Desplegando cambios para aplicar fly.toml y checks..."
fly deploy --app "${APP_NAME}"

echo "[4/4] Verificando estado y checks..."
fly status --app "${APP_NAME}"
fly checks list --app "${APP_NAME}"

echo "Listo. Ahora puedes ir a https://fly-metrics.net y filtrar por app=${APP_NAME}."
