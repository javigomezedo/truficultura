# Plan de test exhaustivo — Implementación de planes Trufiq

## Setup previo

```sql
-- Trial activo
UPDATE tenants SET subscription_status='trialing',
  trial_ends_at=NOW()+INTERVAL '14 days', plan=NULL WHERE id=X;

-- read_only (trial expirado)
UPDATE tenants SET subscription_status='trialing',
  trial_ends_at=NOW()-INTERVAL '1 day' WHERE id=X;

-- Basic activo
UPDATE tenants SET subscription_status='active', plan='basic',
  subscription_ends_at=NOW()+INTERVAL '365 days' WHERE id=X;

-- Premium activo
UPDATE tenants SET subscription_status='active', plan='premium',
  subscription_ends_at=NOW()+INTERVAL '365 days' WHERE id=X;

-- Enterprise activo
UPDATE tenants SET subscription_status='active', plan='enterprise',
  subscription_ends_at=NOW()+INTERVAL '365 days' WHERE id=X;

-- past_due
UPDATE tenants SET subscription_status='past_due' WHERE id=X;
```

---

## BLOQUE 1 — Modos de acceso (get_plan_mode)

### 1.1 Trial activo
```sql
UPDATE tenants SET subscription_status='trialing',
  trial_ends_at=NOW() + INTERVAL '7 days' WHERE id=<tid>;
```
- [ ] Badge navbar: "Prueba – X días restantes"
- [ ] `/billing/subscribe` → mensaje en verde "Tu período de prueba…"
- [ ] Acceso a `/weather/`, `/plot-analytics/`, `/assistant/`, `/tenant/` (todas las features disponibles)
- [ ] Botones crear/editar/borrar **visibles** en todas las listas
- [ ] Botón submit **visible** en todos los formularios

### 1.2 Trial expirado → read_only
```sql
UPDATE tenants SET subscription_status='trialing',
  trial_ends_at=NOW() - INTERVAL '1 day' WHERE id=<tid>;
```
- [ ] Banner rojo persistente en base.html ("Tu suscripción ha finalizado…")
- [ ] Badge navbar: "Solo lectura" (o equivalente)
- [ ] `/billing/subscribe` → mensaje "Tu periodo de prueba ha finalizado. Elige un plan…"
- [ ] Botones "Nueva Parcela", "Nuevo Gasto", "Nuevo Ingreso", etc. → **ocultos** en todas las listas
- [ ] Botones editar/eliminar en filas → **ocultos**
- [ ] Submit en formularios → **oculto** (navega directamente a `/plots/new`, `/expenses/new`, etc.)
- [ ] POST `/plots/` → **403/redirect** (require_write_access bloquea)
- [ ] POST `/expenses/` → **403/redirect**
- [ ] Tabs de importación en `/imports/` → **ocultos**, solo aparece alerta
- [ ] Listas de parcelas, gastos, ingresos → **cargan correctamente** (lectura OK)

### 1.3 past_due → read_only
```sql
UPDATE tenants SET subscription_status='past_due' WHERE id=<tid>;
```
- [ ] Banner rojo persistente
- [ ] Botones de escritura **ocultos**
- [ ] POST bloqueados por require_write_access

### 1.4 canceled → read_only
```sql
UPDATE tenants SET subscription_status='canceled' WHERE id=<tid>;
```
- [ ] Mismos puntos que 1.3

### 1.5 Active Basic
```sql
UPDATE tenants SET subscription_status='active', plan='basic',
  subscription_ends_at=NOW() + INTERVAL '365 days' WHERE id=<tid>;
```
- [ ] Badge navbar: "Basic"
- [ ] `/billing/subscribe` → tarjeta Basic con "Tu plan actual"
- [ ] Botones crear/editar/borrar **visibles**
- [ ] Submit en formularios **visible**
- [ ] Límite plantas: 500 (ver Bloque 3)
- [ ] `/weather/` → **403/upgrade** (requiere Premium)
- [ ] `/plot-analytics/` → **403/upgrade**
- [ ] `/assistant/` → **403/upgrade**
- [ ] `/tenant/` → **403/upgrade** (requiere Enterprise)

