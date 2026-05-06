# Plan: Sistema de Avisos (Notifications)

## Decisiones de diseño

- **Canal**: In-app (campanita navbar + centro de notificaciones) + email opcional por tipo de aviso crítico
- **Umbrales**: Panel de preferencias por usuario (configurable)
- **Destinatarios**: Todos los miembros activos del tenant
- **Next migration**: 0032

---

## Tipos de aviso

| Código | Descripción | Temporada | Severidad | Email def. |
|--------|-------------|-----------|-----------|------------|
| `campaign_start` | Inicio campaña agrícola (1 mayo) | Mayo | info | No |
| `no_truffle_events` | Sin eventos de trufa en N días (def. 7) | Dic–Mar | warning | Sí |
| `low_water_balance` | Aporte hídrico (lluvia+riego) bajo en últimos N días | Siempre | warning | Sí |
| `user_inactive` | Usuario sin conectarse N días (def. 30) | Siempre | info | No |
| `no_rainfall_data` | Sin registros de lluvia N días (def. 14) — hueco de datos | Siempre | info | No |
| `campaign_end_reminder` | Recordatorio cierre campaña (abril) | Abril | info | No |
| `stressed_plant_no_replacement` | Planta estresada/muerta sin reemplazar N días (def. 30) | Siempre | info | No |
| `no_irrigation_summer` | Sin riego en parcela N días durante verano Jul–Sep (def. 14) | Jul–Sep | warning | No |
| `no_brule_measurement` | Sin medición de brûlé en N semanas (def. 4) | Siempre | info | No |
| `low_harvest_vs_previous` | Cosecha actual <X% de media histórica (def. 50%) | Dic–Mar | warning | No |

---

## Fase 1 — Base de datos (bloqueante para todo)

1. Crear `app/models/notification.py` con dos modelos:
   - **`Notification`**: `id`, `user_id`, `tenant_id`, `notification_type`, `severity`, `title`, `message`, `extra_data` (JSON), `is_read`, `is_dismissed`, `email_sent`, `created_at`, `dedup_key`
   - **`NotificationPreference`**: `id`, `user_id`, `tenant_id`, `notification_type`, `enabled`, `email_enabled`, `threshold_days`, `threshold_value`
   - UNIQUE constraint `(user_id, dedup_key)` en `Notification` para deduplicación
   - UNIQUE constraint `(user_id, notification_type)` en `NotificationPreference`
2. Migración `0032_add_notifications_tables.py`
3. Añadir `last_seen_at: DateTime (nullable, tz)` a `app/models/user.py`
4. Migración `0033_add_last_seen_at_to_users.py`

## Fase 2 — Tracking de actividad (*depende de Fase 1*)

5. En `app/auth.py`, función `get_current_user()`: actualizar `user.last_seen_at = utcnow()` de forma **throttled** (solo si `last_seen_at` es `None` o ha pasado más de 1 hora) para no escribir en BD en cada request

## Fase 3 — Servicio de notificaciones (*depende de Fases 1 y 2*)

6. Crear `app/services/notifications_service.py` con:
   - **CRUD de avisos**: `get_unread_count()`, `list_notifications()`, `mark_read()`, `mark_all_read()`, `dismiss()`
   - **Preferencias**: `get_preferences()` (retorna config del usuario con fallback a defaults), `upsert_preference()`
   - **Generación**: `check_and_create_notifications(db)` — entrada del cron; itera todos los tenants y sus miembros activos
   - **Helper de deduplicación**: `_create_if_not_exists()` — inserta solo si no existe `dedup_key` para ese usuario; si `email_enabled=True` llama a `send_email()` de `email_service`
   - **Checkers por tipo** (uno por cada fila de la tabla anterior): cada checker recibe tenant, lista de miembros y preferencias resueltas, y llama a `_create_if_not_exists()`
   - **Clave de dedup por tipo**: `campaign_start` → año campaña; `no_truffle_events` → semana ISO; `low_water_balance` → fecha exacta; resto → YYYY-MM

## Fase 4 — Script cron (*depende de Fase 3*)

