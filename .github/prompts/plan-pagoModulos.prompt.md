# Plan: Sistema de pagos por módulos (Planes Basic / Premium / Enterprise)

## Matriz de acceso (definitiva)
read_only = mismo acceso que basic, pero sin escritura (post-trial, past_due, canceled)

| Funcionalidad              | Trial | read_only (= basic 👁) | Basic | Premium | Enterprise |
|----------------------------|-------|------------------------|-------|---------|------------|
| Parcelas                   | ✅    | 👁                     | ✅    | ✅      | ✅         |
| Gastos / Ingresos          | ✅    | 👁                     | ✅    | ✅      | ✅         |
| Rentabilidad / analítica   | ✅    | 👁                     | ✅    | ✅      | ✅         |
| Pozos / riego / labores    | ✅    | 👁                     | ✅    | ✅      | ✅         |
| Lluvia (manual + Aemet)    | ✅    | 👁                     | ✅    | ✅      | ✅         |
| Tiempo (Aemet/Ibericam)    | ✅    | ❌                     | ❌    | ✅      | ✅         |
| Análisis de parcelas       | ✅    | ❌                     | ❌    | ✅      | ✅         |
| Simulador de riego         | ✅    | ❌                     | ❌    | ✅      | ✅         |
| Asistente IA               | ✅    | ❌                     | ❌    | ✅      | ✅         |
| Trabajadores / multitenant | ✅    | ❌                     | ❌    | ❌      | ✅         |
| Límite plantas             | ∞     | ∞ (👁)                 | ≤500  | ∞       | ∞          |
| Export datos               | ✅    | ✅                     | ✅    | ✅      | ✅         |

👁 = acceso solo lectura (can read, cannot write/create/delete)

## Implicación clave en has_feature
- `has_feature` resuelve features disponibles independientemente de escritura
- `read_only` comparte exactamente la misma lista de features que `basic`
- `require_write_access` es el único guard que separa `basic` de `read_only`
- `has_feature("lluvia", read_only)` == True (lluvia es accesible en read_only, solo lectura)
- `has_feature("tiempo", read_only)` == False
- `has_feature("analitica_parcelas", read_only)` == False

## Decisiones de diseño (confirmadas)
- `get_plan_mode` devuelve: `"trial"` | `"read_only"` | `"basic"` | `"premium"` | `"enterprise"`
  - `"trial"` = `status=="trialing"` y `trial_ends_at > now`
  - `"read_only"` = trial expirado, past_due, canceled, o active con `subscription_ends_at <= now`
  - `"basic|premium|enterprise"` = `status=="active"` y `tenant.plan` setado y subscription vigente
- Admin (`role=="admin"`) → siempre `"enterprise"`
- No existe `"blocked"` como nivel de acceso distinto; past_due y canceled → `read_only`
- Cambio de plan vía Stripe Customer Portal (no UI propia); webhook `customer.subscription.updated` detecta nuevo `price_id` → actualiza `tenant.plan`
- Exports siempre permitidos (incluso en `read_only`)
- Migración DEV: `UPDATE tenants SET plan='premium' WHERE subscription_status='active'`
- `TRIAL_DAYS = 30` (era 14)

## Límite de 500 plantas en Basic — detalle de implementación

El límite se aplica en DOS niveles porque hay múltiples vías para añadir plantas:

### Nivel 1 — Router dependency `require_plant_limit`
Aplica solo a la creación de una planta individual (POST /plants/nuevo o equivalente).
Comprueba `count(plants for tenant) >= 500` antes de permitir el handler.

### Nivel 2 — Lógica en el servicio (no en el router)
Para los otros dos casos donde el total puede aumentar:
- **Actualizar `num_plants` en una parcela**: el servicio calcula
  `total_proyectado = total_plantas_tenant - plantas_actuales_parcela + nuevo_num_plants`
  y lanza `PlantLimitExceededException` si `total_proyectado > 500`.
- **Bulk import**: el servicio cuenta el total proyectado antes de insertar y rechaza si supera 500.

