# Plan: Estrategia de testing multi-tenant (local, Docker)

**TL;DR**: La app local ya apunta a Docker (`localhost:5433/trufiq`) con datos reales. Ejecutamos las migraciones ahí, validamos todos los flujos, y si algo falla revertimos con `alembic downgrade`. DEV nunca se toca. El comportamiento de "usuario acepta invitación → pierde sus datos del solo-tenant" es el correcto y esperado.

---

## Prerequisitos

Asegúrate de que Docker está corriendo y la app local apunta al contenedor:
```bash
docker compose up -d db
# .env debe tener:
# DATABASE_URL=postgresql+asyncpg://trufi:trufi@localhost:5433/trufiq
```

---

## Fase A — Ejecutar migración sobre la BD local con datos

**A1 · Snapshot pre-migración**

```bash
psql postgresql://trufi:trufi@localhost:5433/trufiq -c "
SELECT id, username, email FROM users ORDER BY id;
SELECT 'plots'    AS tbl, COUNT(*) FROM plots    UNION ALL
SELECT 'expenses'        , COUNT(*) FROM expenses UNION ALL
SELECT 'incomes'         , COUNT(*) FROM incomes;"
```
Guarda la salida — es tu referencia de comparación post-migración.

**Válido si:** tienes los recuentos antes de tocar nada.

---

**A2 · Ejecutar migraciones 0017 + 0018**

```bash
alembic upgrade head
```

**Válido si:** termina sin errores. Los últimos mensajes confirman `0017` y `0018` ejecutadas.

---

**A3 · Verificar tablas de tenant creadas**

```bash
psql postgresql://trufi:trufi@localhost:5433/trufiq -c "
SELECT COUNT(*) AS total_tenants    FROM tenants;
SELECT COUNT(*) AS total_memberships FROM tenant_memberships;
SELECT u.username, t.name, t.slug, tm.role
FROM users u
JOIN tenant_memberships tm ON tm.user_id = u.id
JOIN tenants t ON t.id = tm.tenant_id
ORDER BY u.id;"
```

**Válido si:** `total_tenants = total_memberships = COUNT(users)`. Todos `role = 'owner'`. Slugs únicos.

---

**A4 · Verificar integridad de datos**

```bash
psql postgresql://trufi:trufi@localhost:5433/trufiq -c "
SELECT u.username,
  (SELECT COUNT(*) FROM plots    WHERE tenant_id = t.id) AS plots,
  (SELECT COUNT(*) FROM expenses WHERE tenant_id = t.id) AS expenses,
  (SELECT COUNT(*) FROM incomes  WHERE tenant_id = t.id) AS incomes
FROM users u
JOIN tenant_memberships tm ON tm.user_id = u.id
JOIN tenants t ON t.id = tm.tenant_id;

-- Sin huérfanos (excepto AEMET):
SELECT COUNT(*) AS plots_sin_tenant    FROM plots    WHERE tenant_id IS NULL;
SELECT COUNT(*) AS expenses_sin_tenant FROM expenses WHERE tenant_id IS NULL;
SELECT COUNT(*) AS aemet_sin_tenant    FROM rainfall_records WHERE tenant_id IS NULL;"
```

**Válido si:** la suma de plots/expenses/incomes coincide con el snapshot de A1. `plots_sin_tenant = 0`, `expenses_sin_tenant = 0`. `aemet_sin_tenant` puede ser > 0 (registros de AEMET sin usuario).

---

**A5 · Verificar migración de Stripe**

```bash
psql postgresql://trufi:trufi@localhost:5433/trufiq -c "
SELECT u.username, t.stripe_customer_id, t.subscription_status,
       t.trial_ends_at, t.subscription_ends_at
FROM users u
JOIN tenant_memberships tm ON tm.user_id = u.id
JOIN tenants t ON t.id = tm.tenant_id
WHERE t.stripe_customer_id IS NOT NULL;"
```

**Válido si:** los `stripe_customer_id` de los tenants coinciden con los que tenían los usuarios en el snapshot de A1.

---

**A6 · Login de usuario existente con la app en local**

```bash
uvicorn app.main:app --reload
```

