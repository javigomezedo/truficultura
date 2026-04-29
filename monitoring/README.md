# Monitorizacion y alertas (stack externo)

Este directorio documenta el enfoque recomendado para Truficultura cuando el Grafana gestionado por Fly no permite administrar alertas.

Resumen de arquitectura recomendada:

- Fly como runtime de aplicacion y fuente de metricas (Prometheus API).
- Grafana externo (por ejemplo Grafana Cloud) para dashboards, reglas y notificaciones.
- Opcional: Sentry para trazas de excepcion y contexto de errores.

Documento principal:

- `monitoring/external-observability-plan.md`
- `monitoring/truficultura-overview-dashboard.json`

Estado:

- DEV ya validado con alertas reales y notificacion por email.
- El siguiente hito es crear STAGING y despues promover la configuracion a PROD con canales y umbrales adaptados.

Nota de fase actual:

- El dashboard de DEV queda congelado como baseline operativo.
- No se aplicaran cambios de promocion a STAGING/PROD hasta que se habilite STAGING.

Diseno recomendado:

- Un unico Grafana externo.
- Un datasource por entorno: DEV, STAGING y PROD.
- Carpetas y reglas separadas por entorno.
- Canales de notificacion distintos segun entorno y severidad.

Dashboard base disponible:

- `monitoring/truficultura-overview-dashboard.json`
- Pensado para importar primero en DEV.
- Reutilizable en STAGING y PROD cambiando datasource y app.

Uso recomendado:

- Importar el JSON en Grafana Cloud.
- Seleccionar `Fly Prometheus DEV` como datasource inicial.
- Mantener `truficultura-dev` como valor de `app` en DEV.
- Duplicar o reimportar el mismo dashboard para STAGING y PROD cambiando:
	- datasource a `Fly Prometheus STAGING` o `Fly Prometheus PROD`
	- `app` a `truficultura-staging` o `truficultura-prod`
	- folder a `Truficultura / STAGING` o `Truficultura / PROD`

Comprobaciones base en Fly:

- `fly status --app truficultura-dev`
- `fly checks list --app truficultura-dev`
- `curl -sS https://truficultura-dev.fly.dev/metrics | head`
