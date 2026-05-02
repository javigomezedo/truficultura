# Plan: Introducción de Tenants/Empresas

## Decisiones tomadas
- **Modelo**: Opción B — siempre tenant. Usuarios independientes = tenant de 1 persona (transparente).
- **Roles en tenant**: owner / admin / member (3 niveles).
- **Billing**: se mueve al nivel de tenant (stripe_customer_id, subscription_status, trial_ends_at, subscription_ends_at pasan de User → Tenant).
- **Multitenant por usuario**: No. 1 usuario = 1 tenant a la vez.
- **Invitaciones**: por email con enlace/token de unión.

## TL;DR
Introducir una tabla `tenants` como nuevo nivel de aislamiento. Todos los modelos de datos (plots, expenses, incomes, etc.) pasan de `user_id` → `tenant_id`. Los usuarios independientes son transparentemente un tenant de 1 persona. El billing pasa al tenant. Se añaden páginas de gestión de tenant (miembros, invitaciones). Se mantiene el rol `admin` de aplicación (superadmin). Migración: un tenant creado automáticamente por cada usuario existente con sus datos reasignados.

---

## Fase 0 — Modelos de datos (bloquea todas las demás)

### 0.1 Nuevo modelo `Tenant` — tabla `tenants`
Columnas: `id` (PK), `name` String(200), `slug` String(100) unique, `created_at` DateTime(tz),
`stripe_customer_id` String(100) nullable unique, `subscription_status` String(30) default `"trialing"`,
`trial_ends_at` DateTime(tz) nullable, `subscription_ends_at` DateTime(tz) nullable.

### 0.2 Nuevo modelo `TenantMembership` — tabla `tenant_memberships`
Columnas: `id`, `tenant_id` FK→tenants CASCADE, `user_id` FK→users CASCADE,
`role` String(20) (`"owner"` / `"admin"` / `"member"`), `joined_at` DateTime(tz), `invited_by_user_id` FK→users nullable.
UniqueConstraint(tenant_id, user_id). Índices: ix_tenant_membership_user, ix_tenant_membership_tenant.

### 0.3 Nuevo modelo `TenantInvitation` — tabla `tenant_invitations`
Columnas: `id`, `tenant_id` FK→tenants CASCADE, `email` String(255), `token` String(64) unique (token URL-safe generado por `secrets.token_urlsafe`), `invited_by_user_id` FK→users, `role` String(20) default `"member"`, `created_at` DateTime(tz), `expires_at` DateTime(tz), `accepted_at` DateTime(tz) nullable.
Índice: ix_tenant_invitation_tenant.

### 0.4 Modificar `User` — eliminar campos de billing
Eliminar columnas: `stripe_customer_id`, `subscription_status`, `trial_ends_at`, `subscription_ends_at`.
Añadir relación: `membership` → TenantMembership (uselist=False), propiedad calculada `tenant` → Tenant via membership.

### 0.5 Añadir `tenant_id`, `created_by_user_id` y `updated_by_user_id` a todos los modelos con datos
Modelos afectados: `Plot`, `Expense`, `Income`, `Plant`, `TruffleEvent`, `IrrigationRecord`, `Well`, `PlotEvent`, `RecurringExpense`, `RainfallRecord`, `PlotHarvest`, `PlantPresence`, `ExpenseProrationGroup`.

**`tenant_id`**: FK → tenants.id CASCADE. Nullable inicialmente para migración, luego NOT NULL (excepto `RainfallRecord` donde sigue nullable para registros globales AEMET/ibericam). Reemplaza al `user_id` actual como filtro de aislamiento de datos.

**`created_by_user_id`**: FK → users.id SET NULL. Nullable. Indica qué usuario del tenant creó el registro. Si el usuario es eliminado, el campo queda NULL (el registro se conserva).

**`updated_by_user_id`**: FK → users.id SET NULL. Nullable. Indica qué usuario del tenant modificó el registro por última vez. NULL si nunca ha sido actualizado. No aplica a modelos inmutables (`TruffleEvent`, `PlantPresence`) donde solo existe creación; en esos casos solo se añade `created_by_user_id`.

El `user_id` existente en todos estos modelos se **elimina** (reemplazado por `tenant_id` + auditoría).

---

## Fase 1 — Migraciones Alembic (depende de Fase 0)