### 1.6 Active Premium
```sql
UPDATE tenants SET subscription_status='active', plan='premium',
  subscription_ends_at=NOW() + INTERVAL '365 days' WHERE id=<tid>;
```
- [ ] Badge navbar: "Premium"
- [ ] `/billing/subscribe` → tarjeta Premium con "Tu plan actual"
- [ ] `/weather/` → **accesible** ✅
- [ ] `/plot-analytics/` → **accesible** ✅
- [ ] `/assistant/` → **accesible** ✅
- [ ] `/tenant/` → **403/upgrade** (solo Enterprise)
- [ ] Límite plantas: **ilimitado** (ver Bloque 3)

### 1.7 Active Enterprise
```sql
UPDATE tenants SET subscription_status='active', plan='enterprise',
  subscription_ends_at=NOW() + INTERVAL '365 days' WHERE id=<tid>;
```
- [ ] Badge navbar: "Enterprise"
- [ ] `/billing/subscribe` → tarjeta Enterprise con "Tu plan actual"
- [ ] `/tenant/` → **accesible** ✅ (gestión multi-tenant)
- [ ] Todas las features desbloqueadas

### 1.8 Active con subscription_ends_at en el pasado → read_only
```sql
UPDATE tenants SET subscription_status='active', plan='basic',
  subscription_ends_at=NOW() - INTERVAL '1 day' WHERE id=<tid>;
```
- [ ] Banner rojo (suscripción expirada aunque status='active')
- [ ] Mismos puntos que 1.2

### 1.9 Usuario admin
- [ ] `get_plan_mode` retorna "enterprise" sin importar `subscription_status`
- [ ] Acceso a **todas** las features sin restricción
- [ ] Gestión de usuarios en `/admin/users/`

---

## BLOQUE 2 — UI read_only (verificación visual por página)

Con usuario en modo **read_only** (escenario 1.2), navegar a cada página:

| Página | Qué verificar |
|--------|---------------|
| `/plots/` | "Nueva Parcela" **oculto** · Mapa/QR **visibles** · editar/eliminar en dropdown **ocultos** · "Crear primera parcela" (vacío) **oculto** |
| `/plots/new` | Formulario carga · submit **oculto** |
| `/plots/<id>/edit` | Formulario carga · submit **oculto** |
| `/expenses/` | "Nuevo Gasto" **oculto** · editar/eliminar **ocultos** |
| `/expenses/new` | Submit **oculto** |
| `/incomes/` | "Nuevo Ingreso" **oculto** |
| `/incomes/new` | Submit **oculto** |
| `/recurring-expenses/` | "Nuevo Gasto Recurrente" **oculto** · botones inline (editar/toggle/eliminar) **ocultos** |
| `/recurring-expenses/new` | Submit **oculto** |
| `/lluvia/` | "Registro manual" **oculto** · botón calendario **visible** · editar/eliminar manuales **ocultos** |
| `/lluvia/new` | Submit **oculto** |
| `/wells/` | "Nuevo registro de pozos" **oculto** |
| `/wells/new` | Submit **oculto** |
| `/plot-events/list` | "Nuevo evento" **oculto** |
| `/plot-events/new` | Submit **oculto** |
| `/irrigation/` | "Nuevo registro" y "Registrar factura" **ocultos** |
| `/irrigation/new` | Submit **oculto** |
| `/irrigation/bulk` | Submit **oculto** |
| `/imports/` | Tabs importación **ocultos** · alerta warning visible |
| `/harvests/` | "Registrar cosecha" **oculto** |
| `/harvests/new` | Submit **oculto** |
| `/harvests/<id>/edit` | Submit **oculto** |

---

## BLOQUE 3 — Límite de plantas (Basic, 500)

### 3.1 Basic con < 500 plantas
```sql
UPDATE tenants SET subscription_status='active', plan='basic',
  subscription_ends_at=NOW() + INTERVAL '365 days' WHERE id=<tid>;
-- Verificar que sum(num_plants) en plots < 500
```
- [ ] Crear nueva parcela con `num_plants=50` → **funciona**
- [ ] Importar CSV con plantas → **funciona**

