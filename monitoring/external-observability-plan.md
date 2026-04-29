# Plan detallado development -> staging -> production para observabilidad externa

## Objetivo

Tener control de errores, alertas y salud de infraestructura con un sistema externo, manteniendo Fly como plataforma de ejecucion.

## Arquitectura objetivo

- Aplicacion en Fly expone metricas en /metrics.
- Fly scrapea esas metricas mediante bloque metrics en fly.toml y las publica en su Prometheus API.
- Grafana externo consulta la Prometheus API de Fly y gestiona reglas/alertas.
- Logs se consultan en Fly Log Search y, si hace falta alertar por logs, se exportan a Loki.
- Errores de aplicacion detallados en Sentry (opcional pero recomendado).

## Diseno recomendado para los 3 entornos

- Un unico Grafana externo para todos los entornos.
- Un datasource por entorno para aislar consultas y simplificar reglas.
- Carpetas, dashboards y alert rules separadas por entorno.
- Contact points y notification policies separados por entorno y severidad.

Nombres sugeridos:

- Apps Fly
  - `trufiq-dev`
  - `trufiq-staging`
  - `trufiq-prod`
- Datasources
  - `Fly Prometheus DEV`
  - `Fly Prometheus STAGING`
  - `Fly Prometheus PROD`
- Folders de alertas y dashboards
  - `Trufiq / DEV`
  - `Trufiq / STAGING`
  - `Trufiq / PROD`
- Evaluation groups
  - `trufiq-dev-core`
  - `trufiq-staging-core`
  - `trufiq-prod-core`

Labels recomendados en todas las reglas:

- `service=trufiq`
- `environment=dev|staging|prod`
- `severity=warning|critical`
- `team=backend`

Canales recomendados:

- `development`
  - email unico o Slack de desarrollo
- `staging`
  - Slack de equipo + email tecnico
- `production`
  - on-call/PagerDuty + Slack + email

## Estado actual

- DEV validado el 2026-04-29.
- Fly publica metricas custom correctamente via `/metrics` y Prometheus API.
- Grafana Cloud externo conectado al org `personal`.
- Alertas DEV creadas y evaluando correctamente.
- Notificaciones por email comprobadas tanto en disparo como en resolucion de un incidente real de `instance down`.
- STAGING pendiente de crear y alinear con el comportamiento esperado de PROD.
- PROD pendiente de habilitar con canales y umbrales definitivos.

## Fase 1 (DEV) - Preparar y validar metricas

1. Validar configuracion de Fly
- Confirmar bloque metrics en fly.toml:
  - port = 8000
  - path = /metrics
- Confirmar check de salud en /health.

2. Validar endpoint de metricas en dev
- Ejecutar:
  - curl -sS https://trufiq-dev.fly.dev/metrics
- Verificar presencia de:
  - truficultura_http_requests_total
  - truficultura_http_request_duration_seconds
  - truficultura_unhandled_exceptions_total

3. Configurar logs estructurados
- En secrets de Fly dev:
  - LOG_LEVEL=INFO
  - LOG_JSON=1
  - METRICS_ENABLED=1
- Nota: si necesitas proteger /metrics con token para scrapers externos, usar METRICS_TOKEN y cabecera x-metrics-token.

4. Verificacion de plataforma
- fly status --app trufiq-dev
- fly checks list --app trufiq-dev
- fly logs --app trufiq-dev --no-tail | tail -n 80

Criterio de salida Fase 1:
- checks pasando
- metricas disponibles
- logs legibles y con nivel/error

## Fase 2 (DEV) - Grafana externo y primeras alertas

1. Crear stack Grafana externo
- Opcion recomendada: Grafana Cloud (rapido, sin mantenimiento).

2. Conectar datasource Prometheus (Fly)
- URL:
  - https://api.fly.io/prometheus/<org-slug>/
- Auth header:
  - Authorization: Bearer <token>  (si token de fly auth token)
  - Authorization: FlyV1 <token>   (si token de fly tokens create)

3. Crear dashboard base DEV
- Panel tasa de peticiones
- Panel ratio 5xx
- Panel latencia p95
- Panel excepciones no controladas
- Base exportable disponible en `monitoring/truficultura-overview-dashboard.json`
- Importar en folder `Trufiq / DEV` usando datasource `Fly Prometheus DEV`

