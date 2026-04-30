# Monitorizacion y alertas (stack externo)

Este directorio documenta el enfoque recomendado para Trufiq cuando el Grafana gestionado por Fly no permite administrar alertas.

Resumen de arquitectura recomendada:

- Fly como runtime de aplicacion y fuente de metricas (Prometheus API).
- Grafana externo (por ejemplo Grafana Cloud) para dashboards, reglas y notificaciones.
- Sentry como capa de diagnostico de excepciones (issue grouping + stacktrace).
- Fly Logs como apoyo para contexto operativo y trazas no cubiertas por excepciones.

Documento principal:

- `monitoring/external-observability-plan.md`
- `monitoring/trufiq-overview-dashboard.json`

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

- `monitoring/trufiq-overview-dashboard.json`
- Pensado para importar primero en DEV.
- Reutilizable en STAGING y PROD cambiando datasource y app.

Uso recomendado:

- Importar el JSON en Grafana Cloud.
- Seleccionar `Fly Prometheus DEV` como datasource inicial.
- Mantener `trufiq-dev` como valor de `app` en DEV.
- Duplicar o reimportar el mismo dashboard para STAGING y PROD cambiando:
	- datasource a `Fly Prometheus STAGING` o `Fly Prometheus PROD`
	- `app` a `trufiq-staging` o `trufiq-prod`
	- folder a `Trufiq / STAGING` o `Trufiq / PROD`

Comprobaciones base en Fly:

- `fly status --app trufiq-dev`
- `fly checks list --app trufiq-dev`
- `curl -sS https://trufiq-dev.fly.dev/metrics | head`

Direccion elegida (coste bajo):

- Deteccion: alertas en Grafana con metricas de Prometheus.
- Diagnostico: Sentry para ver stacktrace y agrupar errores.
- Soporte: Fly Logs para contexto adicional (request/infra/scripts).

Configuracion Sentry minima (DEV):

- Definir `SENTRY_DSN`.
- Definir `SENTRY_ENVIRONMENT=development`.
- Mantener `SENTRY_TRACES_SAMPLE_RATE=0` para no incurrir en coste de tracing al inicio.
- Opcional: definir `SENTRY_RELEASE` con commit SHA o version.

Enlaces recomendados desde alertas de Grafana:

- `runbook_url`: enlace al runbook interno.
- `dashboard_url`: enlace al dashboard de entorno.
- `sentry_url`: busqueda prefiltrada por `environment` y `service`.
- `logs_url`: enlace a Fly Log Search de la app afectada.