### 3.2 Basic con = 500 plantas (límite exacto)
```sql
-- Ajustar num_plants en plots hasta sumar exactamente 500
```
- [ ] Crear parcela con cualquier `num_plants > 0` → error "Has alcanzado el límite de 500 plantas"
- [ ] Importar CSV con plantas → error con mensaje de límite
- [ ] Crear parcela con `num_plants=0` → **permitido** (no suma al límite)

### 3.3 Premium con > 500 plantas
```sql
UPDATE tenants SET plan='premium' WHERE id=<tid>;
```
- [ ] Crear parcela con num_plants adicionales → **sin error** (ilimitado)

### 3.4 Trial con > 500 plantas
- [ ] Sin restricción de plantas durante el trial

---

## BLOQUE 4 — Flujo Stripe Checkout

> Requiere variables de entorno configuradas: `STRIPE_PRICE_ID_BASIC`, `STRIPE_PRICE_ID_PREMIUM`, `STRIPE_PRICE_ID_ENTERPRISE`, `STRIPE_PUBLISHABLE_KEY`.
> Usar tarjeta test: `4242 4242 4242 4242`, cualquier CVC/fecha futura.

### 4.1 Checkout Basic
1. Usuario en trial o read_only → ir a `/billing/subscribe`
2. Click "Suscribirse" en tarjeta Basic → POST `/billing/checkout` con `plan=basic`
- [ ] Redirección a `checkout.stripe.com`
- [ ] Stripe Dashboard: `metadata.plan = "basic"`, `line_items[0].price = STRIPE_PRICE_ID_BASIC`
- [ ] Completar pago con tarjeta test
- [ ] Webhook `checkout.session.completed` recibido (ver Bloque 5)
- [ ] `tenant.subscription_status = 'active'`, `tenant.plan = 'basic'`
- [ ] `tenant.subscription_ends_at` rellenado
- [ ] Email de activación enviado
- [ ] Al volver a la app: badge "Basic", acceso correcto

### 4.2 Checkout Premium
- [ ] `metadata.plan = "premium"`, price = `STRIPE_PRICE_ID_PREMIUM`
- [ ] Tras webhook: `tenant.plan = 'premium'`
- [ ] Features premium desbloqueadas

### 4.3 Checkout Enterprise
- [ ] `metadata.plan = "enterprise"`, price = `STRIPE_PRICE_ID_ENTERPRISE`
- [ ] Tras webhook: `tenant.plan = 'enterprise'`
- [ ] `/tenant/` accesible

### 4.4 Plan inválido en POST
```bash
curl -X POST http://localhost:8000/billing/checkout \
  -d "plan=hacker_plan" -b <cookies>
```
- [ ] Router normaliza a `"basic"` → checkout con price Basic

### 4.5 Stripe no configurado
```bash
# Eliminar STRIPE_SECRET_KEY temporalmente
```
- [ ] POST `/billing/checkout` → **503**
- [ ] POST `/billing/portal` → **503**

---

## BLOQUE 5 — Webhooks Stripe

> Activar escucha: `stripe listen --forward-to localhost:8000/billing/stripe/webhook`

### 5.1 `checkout.session.completed`
- [ ] `tenant.subscription_status = 'active'`
- [ ] `tenant.plan` = valor de `metadata.plan`
- [ ] `tenant.subscription_ends_at` rellenado desde `sub.current_period_end`
- [ ] Email de activación enviado al owner del tenant

### 5.2 `invoice.paid` — primera factura (subscription_create)
`stripe trigger invoice.paid`
- [ ] `tenant.subscription_status = 'active'`
- [ ] `tenant.subscription_ends_at` actualizado
- [ ] **Sin** email de renovación (billing_reason ≠ subscription_cycle)

### 5.3 `invoice.paid` — renovación anual (subscription_cycle)
- [ ] `tenant.subscription_status = 'active'`
- [ ] `tenant.subscription_ends_at` actualizado (+1 año)
- [ ] Email de renovación enviado al owner

### 5.4 `invoice.payment_failed`
`stripe trigger invoice.payment_failed`
- [ ] `tenant.subscription_status = 'past_due'`
- [ ] UI pasa a read_only (banner rojo, sin botones escritura)
- [ ] Email de pago fallido enviado

