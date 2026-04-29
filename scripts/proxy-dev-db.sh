#!/usr/bin/env bash
# Levanta el proxy local hacia trufiq-db-dev en Fly.io
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

# Lee una clave puntual de .env sin evaluar todo el archivo.
# Esto evita errores cuando hay valores con espacios (p.ej. tokens largos).
get_env_value() {
	local key="$1"
	local value=""

	if [ ! -f .env ]; then
		return 1
	fi

	value="$(awk -v key="$key" '
		$0 ~ "^(export[[:space:]]+)?" key "=" {
			sub(/^[^=]*=/, "", $0)
			print $0
			found=1
		}
		END {
			if (!found) exit 1
		}
	' .env 2>/dev/null || true)"

	if [ -z "$value" ]; then
		return 1
	fi

	# Quita comillas envolventes simples o dobles, si existen.
	if [[ "$value" =~ ^\".*\"$ ]]; then
		value="${value:1:${#value}-2}"
	elif [[ "$value" =~ ^\'.*\'$ ]]; then
		value="${value:1:${#value}-2}"
	fi

	printf '%s' "$value"
}

DB_PASSWORD="${TRUFIQ_DB_DEV_PASSWORD:-}"

if [ -z "$DB_PASSWORD" ]; then
	DB_PASSWORD="$(get_env_value "TRUFIQ_DB_DEV_PASSWORD" || true)"
fi

if [ -z "$DB_PASSWORD" ]; then
	echo "TRUFIQ_DB_DEV_PASSWORD no definida; intentando obtenerla desde Fly..."
	DB_PASSWORD="$(flyctl postgres credentials --app trufiq-db-dev 2>/dev/null | awk '/Password:/ {print $2; exit}')"
fi

if [ -z "$DB_PASSWORD" ]; then
	echo "No se pudo obtener la password."
	echo "Define TRUFIQ_DB_DEV_PASSWORD en .env o ejecuta flyctl postgres credentials --app trufiq-db-dev"
	exit 1
fi

echo "Iniciando proxy → trufiq-db-dev (localhost:5434)"
echo "Conecta tu cliente a: postgresql://postgres:${DB_PASSWORD}@localhost:5434/trufiq_dev"
echo "Ctrl+C para cerrar el proxy"
echo ""

flyctl proxy 5434:5432 --app trufiq-db-dev
