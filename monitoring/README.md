# Monitorizacion y alertas (stack externo)

Este directorio documenta el enfoque recomendado para Truficultura cuando el Grafana gestionado por Fly no permite administrar alertas.

Resumen de arquitectura recomendada:

- Fly como runtime de aplicacion y fuente de metricas (Prometheus API).
- Grafana externo (por ejemplo Grafana Cloud) para dashboards, reglas y notificaciones.
- Opcional: Sentry para trazas de excepcion y contexto de errores.

Documento principal:

- `monitoring/external-observability-plan.md`

Estado:

- DEV ya validado con alertas reales y notificacion por email.
- El siguiente hito es crear STAGING y despues promover la configuracion a PROD con canales y umbrales adaptados.

Diseno recomendado:

- Un unico Grafana externo.
- Un datasource por entorno: DEV, STAGING y PROD.
- Carpetas y reglas separadas por entorno.
- Canales de notificacion distintos segun entorno y severidad.

Comprobaciones base en Fly:

- `fly status --app truficultura-dev`
- `fly checks list --app truficultura-dev`
- `curl -sS https://truficultura-dev.fly.dev/metrics | head`