### 5.5 `customer.subscription.deleted` (cancelación inmediata)
`stripe trigger customer.subscription.deleted`
- [ ] `tenant.subscription_status = 'canceled'`
- [ ] UI pasa a read_only
- [ ] Email de cancelación enviado

### 5.6 `customer.subscription.updated` — cancelación al final del período
- [ ] `subscription_status` sigue `'active'` hasta `current_period_end`
- [ ] Email de cancelación enviado
- [ ] Tras expirar `subscription_ends_at`: modo read_only en siguiente login

### 5.7 Webhook con firma inválida
```bash
curl -X POST http://localhost:8000/billing/stripe/webhook \
  -H "stripe-signature: bad" -d '{}'
```
- [ ] Respuesta **400**

### 5.8 STRIPE_WEBHOOK_SECRET no configurado
```bash
# Eliminar STRIPE_WEBHOOK_SECRET temporalmente
curl -X POST http://localhost:8000/billing/stripe/webhook \
  -H "stripe-signature: t=1,v1=abc" -d '{}'
```
- [ ] Respuesta **503**

### 5.9 customer_id desconocido en webhook
- [ ] No lanza excepción, simplemente no hace nada (log warning)
- [ ] `db.commit` **no** llamado

---

## BLOQUE 6 — Portal de facturación

### 6.1 Flujo normal
1. Usuario con `stripe_customer_id` → POST `/billing/portal`
- [ ] Redirección a `billing.stripe.com/session/…`
- [ ] En portal: puede ver facturas, cambiar método de pago, cancelar

### 6.2 Cancelar desde portal
- [ ] Webhook `customer.subscription.deleted` recibido → `status='canceled'` → read_only

### 6.3 Sin customer_id
```sql
UPDATE tenants SET stripe_customer_id=NULL WHERE id=<tid>;
```
- [ ] POST `/billing/portal` → **503**

---

## BLOQUE 7 — Feature gating por plan

### Basic activo — accesos bloqueados
| URL | Método | Resultado esperado |
|-----|--------|--------------------|
| `/weather/` | GET | 403 / redirect upgrade |
| `/plot-analytics/` | GET | 403 / redirect upgrade |
| `/assistant/` | GET | 403 / redirect upgrade |
| `/tenant/` | GET | 403 / redirect upgrade |

### Premium activo — accesos correctos
| URL | Resultado esperado |
|-----|--------------------|
| `/weather/` | 200 ✅ |
| `/plot-analytics/` | 200 ✅ |
| `/assistant/` | 200 ✅ |
| `/tenant/` | 403 ✅ (solo Enterprise) |

### Enterprise activo — acceso total
| URL | Resultado esperado |
|-----|--------------------|
| `/weather/` | 200 ✅ |
| `/plot-analytics/` | 200 ✅ |
| `/assistant/` | 200 ✅ |
| `/tenant/` | 200 ✅ |

---

## BLOQUE 8 — Multitenancy (sin cross-contamination)

1. Crear dos tenants: tenant A (Basic) y tenant B (Premium)
- [ ] Usuario de tenant A no ve datos de tenant B
- [ ] Cambiar plan de tenant A no afecta tenant B
- [ ] Webhook de `cus_A` solo actualiza tenant A
- [ ] Webhook de customer desconocido → log warning, sin crash

---

## BLOQUE 9 — Regresión (funcionalidad core intacta)

Con usuario en **Trial** o **Premium** (escritura habilitada):
- [ ] Crear/editar/eliminar parcela funciona
- [ ] Crear/editar/eliminar gasto funciona  
- [ ] Crear/editar/eliminar ingreso funciona
- [ ] Crear/editar/eliminar gasto recurrente funciona
- [ ] Importar CSV de parcelas funciona
- [ ] Importar CSV de gastos/ingresos funciona
- [ ] Dashboard carga con gráficos
- [ ] Exportar datos funciona
- [ ] Registro manual de lluvia funciona
- [ ] Registro de pozos funciona
- [ ] Registro de riego funciona
- [ ] Eventos de parcela funcionan
- [ ] Suite automatizada: `920 passed` sin regresiones
