# Runbook Operativo: Migracion de Nombre a Trufiq

Objetivo: ejecutar el rebranding de Truficultura a Trufiq con riesgo bajo, validaciones por fase y rollback claro.

Duracion estimada:
- DEV completo: 2-3 horas.
- STAGING: 45-60 min.
- PROD: 45-60 min.
- Observacion post-cutover: 24-48 h.

## Modo Ejecucion (Checklist en Vivo)

Uso recomendado:
- Recorre las fases en orden.
- Marca estado por fase: PENDIENTE, EN CURSO, BLOQUEADA, COMPLETADA.
- No avances a la siguiente fase sin cumplir las validaciones de la fase actual.

Leyenda de estado:
- [ ] PENDIENTE
- [~] EN CURSO
- [x] COMPLETADA
- [!] BLOQUEADA

### Hoja de Control

Fase 0 - Preparacion
- Estado: [ ]
- Responsable:
- Inicio:
- Fin:
- Evidencias (comandos/salidas clave):
- Go/No-Go: NO-GO hasta tener tag pre-migracion

Fase 1 - Inventario y linea base
- Estado: [ ]
- Responsable:
- Inicio:
- Fin:
- Evidencias (ruta del inventario y resumen):
- Go/No-Go: NO-GO si faltan archivos criticos en el inventario

Fase 2 - Renombrado de repo
- Estado: [ ]
- Responsable:
- Inicio:
- Fin:
- Evidencias (remote origin y push a rama):
- Go/No-Go: NO-GO si falla push al nuevo origin

Fase 3 - Rebranding codigo/config
- Estado: [ ]
- Responsable:
- Inicio:
- Fin:
- Evidencias (diff, lock actualizado, tests):
- Go/No-Go: NO-GO si no hay tests verdes

Fase 4 - CI/CD
- Estado: [ ]
- Responsable:
- Inicio:
- Fin:
- Evidencias (run de CI y resultado):
- Go/No-Go: NO-GO si CI no esta en verde

Fase 5 - Fly DEV en paralelo
- Estado: [ ]
- Responsable:
- Inicio:
- Fin:
- Evidencias (status/checks/health/metrics):
- Go/No-Go: NO-GO si health o checks fallan

Fase 6 - DB y scripts operativos
- Estado: [ ]
- Responsable:
- Inicio:
- Fin:
- Evidencias (alembic + tests integration):
- Go/No-Go: NO-GO si integracion no esta en verde

Fase 7 - Grafana y observabilidad
- Estado: [ ]
- Responsable:
- Inicio:
- Fin:
- Evidencias (dashboard con datos + alertas):
- Go/No-Go: NO-GO si no hay visibilidad en dashboard

Fase 8 - STAGING y PROD
- Estado: [ ]
- Responsable:
- Inicio:
- Fin:
- Evidencias (health/smoke/error rate):
- Go/No-Go: NO-GO si STAGING no valida

Fase 9 - Cutover integraciones
- Estado: [ ]
- Responsable:
- Inicio:
- Fin:
- Evidencias (webhooks/correo/callbacks):
- Go/No-Go: NO-GO si no pasan eventos reales

Fase 10 - Cierre y limpieza
- Estado: [ ]
- Responsable:
- Inicio:
- Fin:
- Evidencias (inventario final sin referencias criticas):
- Go/No-Go: GO final solo con criterio de exito completo

### Criterios de Parada Inmediata

- Cualquier fase con perdida de acceso a datos o errores 5xx sostenidos.
- Healthcheck KO durante despliegue en entorno objetivo.
- Fallo de migraciones en base de datos.
- CI roto en rama de migracion sin causa clara.

### Plantilla de Evidencia por Fase

```text
Fecha/hora:
Entorno:
Comando ejecutado:
Salida resumida:
Decision: GO / NO-GO
Responsable:
```

## Fase 0: Preparacion (Go/No-Go Inicial)

Criterio de entrada:
- Tienes acceso admin a GitHub repo.
- Tienes acceso a Fly apps y secrets.
- Tienes acceso a Grafana y alertas.
- CI actual esta en verde.