Mensaje de error uniforme en los tres casos:
> "Has alcanzado el límite de 500 plantas del plan Básico. Actualiza a Premium para plantas ilimitadas."

Ejemplos:
- 500 plantas existentes → crear 1 más → falla (router dependency)
- Parcela con 100 plantas, total tenant = 500 → cambiar num_plants a 101 → falla (servicio: 501 > 500)
- Import con 50 plantas cuando ya hay 480 → falla (servicio: 530 > 500)

## Modo lectura (read_only) — comportamiento de UI

La seguridad real la garantiza el backend (`require_write_access` bloquea los POST).
La UI es capa de UX, no de seguridad.

### En vistas de lista
- Ocultar botón "Crear nuevo / Añadir" (via `{% if not is_read_only %}`)
- Ocultar iconos/botones de editar por fila
- Ocultar iconos/botones de eliminar por fila

### En vistas de formulario (GET /expenses/nuevo, GET /plots/1/editar, etc.)
El usuario PUEDE navegar a la URL del formulario (no se redirige). Pero:
- Todos los `<input>`, `<select>`, `<textarea>` renderizan con `readonly` o `disabled`
- El botón de submit se oculta completamente
- Banner inline en el formulario: "Estás en modo solo lectura. Suscríbete para editar."

Esto permite al usuario ver los detalles de un registro en el formulario, pero no modificarlos.
Es mejor UX que un error 403 en el GET.

### Patrón Jinja2
```jinja
{# Botones de acción en lista #}
{% if not is_read_only %}
  <a href="/expenses/nuevo" class="btn btn-primary">Nueva gasto</a>
{% endif %}

{# Campos de formulario #}
<input type="text" name="concepto" value="{{ expense.concepto }}"
       {{ 'readonly' if is_read_only else '' }}>

{# Submit #}
{% if not is_read_only %}
  <button type="submit" class="btn btn-primary">Guardar</button>
{% endif %}
```

## Plan de implementación

### Fase 1 — Modelo y configuración
1. Añadir `plan: Optional[str]` a `Tenant` (valores: `"basic"` | `"premium"` | `"enterprise"` | `None`)
2. Migración `0016_add_plan_to_tenants.py` con `UPDATE tenants SET plan='premium' WHERE subscription_status='active'`
3. `app/config.py`: añadir `STRIPE_PRICE_ID_BASIC`, `STRIPE_PRICE_ID_PREMIUM`, `STRIPE_PRICE_ID_ENTERPRISE`; `TRIAL_DAYS=30`; deprecar `STRIPE_PRICE_ID`

### Fase 2 — app/plan_access.py (nuevo)
4. `get_plan_mode(user) -> str`
5. `is_read_only(user) -> bool`
6. `has_feature(user, feature) -> bool`
   - Internamente: `plan_effective = "basic"` si `read_only`, luego aplicar matriz
7. Dependencias FastAPI:
   - `require_write_access`: bloquea si `is_read_only(user)` → HTTP 403 con flash message
   - `require_feature(feature)`: factory; lanza `PlanUpgradeRequiredException` si `not has_feature(user, feature)`
   - `require_plant_limit`: bloquea si `plan=="basic"` (o `read_only`) y `count(plants) >= 500`
8. Simplificar `is_subscription_blocked` en `auth.py` — ya no bloquea del todo, cede al nuevo sistema
9. Almacenar `plan_mode` en session en `get_current_user`

### Fase 3 — Billing (3 planes)
10. `billing_service.py`:
    - `create_checkout_session(tenant, user, plan, db)` con plan; dict `PRICE_ID_TO_PLAN = {STRIPE_PRICE_ID_BASIC: "basic", ...}`
    - Webhook `checkout.session.completed`: `tenant.plan = metadata["plan"]`
    - Webhook `customer.subscription.updated`: resolver plan desde `price_id` vía `PRICE_ID_TO_PLAN`, actualizar `tenant.plan`
    - Webhook `customer.subscription.deleted`: `tenant.plan = None`