### 1.1 Migration `0017_add_tenants_and_memberships.py`
- `upgrade()`: CREATE TABLE tenants, tenant_memberships, tenant_invitations. Añadir `tenant_id` (nullable), `created_by_user_id` (nullable FK→users SET NULL) y `updated_by_user_id` (nullable FK→users SET NULL) a Plot, Expense, Income, Plant, TruffleEvent, IrrigationRecord, Well, PlotEvent, RecurringExpense, RainfallRecord, PlotHarvest, PlantPresence, ExpenseProrationGroup. Solo `created_by_user_id` en modelos inmutables (TruffleEvent, PlantPresence).
- `downgrade()`: DROP todas las columnas y tablas añadidas.

### 1.2 Migration `0018_migrate_user_data_to_tenants.py` — DATA MIGRATION
Script que:
1. Para cada User existente: INSERT INTO tenants (name=user.username, slug=user.username, stripe_customer_id=user.stripe_customer_id, subscription_status=user.subscription_status, trial_ends_at=user.trial_ends_at, subscription_ends_at=user.subscription_ends_at).
2. INSERT INTO tenant_memberships (tenant_id=nuevo_tenant.id, user_id=user.id, role="owner", joined_at=now).
3. UPDATE Plot SET tenant_id=tenant.id, created_by_user_id=user.id WHERE user_id=user.id. (repetir para todas las tablas, asignando created_by_user_id=user.id como valor histórico razonable)
4. Para las tablas con `updated_by_user_id`, dejar NULL (no hay información histórica de quién actualizó).
- Ejecutarse en Python puro (op.execute con SQL) dentro del script Alembic.
- `downgrade()`: SET tenant_id=NULL, created_by_user_id=NULL, updated_by_user_id=NULL en todas las tablas; DELETE tenant_memberships; DELETE tenants.

### 1.3 Migration `0019_make_tenant_id_not_null_drop_user_billing.py`
- ALTER COLUMN `tenant_id` SET NOT NULL en todas las tablas (excepto `rainfall_records` donde sigue nullable).
- DROP COLUMN `user_id` de Plot, Expense, Income, Plant, TruffleEvent, IrrigationRecord, Well, PlotEvent, RecurringExpense, PlotHarvest, PlantPresence, ExpenseProrationGroup.
- DROP COLUMN `stripe_customer_id`, `subscription_status`, `trial_ends_at`, `subscription_ends_at` de `users`.
- `downgrade()`: re-añadir las columnas eliminadas como nullable.

---

## Fase 2 — Auth y sesión (depende de Fase 1)

### 2.1 Modificar `app/auth.py`
- `get_current_user()`: tras cargar el User, cargar su TenantMembership → Tenant. Almacenar `tenant_id` y `tenant_role` en `request.session`. Exponer `user.active_tenant` y `user.tenant_role` como atributos en el objeto retornado (o mediante un objeto wrapper `AuthenticatedUser`).
- `require_subscription()`: verificar `tenant.subscription_status` / `tenant.trial_ends_at` en vez de los campos del User.
- Nueva dependencia `require_tenant_owner(current_user)`: lanza excepción si `user.tenant_role != "owner"`.
- Nueva dependencia `require_tenant_admin(current_user)`: lanza excepción si role no es owner ni admin.
- Admins de aplicación (`user.role == "admin"`) siguen bypassando `require_subscription`.

### 2.2 Objeto `AuthenticatedUser` (o extender el User con propiedades)
El objeto `current_user` que pasan los routers debe exponer:
- `current_user.id` → user.id
- `current_user.active_tenant_id` → tenant.id
- `current_user.tenant_role` → "owner" / "admin" / "member"
- `current_user.active_tenant` → objeto Tenant

### 2.3 Modificar `app/routers/auth.py` — registro de nuevos usuarios
Al registrar un usuario nuevo: crear automáticamente un Tenant (nombre = nombre de usuario, slug generado) y crear TenantMembership con role="owner".
El primer usuario sigue siendo `role="admin"` en User (superadmin de la app).

---

## Fase 3 — Nuevos servicios (depende de Fase 0)

### 3.1 Nuevo `app/services/tenant_service.py`
- `get_tenant(db, tenant_id)` → Tenant
- `get_tenant_members(db, tenant_id)` → list[TenantMembership + User]
- `update_tenant(db, tenant_id, data)` → Tenant (nombre, slug)
- `remove_member(db, tenant_id, user_id_to_remove, current_user_id)` (no puede eliminar el owner)
- `change_member_role(db, tenant_id, user_id_to_change, new_role, current_user_id)` (solo owner puede cambiar roles; no puede auto-degradar owner)
- `leave_tenant(db, tenant_id, user_id)` (si es owner y único miembro, se puede; si es owner con más miembros, debe transferir)