Comandos:
```bash
git fetch --all --prune
git checkout main
git pull
git checkout -b chore/rebrand-trufiq
git tag pre-trufiq-migration-$(date +%Y%m%d-%H%M)
```

Validacion:
```bash
git status
git tag | grep pre-trufiq-migration
```

Rollback:
```bash
git checkout main
git branch -D chore/rebrand-trufiq
```

## Fase 1: Inventario y Linea Base

Objetivo: capturar donde vive el nombre actual para no dejar restos criticos.

Comandos:
```bash
rg -n "truficultura|TRUFICULTURA|truficultura-dev|truficultura-staging|truficultura-prod" .
rg -n "TRUFICULTURA_DB_DEV_PASSWORD|truficultura-theme|truficultura-overview" .
```

Validacion:
- Guardar salida en un archivo temporal local para checklist de cierre.
- Confirmar que aparecen al menos estos archivos clave: `pyproject.toml`, `fly.toml`, `.github/workflows/ci.yml`, `.github/workflows/fly-deploy.yml`, `app/main.py`, `app/config.py`, `app/observability.py`, `monitoring/README.md`, `monitoring/truficultura-overview-dashboard.json`, `README.md`.

Go/No-Go:
- Si faltan archivos esperados en el inventario, parar y revisar.

## Fase 2: Renombrado de Repo en GitHub

Objetivo: alinear repo remoto con nueva marca.

Comandos con gh:
```bash
gh repo rename trufiq --yes
git remote -v
git remote set-url origin git@github.com:TU_ORG/trufiq.git
git remote -v
git ls-remote --heads origin | head
```

Alternativa sin gh:
- Renombrar en GitHub UI.
- Ejecutar solo `git remote set-url origin ...`.

Validacion:
```bash
git push --set-upstream origin chore/rebrand-trufiq
```

Rollback:
- Renombrar repo de vuelta en GitHub UI.
- Ajustar `origin` al nombre anterior.

## Fase 3: Rebranding de Codigo y Config Local

Objetivo: actualizar marca, textos y naming tecnico interno.

Archivos objetivo:
- `pyproject.toml`
- `.env.example`
- `app/main.py`
- `app/config.py`
- `app/services/email_service.py`
- `app/static/js/app.js`
- `app/static/img/favicon.svg`
- `locales/es/LC_MESSAGES/messages.po`
- `locales/en/LC_MESSAGES/messages.po`
- `locales/fr/LC_MESSAGES/messages.po`
- `README.md`

Convencion en esta fase:
- Marca visible: Trufiq.
- Slug: trufiq.
- Entornos objetivo: trufiq-dev, trufiq-staging, trufiq-prod.
- Metricas Prometheus: mantener prefijo actual temporalmente para continuidad historica.

Comandos de control:
```bash
rg -n "Truficultura|truficultura" app locales README.md pyproject.toml .env.example
uv lock
uv run pytest
```

Validacion:
- Tests verdes.
- No quedan referencias de marca antigua en UI/config critica.
- Quedan solo referencias historicas intencionadas en docs de migracion si las hubiera.

Commit recomendado:
```bash
git add -A
git commit -m "rebrand: update app naming to Trufiq (code, config, i18n)"
```

## Fase 4: CI/CD

Objetivo: asegurar que pipelines funcionan con el nuevo nombre.

Archivos:
- `.github/workflows/ci.yml`
- `.github/workflows/fly-deploy.yml`

Comandos:
```bash
git add -A
git commit -m "ci: align pipelines with Trufiq naming"
git push
gh workflow run ci.yml
gh run list --limit 5
```

Validacion:
- CI en verde.
- Build de imagen correcto.
- No referencias rotas a apps Fly antiguas en workflow activo.

Rollback:
```bash
git revert HEAD
```

## Fase 5: Fly DEV en Paralelo

Objetivo: levantar entorno nuevo sin tocar el actual.

