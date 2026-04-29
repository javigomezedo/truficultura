# Fly Managed Grafana: logs y alertas para Truficultura

Esta guia esta pensada para usar el Grafana gestionado de Fly en `https://fly-metrics.net`.

## 1) Aplicar configuracion en Fly

Desde la raiz del proyecto:

```bash
chmod +x scripts/fly_enable_observability.sh
./scripts/fly_enable_observability.sh truficultura-dev
```

Que hace el script:

- activa `METRICS_ENABLED=1`
- activa logs estructurados (`LOG_JSON=1`)
- elimina `METRICS_TOKEN` para que Fly pueda scrapear `/metrics`
- despliega y valida checks

## 2) Ver errores en el dashboard de logs

Abre:

- `https://fly-metrics.net/d/fly-logs/fly-logs?orgId=1569106&var-app=truficultura-dev`

Consultas utiles en Log Search:

- Errores y excepciones de app:
  - `app:truficultura-dev AND (ERROR OR Exception OR traceback OR "Excepcion")`
- Problemas de base de datos:
  - `app:truficultura-dev AND (postgres OR asyncpg OR "connection refused" OR timeout)`
- Fallos de cron:
  - `app:truficultura-dev AND ("Fallo fatal en cron" OR "Error al procesar gastos recurrentes" OR "Error inesperado procesando municipio")`

## 3) Crear alertas en Fly Managed Grafana (métricas)

En `Alerting -> Alert rules -> New alert rule`, datasource Prometheus.

### A) Excepciones no controladas (critical)

- Query A:

```promql
sum(increase(truficultura_unhandled_exceptions_total{app="truficultura-dev"}[5m]))
```

- Condition: `A > 0`
- For: `1m`
- Labels: `severity=critical`, `service=truficultura`

### B) Ratio 5xx (warning)

- Query A:

```promql
sum(rate(fly_app_http_responses_count{app="truficultura-dev",status=~"5.."}[5m]))
/
clamp_min(sum(rate(fly_app_http_responses_count{app="truficultura-dev"}[5m])), 0.001)
```

- Condition: `A > 0.05`
- For: `10m`
- Labels: `severity=warning`, `service=truficultura`

### C) Ratio 5xx (critical)

- Misma query que B
- Condition: `A > 0.20`
- For: `5m`
- Labels: `severity=critical`, `service=truficultura`

### D) Instancia down (critical)

- Query A:

```promql
max by (instance) (fly_instance_up{app="truficultura-dev"})
```

- Condition: `A < 1`
- For: `2m`
- Labels: `severity=critical`, `service=truficultura`

## 4) Notificaciones (contact points)

En `Alerting -> Contact points`:

- crea Slack/email/PagerDuty/webhook

En `Alerting -> Notification policies`:

- `severity=critical` -> PagerDuty + Slack + email
- `severity=warning` -> Slack

## 5) Validacion final

- Fuerza un error controlado en entorno dev y verifica:
  - aparece en Logs dashboard
  - sube `truficultura_unhandled_exceptions_total`
  - dispara la alerta correspondiente