4. Crear reglas de alerta DEV

A) Excepciones no controladas (critical)
- Query:
  sum(increase(truficultura_unhandled_exceptions_total{app="trufiq-dev"}[5m]))
- Condicion: > 0
- For: 1m

B) Ratio 5xx warning
- Query:
  sum(rate(fly_app_http_responses_count{app="trufiq-dev",status=~"5.."}[5m]))
  /
  clamp_min(sum(rate(fly_app_http_responses_count{app="trufiq-dev"}[5m])), 0.001)
- Condicion: > 0.05
- For: 10m

C) Ratio 5xx critical
- Misma query
- Condicion: > 0.20
- For: 5m

D) Instancia down (critical)
- Query:
  max by (instance) (fly_instance_up{app="trufiq-dev"})
- Condicion: < 1
- For: 2m

E) Latencia p95 warning
- Query:
  histogram_quantile(
    0.95,
    sum by (le) (rate(truficultura_http_request_duration_seconds_bucket{app="trufiq-dev"}[5m]))
  )
- Condicion: > 1.5
- For: 10m

5. Notificaciones DEV
- Configuracion minima valida: un unico contact point por email como default policy.
- Configuracion recomendada: contact points separados por severidad.
- Notification policies por label severity cuando haya mas de un canal.

Criterio de salida Fase 2:
- alertas en estado normal
- al forzar error controlado se dispara alerta esperada

Resultado obtenido en DEV:
- datasource externo operativo
- 4 alert rules creadas
- email recibido en alerta real de `instance down`
- email de resolucion recibido al recuperar la instancia y volver la regla a `Normal`

## Fase 3 (DEV) - Endurecimiento

1. Ajustar umbrales con datos reales de una semana.
2. Excluir rutas ruidosas (por ejemplo /health y /metrics) en dashboards/alertas de latencia.
3. Definir runbook corto por alerta (primeras acciones, comandos de diagnostico, responsables).

Lecciones aprendidas en DEV:

- Las alertas de ratio 5xx en entornos de poco trafico deben tratar `No data` y `Error` como `OK` para evitar ruido.
- La alerta de `instance down` debe tratar `No data` y `Error` como `Alerting`.
- Para detectar perdida de replicas es mejor alertar por numero esperado de instancias activas que por una sola serie individual.

Configuracion DEV afinada:

- `Unhandled exceptions`
  - `No data state = OK`
  - `Error state = Alerting` o `OK` segun tolerancia al ruido
- `HTTP 5xx ratio warning/critical`
  - `No data state = OK`
  - `Error state = OK`
- `Instance down`
  - `No data state = Alerting`
  - `Error state = Alerting`

## Fase 4 (STAGING) - Entorno preproduccion

Objetivo:

- Tener un entorno casi identico a PROD para validar dashboards, reglas y notificaciones antes de promocionar cambios.

1. Crear datasource de staging
- nombre sugerido: `Fly Prometheus STAGING`
- URL: `https://api.fly.io/prometheus/<org-slug>/`
- token readonly dedicado a staging

2. Clonar dashboards y reglas desde development
- cambiar `app="trufiq-dev"` por `app="trufiq-staging"`
- mover o duplicar en folder `Trufiq / STAGING`
- usar evaluation group `trufiq-staging-core`
- reutilizar `monitoring/truficultura-overview-dashboard.json` si prefieres reimportar desde fichero en vez de duplicar desde Grafana

3. Endurecer notificaciones
- `warning` -> Slack de equipo
- `critical` -> Slack de equipo + email tecnico

4. Validacion de staging
- comprobar metricas en datasource STAGING
- forzar una alerta controlada
- validar disparo y resolucion

5. Alinear con PROD
- replicas minimas similares a PROD si es viable
- mismas reglas y labels que PROD, salvo canales y umbrales si hace falta menos ruido

Criterio de salida Fase 4:
- staging replica de forma razonable el comportamiento de prod
- alertas y resoluciones verificadas en staging
- reglas listas para promoverse sin redisenarlas

## Fase 5 (PROD) - Paso a produccion

1. Clonar dashboards y reglas de DEV a PROD
- Cambiar filtros app a trufiq-prod.
- Mantener mismos nombres de alerta con prefijo PROD.
- Reutilizar el mismo dashboard base exportable y ajustar variables por entorno.