1. Ir a `http://localhost:8000/login`.
2. Loguearse con una cuenta real de la BD local.
3. Navegar por el dashboard — debe cargar con sus datos habituales (parcelas, gastos, ingresos).
4. Ir a `/tenant/settings` — debe mostrar su organización personal (nombre = su nombre completo).

**Válido si:** sin errores 500. Datos visibles. Settings muestra el tenant.

---

### Reversión si algo falla en la Fase A

```bash
alembic downgrade 0016
# La BD vuelve exactamente al estado pre-migración. No hay que tocar DEV.
```

---

## Fase B — Flujos de usuario (app local en http://localhost:8000)

> Todos los escenarios usan la BD local Docker con los datos post-migración.

**B1 · Registro nuevo → solo-tenant automático**
1. Ir a `/register` → crear nuevo usuario con un email no existente.
2. Loguearse y navegar a `/tenant/settings`.

**Válido si:**
```bash
psql postgresql://trufi:trufi@localhost:5433/trufiq -c "
SELECT t.name, t.slug, tm.role
FROM tenant_memberships tm JOIN tenants t ON t.id = tm.tenant_id
WHERE tm.user_id = (SELECT id FROM users WHERE email = '<nuevo_email>');"
```
→ 1 fila con `role = 'owner'`. Nombre de org = nombre del nuevo usuario.

---

**B2 · Aislamiento de datos entre tenants**
1. Loguearse como usuario A (uno de los existentes). Anotar las parcelas y gastos que ve.
2. Cerrar sesión. Loguearse como usuario B (otro usuario existente).

**Válido si:** B no ve ningún dato de A en ninguna sección (parcelas, gastos, ingresos, gráficas, cosecha).

---

**B3 · Invitar a otro usuario**
1. Loguearse como usuario A (owner de su tenant).
2. `/tenant/settings` → campo email → introducir el email del usuario del paso B1 → rol `member` → Enviar.

**Válido si:** redirect `?invited=1`, banner verde. Invitación aparece en la tabla de pendientes. En BD:
```bash
psql postgresql://trufi:trufi@localhost:5433/trufiq -c "
SELECT id, email, role, expires_at, token FROM tenant_invitations ORDER BY id DESC LIMIT 1;"
```

---

**B4 · Aceptar invitación — flujo normal**
1. Copiar el `token` del paso B3.
2. Loguearse como el usuario B1 (el que fue invitado).
3. Acceder a `http://localhost:8000/tenant/join/<token>`.
4. Verificar que aparece el aviso "Abandonarás tu organización actual".
5. Clic en "Aceptar invitación".

**Válido si:** redirect `/?joined=1` + toast. En BD:
```bash
psql postgresql://trufi:trufi@localhost:5433/trufiq -c "
-- B ahora pertenece al tenant de A:
SELECT t.name, tm.role FROM tenant_memberships tm
JOIN tenants t ON t.id = tm.tenant_id
WHERE tm.user_id = (SELECT id FROM users WHERE email = '<email_B1>');

-- No hay tenants huérfanos sin miembros:
SELECT id, name FROM tenants
WHERE id NOT IN (SELECT tenant_id FROM tenant_memberships);"
```
El solo-tenant de B1 fue eliminado automáticamente (no tenía Stripe). Los datos que B1 tenía en ese solo-tenant **no se transfieren** — es el comportamiento correcto.

---

**B5 · Aceptar invitación — email no coincide**
1. Como owner A, crear invitación para `fantasma@noexiste.com`.
2. Loguearse como cualquier otro usuario con email diferente y acceder al token.

**Válido si:** la página muestra el bloque rojo con el email del destinatario. El botón "Aceptar" **no aparece**.

---

**B6 · Token expirado**
```bash
psql postgresql://trufi:trufi@localhost:5433/trufiq -c "
UPDATE tenant_invitations SET expires_at = NOW() - INTERVAL '1 day'
WHERE id = (SELECT id FROM tenant_invitations ORDER BY id DESC LIMIT 1);"
```
Visitar el token en el navegador.

**Válido si:** muestra `join_invalid.html` (HTTP 400).

---

**B7 · Token ya aceptado**
Visitar de nuevo el token del paso B4.

**Válido si:** muestra `join_invalid.html`.

---