### 3.2 Nuevo `app/services/invitation_service.py`
- `create_invitation(db, tenant_id, email, role, invited_by_user_id)` → TenantInvitation (genera token con `secrets.token_urlsafe(32)`, expira en 7 días)
- `get_invitation_by_token(db, token)` → TenantInvitation (verifica no expirada, no aceptada)
- `accept_invitation(db, token, accepting_user_id)` → TenantMembership (si el email coincide con el del User; crea membership y marca accepted_at)
- `list_pending_invitations(db, tenant_id)` → list[TenantInvitation]
- `revoke_invitation(db, invitation_id, tenant_id)` → None

### 3.3 Actualizar `app/services/billing_service.py`
- Todas las operaciones de Stripe pasan de `User` → `Tenant`.
- `get_or_create_stripe_customer(db, tenant)` en vez de `(db, user)`.
- Actualizar `subscription_status`, `trial_ends_at`, `subscription_ends_at` en Tenant.

---

## Fase 4 — Actualizar servicios existentes (depende de Fase 0, paralelo con Fase 3)

En todos los servicios que actualmente reciben `user_id: int` y filtran por `Model.user_id == user_id` se modifican para recibir **dos parámetros del contexto de auth**:
- `tenant_id: int` — aislamiento de datos, reemplaza el filtro anterior `Model.user_id == user_id` → `Model.tenant_id == tenant_id`.
- `acting_user_id: int` — auditoría, se asigna a `created_by_user_id` en creaciones y `updated_by_user_id` en actualizaciones.

Los servicios de solo lectura (list, get) solo necesitan `tenant_id`. Los servicios de escritura (create, update, delete) necesitan ambos.

Concretamente:
- `create_*()` → asignar `tenant_id=tenant_id` y `created_by_user_id=acting_user_id`.
- `update_*()` → asignar `updated_by_user_id=acting_user_id`.
- `delete_*()` → no requiere campo de auditoría adicional.
- `_recalculate_percentages(db, tenant_id)`: filtrar por `Plot.tenant_id == tenant_id`.
- `distribute_unassigned_expenses()`: sin cambios en lógica, solo cambia el filtro.
- `process_recurring_expenses_cron.py`: usa `rec.tenant_id`; al crear el Expense generado asigna `created_by_user_id=None` (origen automático, no hay usuario activo).
- `rainfall_service.py`: `RainfallRecord.tenant_id.is_(None)` para registros globales.
- `admin_service.py` → `get_admin_rainfall_overview`: sigue buscando `tenant_id.is_(None)`.
- `assistant_service.py` → `_build_user_context(db, tenant_id)` y `chat()`.
- `export_service.py` y `import_service.py`: `user_id` → `tenant_id`; en imports asignar `created_by_user_id=acting_user_id`.

Servicios afectados (todos): plots_service, expenses_service, incomes_service, plants_service, irrigation_service, wells_service, plot_events_service, truffle_events_service, recurring_expenses_service, plot_harvest_service, plant_presence_service, rainfall_service, plot_analytics_service, dashboard_service, kpi_service, reports_service, charts_service, weather_service, assistant_service, export_service, import_service.

---

## Fase 5 — Actualizar routers (depende de Fase 2 y Fase 4)

Todos los routers cambian:
- Llamadas de solo lectura: `tenant_id=current_user.active_tenant_id`.
- Llamadas de escritura (create, update): `tenant_id=current_user.active_tenant_id, acting_user_id=current_user.id`.
- `app/routers/billing.py`: operar sobre `current_user.active_tenant` en vez de `current_user`.
- Nuevo `app/routers/tenants.py`: gestión del tenant propio (settings, miembros, invitaciones).
  - `GET /tenant/settings` — ver y editar nombre/slug del tenant (require_tenant_owner)
  - `GET /tenant/members` — lista de miembros y invitaciones pendientes (require_tenant_admin)
  - `POST /tenant/members/invite` — crear invitación por email (require_tenant_admin)
  - `POST /tenant/members/{user_id}/role` — cambiar rol (require_tenant_owner)
  - `POST /tenant/members/{user_id}/remove` — eliminar miembro (require_tenant_admin)
  - `GET /join/{token}` — página pública para aceptar invitación (require_user)
  - `POST /join/{token}` — aceptar invitación (require_user)
  - `DELETE /tenant/invitations/{inv_id}` — revocar invitación (require_tenant_admin)
- `app/routers/admin.py`: añadir gestión de tenants del sistema (listar todos los tenants, ver miembros, gestionar subscripciones).

---

## Fase 6 — Templates y frontend (depende de Fase 5, paralelo)

