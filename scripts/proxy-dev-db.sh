#!/usr/bin/env bash
# Levanta el proxy local hacia truficultura-db-dev en Fly.io
# Puerto local 5434 (5432 = Postgres local, 5433 = docker-compose)
#
# Parámetros de conexión (úsalos en tu cliente SQL):
#   Host:     localhost
#   Port:     5434
#   Database: trufiq_dev
#   User:     postgres
#   Password: variable local TRUFIQ_DB_DEV_PASSWORD
#   URL:      postgresql://postgres:<password>@localhost:5434/trufiq_dev

set -euo pipefail

# Carga variables locales no versionadas si existen.
if [ -f .env ]; then
	# shellcheck disable=SC1091
	source .env
fi

# Compatibilidad temporal con el nombre antiguo de variable local.
DB_PASSWORD="${TRUFIQ_DB_DEV_PASSWORD:-${TRUFICULTURA_DB_DEV_PASSWORD:-}}"

if [ -z "$DB_PASSWORD" ]; then
	echo "TRUFIQ_DB_DEV_PASSWORD no definida; intentando obtenerla desde Fly..."
	DB_PASSWORD="$(flyctl postgres credentials --app truficultura-db-dev 2>/dev/null | awk '/Password:/ {print $2; exit}')"
fi

if [ -z "$DB_PASSWORD" ]; then
	echo "No se pudo obtener la password."
	echo "Define TRUFIQ_DB_DEV_PASSWORD en .env o ejecuta flyctl postgres credentials --app truficultura-db-dev"
	exit 1
fi

echo "Iniciando proxy → truficultura-db-dev (localhost:5434)"
echo "Conecta tu cliente a: postgresql://postgres:${DB_PASSWORD}@localhost:5434/trufiq_dev"
echo "Ctrl+C para cerrar el proxy"
echo ""

flyctl proxy 5434:5432 --app truficultura-db-dev