7. Crear `scripts/process_notifications_cron.py` siguiendo exactamente el patrón de `scripts/process_recurring_expenses_cron.py` (async engine, Sentry, `--dry-run`)
8. Actualizar `fly.toml` para añadir `python scripts/process_notifications_cron.py` al comando del cron diario

## Fase 5 — Router y templates (*depende de Fase 3, paralelo con Fase 4*)

9. Crear `app/routers/notifications.py`:
   - `GET /notifications` — centro de notificaciones (HTML)
   - `POST /notifications/{id}/read` — marcar leído
   - `POST /notifications/read-all`
   - `POST /notifications/{id}/dismiss`
   - `GET /notifications/preferences` — formulario de preferencias (HTML)
   - `POST /notifications/preferences` — guardar prefs
   - `GET /notifications/unread-count` — JSON para AJAX del badge
10. `app/templates/notifications/index.html` — lista paginada, filtros por tipo/leído
11. `app/templates/notifications/preferences.html` — tabla con toggle + umbral por tipo
12. Modificar `app/templates/base.html`: añadir campanita con badge (`<span class="badge">`) y dropdown de últimas 5; count cargado via AJAX a `/notifications/unread-count`
13. Incluir el router en `app/main.py`

## Fase 6 — Envío de email (*depende de Fase 3*)

14. En `_create_if_not_exists()`: si el aviso es nuevo Y `NotificationPreference.email_enabled=True` → llamar `send_email()` con plantilla HTML inline (mismo estilo que el resto del proyecto)

## Fase 7 — Tests (*depende de Fases 3, 4, 5*)

15. `tests/services/test_notifications_service.py` — unit tests con `FakeExecuteResult` de `conftest.py`; cubrir: `get_unread_count`, `mark_read`, `dismiss`, `get_preferences`, `_check_campaign_start`, `_check_user_inactive`
16. `tests/test_notifications_router.py` — tests de router siguiendo patrón de `tests/test_expenses_router.py`
17. Verificar que cobertura global no cae por debajo del 82%

---

## Archivos nuevos

- `app/models/notification.py`
- `app/services/notifications_service.py`
- `app/routers/notifications.py`
- `app/templates/notifications/index.html`
- `app/templates/notifications/preferences.html`
- `scripts/process_notifications_cron.py`
- `alembic/versions/0032_add_notifications_tables.py`
- `alembic/versions/0033_add_last_seen_at_to_users.py`
- `tests/services/test_notifications_service.py`
- `tests/test_notifications_router.py`

## Archivos modificados

- `app/models/user.py` — añadir `last_seen_at`
- `app/auth.py` — tracking throttled de `last_seen_at` en `get_current_user()`
- `app/main.py` — include notifications router
- `app/templates/base.html` — campanita en navbar
- `fly.toml` — añadir cron script al comando diario

---

## Decisiones técnicas

- `get_plot_daily_water_balance()` retorna agua aportada en un día (lluvia + riego). El checker de balance bajo sumará los últimos N días y comparará con el umbral configurable (m³ totales en el período)
- El tracking de `last_seen_at` es throttled (≥1h) para evitar escrituras excesivas en BD
- Los avisos **no se borran** al marcarlos leídos — solo cambia `is_read`; `dismiss` activa `is_dismissed` y los oculta de la lista normal
- Defaults de preferencias codificados como constantes en `notifications_service.py`, no en base de datos
- No se implementan preferencias de notificación push (web push) ni Slack — out of scope

---

## Verificación

1. `alembic upgrade head` aplica 0032 y 0033 sin error
2. `pytest tests/services/test_notifications_service.py -q` — todos verdes
3. `pytest tests/test_notifications_router.py -q` — todos verdes
4. `pytest -q tests/` — suite completa verde, cobertura ≥ 82%
5. `python scripts/process_notifications_cron.py --dry-run` — ejecuta sin errores y loguea avisos que generaría
6. Login manual → campanita visible en navbar con badge
7. Crear datos de test (sin eventos trufa en temporada alta) → cron genera aviso → aparece en `/notifications`
8. Guardar preferencia en `/notifications/preferences` → umbral persiste → próximo cron lo respeta