### 6.1 Modificar `app/templates/base.html`
- Mostrar nombre del tenant activo en la navbar.
- Enlace a "Configuración de empresa" → `/tenant/settings`.

### 6.2 Nuevas templates en `app/templates/tenant/`
- `settings.html` — editar nombre del tenant.
- `members.html` — tabla de miembros (nombre, email, rol, acciones) + lista de invitaciones pendientes + formulario de invitación.
- `join.html` — página de aceptación de invitación (muestra nombre del tenant, botón "Unirme").

### 6.3 Modificar templates de admin
- `app/templates/admin/users.html`: mostrar el tenant de cada usuario.
- Nueva `app/templates/admin/tenants.html`: lista de todos los tenants del sistema.

### 6.4 Email de invitación
- Nuevo template de email para invitación (Postmark): nombre del invitador, nombre del tenant, enlace con token.
- Usar `email_service.py` existente para envío.

---

## Fase 7 — Tests (depende de todas las fases anteriores)

### 7.1 Actualizar `tests/conftest.py`
- Añadir helpers para crear un `FakeTenant` y `FakeMembership` en tests unitarios.

### 7.2 Actualizar tests unitarios en `tests/services/`
- En cada archivo de test de servicios: cambiar `user_id=1` → `tenant_id=1` en llamadas y mocks.

### 7.3 Nuevos tests
- `tests/services/test_tenant_service.py`
- `tests/services/test_invitation_service.py`
- `tests/test_tenants_router.py`

### 7.4 Actualizar tests de routers existentes
- Todos los tests de routers que mockean `require_user` y pasan `current_user.id` deben actualizarse para incluir `active_tenant_id`.

---

## Archivos críticos a modificar

| Archivo | Cambio |
|---|---|
| `app/models/` (todos) | Eliminar `user_id`, añadir `tenant_id` FK |
| `app/models/user.py` | Eliminar campos billing, añadir relación membership |
| `app/auth.py` | Cargar tenant en sesión, nuevas dependencias de rol |
| `app/routers/auth.py` | Crear tenant al registrar usuario |
| `app/routers/billing.py` | Billing sobre Tenant |
| `app/services/billing_service.py` | Billing sobre Tenant |
| Todos los services en `app/services/` | user_id → tenant_id + acting_user_id para auditoría |
| Todos los routers en `app/routers/` | current_user.id → current_user.active_tenant_id |
| `scripts/process_recurring_expenses_cron.py` | rec.user_id → rec.tenant_id |
| `alembic/versions/` | 3 nuevas migraciones (0017, 0018, 0019) |

Nuevos archivos:
- `app/models/tenant.py`
- `app/services/tenant_service.py`
- `app/services/invitation_service.py`
- `app/routers/tenants.py`
- `app/templates/tenant/settings.html`
- `app/templates/tenant/members.html`
- `app/templates/tenant/join.html`
- `alembic/versions/0017_add_tenants_and_memberships.py`
- `alembic/versions/0018_migrate_user_data_to_tenants.py`
- `alembic/versions/0019_make_tenant_id_not_null_drop_user_billing.py`
- `tests/services/test_tenant_service.py`
- `tests/services/test_invitation_service.py`
- `tests/test_tenants_router.py`

---

## Verificación

1. `uv run pytest` → todos los tests existentes pasan (actualización de fixtures con tenant_id).
2. Nuevo registro: crear usuario → tenant automático creado → membresía owner.
3. Flujo invitación: owner invita por email → usuario recibe email → accede a `/join/{token}` → acepta → puede ver datos del tenant.
4. Datos aislados: user A (tenant A) no ve datos de user B (tenant B).
5. `alembic upgrade head` en DB vacía: OK.
6. `alembic upgrade head` en DB con datos existentes: 0018 migra correctamente.
7. Billing: checkout Stripe se crea a nivel de tenant; webhook actualiza tenant.subscription_status.
8. Cron `process_recurring_expenses_cron.py`: genera gastos con tenant_id correcto.

---

## Alcance incluido
- Modelo Tenant + Membership + Invitation
- Flujo de invitación por email
- Gestión de miembros y roles (owner/admin/member)
- Migración de datos existentes (0017 → 0018 → 0019)
- Billing al nivel de tenant
- Roles de tenant en dependencias auth
- Auditoría created_by_user_id / updated_by_user_id en todos los modelos de datos

## Alcance excluido (v1)
- Cambio de tenant activo en sesión (usuarios pertenecen a 1 solo tenant)
- Transferencia de ownership entre miembros (puede añadirse después)
- Panel de facturación multi-tenant en admin (más allá de listar tenants)
- SSO / OAuth para tenants corporativos
