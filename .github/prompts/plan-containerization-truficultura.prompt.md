## Backlog Ejecutable - Containerizacion y Despliegue (Fly.io + GHCR)

Objetivo: dejar Truficultura desplegada en cloud con CI/CD automatico en push a main (tests obligatorios), 3 entornos (development/staging/production), cero downtime basico y operacion simple.

Supuestos de esta planificacion:
- Trafico bajo (1-20 usuarios).
- Registro de imagenes en GHCR.
- PostgreSQL gestionado (recomendado para reducir riesgo operativo).
- Costes orientativos a abril de 2026; pueden variar por region y consumo real.

## Dia 1 (base tecnica y CI minimo)

### Objetivo de la fase
Aplicacion dockerizada y pipeline CI funcionando (tests + build), todavia sin despliegue automatico a produccion.

### Backlog de tareas
1. Crear `Dockerfile` de produccion para FastAPI (usuario no root, puerto 8000, comando de arranque estable).
2. Crear `.dockerignore` para reducir el contexto de build.
3. Completar `.env.example` con todas las variables requeridas (incluyendo `SECRET_KEY`).
4. Anadir endpoint de salud (`/health`) en la app.
5. Definir estrategia de migraciones (`alembic upgrade head`) en el proceso de release.
6. Crear workflow de CI en GitHub Actions:
7. Checkout + setup Python.
8. Instalacion de dependencias.
9. Ejecucion de tests del repo.
10. Build de imagen Docker (sin push aun).
11. Activar branch protection en `main` con checks requeridos de CI.

### Entregables
- Imagen construible localmente.
- CI bloqueando merges/deploy si fallan tests.
- Healthcheck funcional.

### Criterios de aceptacion
- `docker build` exitoso.
- Tests verdes en GitHub Actions.
- Endpoint `/health` devuelve 200.

### Estimacion de esfuerzo
- 8-12 horas (1-1.5 dias de trabajo).

## Semana 1 (despliegue cloud y entorno development)

### Objetivo de la fase
Primer despliegue real en cloud con base de datos gestionada y CD para entorno development.

### Backlog de tareas
1. Provisionar app en Fly.io (entorno development).
2. Provisionar PostgreSQL gestionado para development.
3. Configurar secretos en plataforma (`DATABASE_URL`, `SECRET_KEY`, etc.).
4. Configurar despliegue rolling con al menos 2 instancias para evitar downtime basico.
5. Crear workflow de CD para development:
6. Login en GHCR.
7. Push de imagen con tags (`sha` + `latest-dev`).
8. Deploy automatico a Fly.io tras tests correctos.
9. Healthcheck post-deploy y validacion basica de login/flujo principal.
10. Configurar logs y alertas minimas de disponibilidad.
11. Documentar rollback a imagen anterior.

### Entregables
- Entorno development accesible por URL publica.
- Pipeline CI/CD completo para development.
- Runbook inicial de despliegue y rollback.

### Criterios de aceptacion
- Cada push a `main` ejecuta tests y, si pasan, despliega en development.
- Servicio estable tras redeploy.
- Rollback ejecutable en menos de 15 minutos.

### Estimacion de esfuerzo
- 16-24 horas (2-3 dias de trabajo).

## Semana 2 (staging + production + dominio/SSL)

### Objetivo de la fase
Completar estrategia de 3 entornos con promotion flow y salida a produccion segura.

### Backlog de tareas
1. Crear entornos staging y production en Fly.io.
2. Configurar secretos separados por entorno (GitHub Environments + Fly secrets).
3. Definir politica de promocion:
4. `main` despliega auto a development.
5. Promocion a staging automatica o por aprobacion ligera.
6. Promocion a production con aprobacion manual obligatoria.
7. Configurar dominio y DNS.
8. Activar TLS/certificado y redireccion HTTP -> HTTPS.
9. Activar backups automaticos de PostgreSQL y prueba de restauracion.
10. Ejecutar smoke tests en staging y production.
11. Cerrar documentacion operativa (incidentes, restore, rotacion de secretos).

### Entregables
- Tres entornos operativos (dev/staging/prod).
- Produccion con dominio y SSL.
- Backups verificados y runbook final.

### Criterios de aceptacion
- Promotion flow funcionando extremo a extremo.
- Produccion con HTTPS forzado.
- Restauracion de backup validada en entorno no productivo.

### Estimacion de esfuerzo
- 20-32 horas (2.5-4 dias de trabajo).

## Resumen de esfuerzo total

- Dia 1: 8-12 h
- Semana 1: 16-24 h
- Semana 2: 20-32 h
- Total estimado: 44-68 horas (aprox. 1.5-2.5 semanas de ejecucion realista para 1 persona)

## Coste mensual aproximado por servicio

### Escenario A (minimo viable, menor coste)
Nota: prioriza coste; staging y production comparten algunos recursos no criticos cuando sea viable.

| Servicio | Configuracion aproximada | Coste/mes (EUR) |
|---|---|---:|
| Fly.io - App development | 1 instancia pequena | 3-6 |
| Fly.io - App staging | 1 instancia pequena | 3-6 |
| Fly.io - App production | 2 instancias pequenas (rolling deploy) | 8-14 |
| PostgreSQL gestionado | 1 instancia pequena (prod) + backups basicos | 10-18 |
| GHCR | Almacenamiento imagenes habitual de proyecto pequeno | 0-3 |
| Dominio + DNS | 1 dominio anual prorrateado | 1-2 |
| Monitorizacion/alertas extra | Basico (si usas lo incluido en plataforma) | 0-5 |
| **Total estimado** |  | **25-54** |

### Escenario B (separacion estricta por entorno)
Nota: mejor aislamiento, coste mayor.

| Servicio | Configuracion aproximada | Coste/mes (EUR) |
|---|---|---:|
| Fly.io - App development | 1 instancia | 3-6 |
| Fly.io - App staging | 1-2 instancias | 5-12 |
| Fly.io - App production | 2 instancias | 8-14 |
| PostgreSQL gestionado development | 1 instancia pequena | 8-15 |
| PostgreSQL gestionado staging | 1 instancia pequena | 8-15 |
| PostgreSQL gestionado production | 1 instancia pequena + backups | 10-20 |
| GHCR | Registro de imagenes | 0-5 |
| Dominio + DNS | 1 dominio anual prorrateado | 1-2 |
| **Total estimado** |  | **43-89** |

## Recomendacion de arranque (para tu caso)

1. Empezar por Escenario A durante 1-2 meses para validar uso real y consumo.
2. Revisar metrica de carga y coste al final de la Semana 2.
3. Pasar gradualmente a separacion estricta (Escenario B) si sube uso o criticidad.

## Checklist final de salida a produccion

1. Tests verdes y obligatorios en `main`.
2. Imagen versionada y trazable a commit.
3. Migraciones ejecutadas en release sin errores.
4. Healthcheck operativo tras despliegue.
5. Dominio y HTTPS activos.
6. Backups automaticos y restauracion validada.
7. Runbook de rollback documentado y probado.