2. Configurar canales de notificacion de PROD
- Critical: PagerDuty/On-call + Slack + email
- Warning: Slack de equipo
- Definir escalado y horarios de guardia.

3. Seguridad de tokens
- Crear token de solo lectura y alcance minimo para Prometheus API.
- Guardarlo como secreto en Grafana externo.
- Rotacion trimestral.

4. Validacion de smoke en PROD
- Probar lectura de series en datasource.
- Simular escenario de alerta no destructivo y confirmar notificacion.

5. SLOs basicos en PROD
- Disponibilidad HTTP
- Ratio 5xx
- Latencia p95
- Tiempo de deteccion de incidentes

Checklist exacto de promocion a PROD:

1. Crear o duplicar datasource en Grafana externo
- nombre sugerido: `Fly Prometheus PROD`
- URL: `https://api.fly.io/prometheus/<org-slug>/`
- token readonly dedicado a PROD

2. Clonar reglas desde STAGING
- cambiar `app="trufiq-staging"` por `app="trufiq-prod"`
- mantener mismo folder pero con subcarpeta o prefijo PROD
- mantener mismo evaluation group o crear `trufiq-prod-core`

3. Ajustar umbrales y comportamiento por regla
- `Unhandled exceptions`
  - mantener `for=1m`
  - `No data = OK`
  - `Error state = Alerting`
- `HTTP 5xx warning`
  - mantener umbral inicial `> 0.05`
  - revisar tras primera semana de trafico real
  - `No data = OK`
  - `Error state = OK`
- `HTTP 5xx critical`
  - mantener umbral inicial `> 0.20`
  - `No data = OK`
  - `Error state = OK`
- `Instance down`
  - cambiar a umbral acorde al numero minimo esperado de replicas en PROD
  - ejemplo: alertar si instancias activas `< 2` o `< 3` segun despliegue
  - `No data = Alerting`
  - `Error state = Alerting`

4. Separar canales de notificacion
- `severity=critical` -> on-call / PagerDuty + Slack + email
- `severity=warning` -> Slack de equipo
- default policy solo como fallback

5. Ejecutar smoke test tras primer deploy de PROD
- verificar lectura de metricas en datasource PROD
- comprobar que las reglas estan en `Normal`
- simular un incidente controlado no destructivo o una alerta de prueba
- confirmar recepcion en canales correctos

Criterio de salida Fase 5:
- alertas operativas con notificacion real
- runbook aprobado
- responsables y escalado definidos

## Fase 6 (opcional) - Errores de aplicacion con Sentry

1. Integrar SDK en FastAPI y scripts de cron.
2. Enviar excepciones no controladas y contexto de release.
3. Crear enlace cruzado desde alertas Grafana a incidencias Sentry.

Beneficio:
- Grafana detecta el sintoma
- Sentry acelera el diagnostico de causa raiz

## Checklist rapido de ejecucion

- DEVELOPMENT
  - metricas expuestas y scrappeadas
  - datasource externo conectado
  - 5 alertas creadas
  - notificaciones probadas
- STAGING
  - datasource propio creado
  - reglas clonadas desde development
  - disparo y resolucion validados
- PRODUCTION
  - reglas clonadas desde staging con filtro app prod
  - canales de guardia activos
  - token readonly rotado y documentado
  - test de alerta ejecutado tras deploy

## Matriz operativa por entorno

### Development

- Finalidad: detectar roturas funcionales y validar cambios de observabilidad.
- Datasource: `Fly Prometheus DEV`.
- Folder: `Trufiq / DEV`.
- Canales: email unico o Slack de desarrollo.
- Politica: tolerar algo mas de ruido; sirve para aprender y ajustar.

### Staging

- Finalidad: validar que las reglas se comportan como en produccion antes de promocionar.
- Datasource: `Fly Prometheus STAGING`.
- Folder: `Trufiq / STAGING`.
- Canales: Slack de equipo + email tecnico.
- Politica: casi igual que PROD; solo reducir ruido si staging tiene muy poco trafico.

### Production

- Finalidad: detectar incidentes reales y disparar respuesta operativa.
- Datasource: `Fly Prometheus PROD`.
- Folder: `Trufiq / PROD`.
- Canales: on-call/PagerDuty + Slack + email.
- Politica: minima tolerancia a falsos negativos; labels y ownership cerrados.
