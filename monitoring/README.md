# Monitorizacion y alertas (Fly Managed Grafana)

Este proyecto usa el Grafana gestionado por Fly (`fly-metrics.net`) como fuente unica de verdad para logs, metricas y alertas.

## 1) Aplicar observabilidad en Fly

Ejecuta:

```bash
./scripts/fly_enable_observability.sh truficultura-dev
```

Este script:

- activa `METRICS_ENABLED=1`
- activa `LOG_JSON=1`
- elimina `METRICS_TOKEN` para permitir scrape gestionado por Fly
- despliega cambios y valida checks

## 2) Verificacion en plataforma

```bash
fly status --app truficultura-dev
fly checks list --app truficultura-dev
```

## 3) Logs y alertas en Grafana gestionado

- Logs: `https://fly-metrics.net/d/fly-logs/fly-logs?orgId=1569106&var-app=truficultura-dev`
- Guia de reglas y consultas: `monitoring/fly-managed-grafana.md`

## 4) Contact points y politicas

En `fly-metrics.net`:

- `Alerting -> Contact points`
- `Alerting -> Notification policies`

Recomendacion minima:

- `severity=critical` -> PagerDuty/Slack + email
- `severity=warning` -> Slack
