# Plan: Integración de Stripe (Trial 14 días + Suscripción Anual)

**TL;DR:** Capa de control de suscripción por encima del `require_user` existente. Stripe gestiona el cobro; webhooks actualizan el estado en BD; `require_subscription` protege los 18 routers de datos. Trial gestionado por la app (sin tarjeta al registrarse). 9 fases independientemente verificables.

---

## Fase 1 — Modelo de datos + migración `0019`

1. Añadir 4 campos a `User` en `app/models/user.py`:
   - `stripe_customer_id: Mapped[str | None]` — nullable, unique
   - `subscription_status: Mapped[str]` — `"trialing"` | `"active"` | `"past_due"` | `"canceled"`, default `"trialing"`
   - `trial_ends_at: Mapped[datetime | None]`
   - `subscription_ends_at: Mapped[datetime | None]`

2. Migración `alembic/versions/0019_add_subscription_fields_to_users.py`:
   - `upgrade()`: 4 `op.add_column` + data migration: usuarios existentes confirmados → `subscription_status="trialing"`, `trial_ends_at = created_at + 30 días` (periodo de gracia para usuarios ya existentes)
   - `downgrade()`: elimina los 4 campos

---

## Fase 2 — Configuración Stripe

3. Añadir `stripe>=10.0.0` a `pyproject.toml`

4. Añadir a `Settings` en `app/config.py`:
   - `STRIPE_SECRET_KEY: Optional[str] = None`
   - `STRIPE_PUBLISHABLE_KEY: Optional[str] = None`
   - `STRIPE_WEBHOOK_SECRET: Optional[str] = None`
   - `STRIPE_PRICE_ID: Optional[str] = None`
   - `TRIAL_DAYS: int = 14`

5. Actualizar `.env.example` con las nuevas vars

---

## Fase 3 — Servicio de facturación

6. Crear `app/services/billing_service.py`:
   - `start_trial(user, db)` — setea `subscription_status="trialing"`, `trial_ends_at=now+TRIAL_DAYS`
   - `get_or_create_stripe_customer(user, db)` — crea cliente en Stripe si no existe, persiste `stripe_customer_id`
   - `create_checkout_session(user, db) → str` — URL de Stripe Checkout (pago anual, sin trial en Stripe; el trial lo gestiona la app)
   - `create_portal_session(user) → str` — URL del Customer Portal para suscriptores activos
   - `handle_webhook(payload: bytes, stripe_signature: str, db)` — verifica firma y despacha:
     - `checkout.session.completed` → `status="active"`, setea `subscription_ends_at`
     - `invoice.paid` → renueva `subscription_ends_at`
     - `invoice.payment_failed` → `status="past_due"`
     - `customer.subscription.deleted` → `status="canceled"`

---

## Fase 4 — Router de facturación *(paralelo con Fase 3)*

7. Crear `app/routers/billing.py`:
   - `GET /billing/subscribe` — pricing page (usa `require_user`, NO `require_subscription`)
   - `POST /billing/checkout` — crea checkout session, redirige a Stripe
   - `GET /billing/success` — confirmación post-pago
   - `GET /billing/cancel` — vuelta atrás sin pagar
   - `GET /billing/portal` — Customer Portal para suscriptores activos
   - `POST /stripe/webhook` — sin auth; cuerpo raw (`Request.body()`), verifica `Stripe-Signature`

8. Registrar router en `app/main.py`

---

## Fase 5 — Control de acceso *(depende de Fase 3)*

9. Añadir a `app/auth.py`:
   - `class SubscriptionRequiredException(Exception)`
   - `async def require_subscription(user = Depends(require_user)) → User`: admin → pasa; trialing + `trial_ends_at > now` → pasa; active + `subscription_ends_at > now` → pasa; resto → raise

10. Handler en `app/main.py`: `SubscriptionRequiredException` → `RedirectResponse("/billing/subscribe", 303)`

11. Sustituir `require_user` → `require_subscription` en los 18 routers de datos:
    `irrigation`, `plots`, `lluvia`, `plot_events`, `plants`, `aemet_admin`, `wells`, `kpis`,
    `recurring_expenses`, `scan`, `charts`, `reports`, `plot_analytics`, `expenses`,
    `imports`, `exports`, `harvests`, `incomes` *(pueden hacerse en paralelo)*