**B8 · Invitar email que ya es miembro**
Como owner A, intentar invitar el email de alguien que ya pertenece al tenant.

**Válido si:** redirect `?error=already_member`, banner amarillo.

---

**B9 · Email con formato inválido**
En el campo de invitación introducir `no-es-email`.

**Válido si:** redirect `?error=invalid_email`, banner rojo.

---

**B10 · Cambiar rol member → admin**
Owner A cambia el rol del miembro B1 a "Administrador" usando el desplegable.

**Válido si:** `?saved=1`, badge muestra "Administrador". En BD:
```bash
psql postgresql://trufi:trufi@localhost:5433/trufiq -c "
SELECT role FROM tenant_memberships WHERE user_id = (SELECT id FROM users WHERE email = '<email_B1>');"
```
→ `admin`.

---

**B11 · Intentar cambiar rol del owner (bypass)**
```bash
curl -c /tmp/cookies.txt -b /tmp/cookies.txt \
  -X POST http://localhost:8000/tenant/members/<owner_id>/role \
  -d "role=member" -L -v 2>&1 | grep "Location:"
```
*(Primero hay que loguearse como admin para obtener la cookie de sesión)*

**Válido si:** redirect a `?error=forbidden`.

---

**B12 · Eliminar miembro → solo-tenant recreado**
Owner A hace clic en "Eliminar" en la fila del miembro B1.

**Válido si:** `?saved=1`, B1 desaparece de la lista. En BD:
```bash
psql postgresql://trufi:trufi@localhost:5433/trufiq -c "
SELECT t.name, tm.role FROM tenant_memberships tm
JOIN tenants t ON t.id = tm.tenant_id
WHERE tm.user_id = (SELECT id FROM users WHERE email = '<email_B1>');"
```
→ nuevo solo-tenant con `role = 'owner'`. B1 puede loguearse y navegar por la app sin errores.

---

**B13 · Intentar eliminar al owner (bypass)**
POST a `/tenant/members/<owner_id>/remove` con la sesión de un admin.

**Válido si:** redirect `?error=forbidden`.

---

**B14 · Revocar invitación pendiente**
Crear nueva invitación para `nueva@prueba.com`. Hacer clic en "Revocar".

**Válido si:** `?saved=1`, desaparece de la lista. En BD: `SELECT COUNT(*) FROM tenant_invitations WHERE email = 'nueva@prueba.com'` → 0. Visitar el token → `join_invalid.html`.

---

**B15 · Cambiar nombre de la organización**
Owner A cambia el nombre a "Finca La Prueba" en el campo de nombre.

**Válido si:** `?saved=1`, UI muestra "Finca La Prueba". En BD: `SELECT name FROM tenants WHERE id = <tenant_id>`.

---

**B16 · Miembro sin permisos no puede administrar**
Loguearse como B1 con `role = 'member'` en `/tenant/settings`.

**Válido si:** no aparece la sección de nombre ni botones de gestión. POST bypass a cualquier endpoint de gestión → `?error=forbidden`.

---

**B17 · Dashboard tras aceptar invitación**
B1 logueado tras aceptar la invitación de A.

**Válido si:** el dashboard muestra datos de A (las parcelas y gastos de A). Los datos del antiguo solo-tenant de B1 no están (fueron al tenant borrado — comportamiento esperado).

---

**B18 · Usuario expulsado puede seguir usando la app**
B1 expulsado en B12, vuelve a loguearse.

**Válido si:** sin errores 500. Ve su nuevo solo-tenant vacío. Puede crear una parcela o gasto nuevos y quedan guardados en ese nuevo tenant. Los datos del período en que fue miembro de A **no están** (es correcto — pertenecen al tenant de A).

---

## Fase C — Tests de integración automatizados (después de validar B)

En `tests/integration/`, siguiendo el patrón de `test_services_integration.py` con SQLite + aiosqlite:

- **C1** `test_migration_like_flow` — simula en código la migración 0018: crea usuarios en BD, crea sus tenants y memberships, asigna datos, verifica integridad.
- **C2** `test_full_tenant_lifecycle` — A crea tenant, invita a B, B acepta (solo-tenant de B borrado), A expulsa B, solo-tenant de B recreado, B navega sin errores.