Comandos:
```bash
fly apps create trufiq-dev
cp fly.toml fly.trufiq-dev.toml
# Editar app en fly.trufiq-dev.toml a trufiq-dev
fly secrets set -a trufiq-dev DATABASE_URL=... SECRET_KEY=... SMTP_FROM=noreply@trufiq.app
fly deploy -c fly.trufiq-dev.toml -a trufiq-dev
```

Validaciones tecnicas:
```bash
fly status --app trufiq-dev
fly checks list --app trufiq-dev
curl -sS -i https://trufiq-dev.fly.dev/health | head -n 20
curl -sS https://trufiq-dev.fly.dev/metrics | head -n 30
```

Validacion funcional:
- Login.
- Alta/edicion de gasto.
- Alta/edicion de ingreso.
- Vista de graficas.

Go/No-Go:
- Si health/checks no estan OK, no avanzar a STAGING.

## Fase 6: Base de Datos y Scripts Operativos

Objetivo: coherencia de nombres de DB y herramientas de operacion.

Archivos:
- `alembic.ini`
- `docker-compose.yml`
- `scripts/proxy-dev-db.sh`
- `README.md`

Comandos:
```bash
uv run alembic upgrade head
uv run pytest tests/integration -q
```

Validacion:
- Integracion en verde.
- Proxy DB funciona con variables nuevas.
- Documentacion de conexion actualizada.

## Fase 7: Grafana y Observabilidad

Objetivo: dashboards y alertas apuntando al nuevo app label.

Archivos:
- `monitoring/truficultura-overview-dashboard.json`
- `monitoring/README.md`
- `monitoring/external-observability-plan.md`
- `app/observability.py`

Estrategia recomendada:
- Duplicar dashboard actual y cambiar solo filtros de app a `trufiq-dev`, `trufiq-staging`, `trufiq-prod`.
- Mantener nombres de metricas por ahora.

Comandos de verificacion:
```bash
curl -sS https://trufiq-dev.fly.dev/metrics | grep -E "http_requests_total|http_request_duration_seconds|unhandled_exceptions_total" | head -n 20
```

Validacion:
- Dashboard con datos reales.
- Alertas criticas disparan/evaluan correctamente.

## Fase 8: STAGING y PROD

Objetivo: desplegar por promocion, no por salto directo.

Comandos:
```bash
fly apps create trufiq-staging
fly apps create trufiq-prod
fly secrets set -a trufiq-staging ...
fly secrets set -a trufiq-prod ...
fly deploy -c fly.trufiq-staging.toml -a trufiq-staging
fly deploy -c fly.trufiq-prod.toml -a trufiq-prod
```

Validacion STAGING:
- health OK.
- smoke tests funcionales.
- dashboards con data.

Validacion PROD:
- health OK.
- login + flujo economico basico OK.
- error rate estable tras 30-60 min.

## Fase 9: Cutover de Integraciones

Objetivo: mover todo el trafico e integraciones al naming nuevo.

Checklist:
- Webhooks Stripe actualizados a host trufiq.
- SMTP FROM y dominios de correo actualizados.
- Cualquier callback URL externo actualizado.
- Runbooks y docs operativos actualizados.

Validacion:
- Evento real de webhook recibido.
- Correo transaccional correcto.
- No errores de callback en logs.

## Fase 10: Cierre y Limpieza

Objetivo: cerrar migracion y retirar legado.

Comandos:
```bash
rg -n "Truficultura|truficultura" .
git status
uv run pytest
```

Acciones:
- Eliminar referencias no deseadas al nombre anterior.
- Mantener solo lo historico intencionado.
- Tras 24-48 h estables, desactivar apps Fly antiguas.

Criterio de exito final:
- CI verde.
- DEV/STAGING/PROD en Trufiq operativos.
- Observabilidad y alertas correctas.
- Sin dependencias activas del naming anterior.

## Plan de Ejecucion en una Tarde

Orden recomendado:
1. Fase 0
2. Fase 1
3. Fase 2
4. Fase 3
5. Fase 4
6. Fase 5
7. Fase 7
8. Fase 8 (al menos STAGING)
9. Fase 9
10. Fase 10