12. `app/routers/auth.py` — en `/register/confirm/{token}`: llamar `billing_service.start_trial(user, db)` antes del redirect al dashboard

---

## Fase 6 — UI *(paralelo con Fase 5)*

13. `app/templates/billing/subscribe.html` — tarjeta de pricing con precio anual, beneficios, CTA. Según estado: badge "X días de prueba restantes", mensaje de reactivación para `past_due`/`canceled`
14. `app/templates/billing/success.html` y `billing/cancel.html`
15. Banner en `app/templates/base.html` — si `subscription_status == "trialing"`: "Te quedan N días de prueba gratuita — [Suscribirse]"

---

## Fase 7 — Panel admin *(paralelo con Fase 6)*

16. Extender `app/templates/admin/users.html` con columnas: `subscription_status`, `trial_ends_at`, `subscription_ends_at`, `stripe_customer_id`

---

## Fase 8 — Tests *(depende de Fases 3-5)*

17. `tests/services/test_billing_service.py` — unit tests para `start_trial` y `handle_webhook` (mock `stripe.Webhook.construct_event` con `unittest.mock.patch`)
18. Actualizar fixtures de usuarios en tests existentes: añadir `subscription_status="active"` para que no fallen con el nuevo gate

---

## Fase 9 — Despliegue por entornos

**Regla clave: la distinción es test vs live, no local vs dev.**

| Entorno | `STRIPE_SECRET_KEY` | `STRIPE_WEBHOOK_SECRET` | Dinero real |
|---|---|---|---|
| Local | `sk_test_...` (compartida) | CLI `whsec_` (temporal, auto) | No |
| DEV | `sk_test_...` (compartida) | `whsec_dev` (propio del endpoint) | No |
| Staging | `sk_test_...` (compartida) | `whsec_staging` (propio) | No |
| Production | `sk_live_...` | `whsec_prod` (propio) | **Sí** |

19. **Local**: test keys en `.env`. Stripe CLI: `stripe listen --forward-to localhost:8000/stripe/webhook` (el CLI genera su propio `whsec_` temporal que va en `STRIPE_WEBHOOK_SECRET` del `.env`)

20. **DEV** (`trufiq-dev`): `fly secrets set STRIPE_SECRET_KEY=sk_test_... STRIPE_WEBHOOK_SECRET=whsec_dev_...`. Registrar `https://trufiq-dev.fly.dev/stripe/webhook` en Stripe Dashboard

21. **Staging** (futuro): misma mecánica que DEV, endpoint propio en Dashboard, `whsec_staging` propio. `STRIPE_PRICE_ID` puede apuntar a un precio de test diferente

22. **Production** (futuro): live keys. Recomendado: proyecto Stripe separado (test project vs live project) para aislar datos

---

## Archivos afectados

- `app/models/user.py` — 4 campos nuevos
- `app/config.py` — 5 vars nuevas
- `pyproject.toml` — añadir `stripe`
- `app/auth.py` — `SubscriptionRequiredException` + `require_subscription`
- `app/main.py` — handler + registrar billing router
- `app/routers/auth.py` — llamar `start_trial` en confirmación email
- `app/services/billing_service.py` — nuevo
- `app/routers/billing.py` — nuevo
- `app/templates/billing/` — 3 templates nuevos (`subscribe.html`, `success.html`, `cancel.html`)
- `app/templates/base.html` — banner trial
- `alembic/versions/0019_add_subscription_fields_to_users.py` — nueva migración

---

## Verificación

1. `pytest tests/` verde tras implementar (con fixtures actualizadas)
2. Unit tests `test_billing_service.py`: `start_trial`, `handle_webhook` para cada evento
3. Manual local: registro → email → confirmar → banner trial visible → "Suscribirse" → Stripe Checkout → tarjeta `4242 4242 4242 4242` → success → dashboard accesible
4. Manual DEV: `fly secrets set` → deploy → probar webhook desde Stripe Dashboard ("Send test webhook")

---

## Decisiones

- **Trial sin tarjeta**: gestionado por la app, no por Stripe → mejor conversión
- **`require_subscription` wrappea `require_user`**: no rompe patrón existente, fácil de revertir
- **Webhook usa `Request.body()` raw**: necesario para verificación de firma de Stripe (no `Body(...)` tipado)
- **Fuera de alcance**: facturas PDF, cupones/descuentos, planes mensuales, multi-seat