11. `billing.py` router: `POST /billing/checkout` acepta form field `plan` (validado contra enum)
12. `billing/subscribe.html`: 3 cards de planes con precios, features y CTA; plan recomendado destacado

### Fase 4 — Guards en routers
13. `require_write_access` en todos los POST de crear/editar/borrar de:
    `plots`, `expenses`, `incomes`, `recurring_expenses`, `plants`, `plot_events`, `wells`,
    `irrigation` (excl. GET /simular), `imports`, `scan`. `exports.py` libre.
14. `require_feature("lluvia")` en `lluvia.py` — read_only puede ver (GET) pero no escribir (POST bloqueado por step 13)
15. `require_feature("asistente_ia")` en `assistant.py`
16. `require_feature("simulador_riego")` en `GET /irrigation/simular`
17. `require_feature("tiempo")` en `weather.py`
18. `require_feature("analitica_parcelas")` en `plot_analytics.py`
19. `require_feature("tenants")` en POST de invitar/quitar miembros en `tenants.py`; `GET /tenant/settings` libre
20. `require_plant_limit` en POST de creación de planta individual
    + lógica de límite en `plants_service` y `plots_service` para update de num_plants e import

### Fase 5 — UI y templates
21. `app/jinja.py`: globals `plan_mode`, `is_read_only`, `has_feature` disponibles en todas las templates
22. `base.html`: banner contextual por estado con mensaje y CTA distintos según estado:
    - trial: "X días de prueba restantes"
    - read_only + trial expirado: "Tu período de prueba ha terminado. Suscríbete para editar."
    - read_only + past_due: "Problema con tu pago. Actualiza tu método de pago."
    - read_only + canceled: "Suscripción cancelada. Reactiva para editar."
    - Badge del plan activo en nav (Trial / Básico / Premium / Enterprise)
23. Exception handler global para `PlanUpgradeRequiredException` → template reutilizable "Función no disponible en tu plan" con CTA de upgrade
24. En formularios: campos `readonly`/`disabled` + submit oculto cuando `is_read_only`
25. En listas: ocultar botones de crear/editar/eliminar cuando `is_read_only`

### Fase 6 — Tests
26. `tests/services/test_plan_access.py` — tests unitarios para toda la matriz
    (`get_plan_mode`, `has_feature`, `is_read_only`, todos los estados)
27. `tests/services/test_plant_limit.py` — tests unitarios para los 3 casos del límite de plantas
28. Actualizar `tests/test_billing_router.py` para 3 planes (parámetro plan, plan inválido → 422)
29. Tests de webhook con metadata de plan en billing service
30. Tests de integración: POST devuelve 403 en read_only; feature bloqueada devuelve página de upgrade

## Archivos a modificar
- `app/models/tenant.py` — campo `plan`
- `alembic/versions/0016_add_plan_to_tenants.py` — nuevo
- `app/config.py` — 3 price IDs, TRIAL_DAYS=30
- `app/plan_access.py` — NUEVO
- `app/auth.py` — simplificar `is_subscription_blocked`, añadir `plan_mode` a session
- `app/services/billing_service.py` — 3 planes, webhook handling de plan
- `app/services/plants_service.py` — límite de plantas en update e import
- `app/services/plots_service.py` — límite de plantas al actualizar num_plants
- `app/routers/billing.py` + `app/templates/billing/subscribe.html` — UI 3 planes
- `app/routers/plots.py`, `expenses.py`, `incomes.py`, `recurring_expenses.py`, `plants.py`,
  `plot_events.py`, `wells.py`, `irrigation.py`, `imports.py`, `scan.py` → `require_write_access`
- `app/routers/lluvia.py` → `require_feature("lluvia")`
- `app/routers/assistant.py` → `require_feature("asistente_ia")`
- `app/routers/weather.py` → `require_feature("tiempo")`
- `app/routers/plot_analytics.py` → `require_feature("analitica_parcelas")`
- `app/routers/tenants.py` → `require_feature("tenants")` en write ops
- `app/jinja.py`
- `app/templates/base.html`
- `app/templates/` (formularios y listas afectados por read_only)
- `tests/` — nuevos y actualizados
