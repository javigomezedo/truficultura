---
description: Cuando hagas cambios en los ficheros de la carpeta `app/services/`, sigue estas pautas para mantener la calidad y coherencia del código.
applyTo: **/app/services/**
---

## Cobertura de tests obligatoria

Cada vez que añadas o modifiques una función en `app/services/`, **debes**:

1. **Revisar si ya existe un test** que cubra esa función en `tests/services/` (tests unitarios) o en `tests/integration/` (tests de integración).
2. **Si no existe cobertura**, crear los tests necesarios antes de dar la tarea por terminada.
3. **Ejecutar la suite completa** al final para confirmar que todo sigue verde:
   ```bash
   .venv/bin/python -m pytest -q tests/
   ```

---

## Dónde y cómo escribir los tests

### Tests unitarios → `tests/services/`

- Un fichero por servicio: `test_<nombre>_service.py`.
- **No usar `AsyncMock` directamente para la sesión**. Usar el patrón `FakeExecuteResult` / `result()` de `tests/conftest.py`:

```python
from unittest.mock import AsyncMock, MagicMock
from tests.conftest import result

db = MagicMock()
db.execute = AsyncMock(return_value=result([objeto1, objeto2]))
```

- Si la función llama a `db.flush`, `db.delete`, `db.add`, mockearlos también:

```python
db.flush = AsyncMock()
db.delete = AsyncMock()
```

- Decorar siempre con `@pytest.mark.asyncio`.
- Importar desde `app.services.<módulo>` sólo las funciones que se van a testear.

### Tests de integración → `tests/integration/`

Usar integración cuando la lógica dependa de relaciones entre modelos, ordenaciones reales de la BD o migraciones. Se usa SQLite en memoria con `aiosqlite`:

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.database import Base

engine = create_async_engine("sqlite+aiosqlite:///:memory:")
async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
```

---

## Qué testear en cada caso

| Tipo de cambio | Tests mínimos requeridos |
|---|---|
| Nueva función `get_*` | Caso encontrado + caso no encontrado (None / lista vacía) |
| Nueva función `create_*` | Verifica `db.add` llamado, objeto devuelto con campos correctos |
| Nueva función `update_*` | Verifica que los campos del objeto cambian |
| Nueva función `delete_*` | Verifica `db.delete` llamado con el objeto correcto |
| Nueva función de agregación / contexto | Verifica totales, filtros por `user_id` y por campaña |
| Cambio en lógica de negocio existente | Actualiza o añade casos que cubran la nueva rama |

---

## Reglas generales

- **Siempre filtrar por `user_id`** en las queries; los tests deben pasar `user_id` y verificar que el filtro existe.
- Los tests deben ser **independientes entre sí** (sin estado compartido).
- Nombres descriptivos: `test_<función>_<escenario>`, p. ej. `test_get_plot_not_found`.
- No testear detalles de implementación de SQLAlchemy; testear el **contrato** de la función (qué devuelve, qué efectos secundarios tiene).
