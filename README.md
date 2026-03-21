# Truficultura

Aplicación web para la gestión de una explotación trufícola: parcelas, gastos, ingresos, rentabilidad por campañas y gráficas de evolución.

## 1. Resumen del proyecto

Truficultura permite registrar y analizar la actividad económica de una explotación de trufa con una lógica de campañas agrícolas (de abril a marzo).

### Qué resuelve

- Gestión de parcelas (bancales) con datos de superficie y producción.
- Registro de gastos (con o sin bancal asignado).
- Registro de ingresos por fecha, categoría, kg y precio por kg.
- Cálculo de rentabilidad global, por campaña y por bancal.
- Visualización de métricas semanales y comparativas mediante gráficas.
- Importación masiva de datos históricos desde CSV.

### Lógica de negocio clave

- **Campaña agrícola**: abril-marzo.
  - Ejemplo: febrero de 2026 pertenece a campaña 2025.
- **Distribución de gastos sin bancal**:
  - Los gastos con `parcela_id = None` se reparten proporcionalmente según el campo `porcentaje` de cada parcela.
- **Totales de ingresos**:
  - `total = cantidad_kg * euros_kg`.

---

## 2. Detalle técnico de implementación

## Stack y tecnologías

- **Backend**: FastAPI
- **ORM**: SQLAlchemy 2.x (modo asíncrono)
- **Driver PostgreSQL**: asyncpg
- **Base de datos**: PostgreSQL
- **Migraciones**: Alembic
- **Configuración**: Pydantic Settings
- **Renderizado HTML**: Jinja2
- **Frontend**: Bootstrap 5 + Bootstrap Icons
- **Gráficas**: Chart.js
- **Herramientas auxiliares**: python-multipart, aiofiles, greenlet

## Arquitectura de carpetas

```text
.
├── app/
│   ├── main.py                 # Arranque FastAPI y dashboard principal
│   ├── config.py               # Configuración (DATABASE_URL, etc.)
│   ├── database.py             # Engine/sesiones async SQLAlchemy
│   ├── utils.py                # Funciones de campaña y reparto de gastos
│   ├── models/                 # Entidades ORM: Parcela, Gasto, Ingreso
│   ├── routers/                # Rutas por módulo funcional
│   ├── services/               # Lógica de negocio y agregaciones
│   ├── schemas/                # Esquemas Pydantic (DTOs)
│   └── templates/              # Vistas Jinja2
├── alembic/                    # Configuración de migraciones
├── import_data/                # Scripts + CSV de importación
├── pyproject.toml              # Dependencias y metadata
├── alembic.ini                 # Config Alembic
└── .env / .env.example         # Variables de entorno
```

## Flujo de ejecución

1. `uvicorn` arranca `app.main:app`.
2. En startup se inicializa base de datos (y tablas si no existen).
3. Cada request abre sesión asíncrona de BD.
4. Los routers delegan en la capa de servicios.
5. Los servicios consultan modelos SQLAlchemy y aplican reglas de negocio.
6. Jinja2 renderiza HTML con datos agregados.
7. En la vista de gráficas, los datos se serializan y se pintan con Chart.js.

## Capa de servicios (refactor aplicada)

La aplicación ya está refactorizada para separar responsabilidades.

- **Routers**: orquestación HTTP (leer params, llamar servicios, renderizar/redirect).
- **Services**: lógica de negocio, agregaciones y operaciones CRUD.
- **Models**: persistencia ORM.

Servicios principales:

- `app/services/parcelas_service.py`: CRUD de parcelas.
- `app/services/gastos_service.py`: CRUD y contexto de listado de gastos por campaña.
- `app/services/ingresos_service.py`: CRUD y contexto de listado de ingresos por campaña.
- `app/services/dashboard_service.py`: cálculo del dashboard global.
- `app/services/reportes_service.py`: cálculo del informe de rentabilidad.
- `app/services/graficas_service.py`: datasets para gráficas y tablas de producción.

Beneficios directos del refactor:

- Menos duplicación de lógica en routers.
- Más facilidad para pruebas unitarias sin levantar servidor.
- Mejor mantenibilidad y evolución del dominio.

## Modelos de datos

### Parcela

Campos relevantes:

- `nombre`
- `superficie_ha`
- `fecha_plantacion`
- `inicio_produccion`
- `porcentaje` (clave para reparto de gastos no asignados)

Relaciones:

- 1:N con `Gasto`
- 1:N con `Ingreso`

### Gasto

Campos relevantes:

- `fecha`
- `concepto`
- `persona`
- `parcela_id` (opcional)
- `cantidad`

### Ingreso

Campos relevantes:

- `fecha`
- `parcela_id` (opcional)
- `cantidad_kg`
- `categoria`
- `euros_kg`
- `total`

## Endpoints y vistas principales

- `/` Dashboard con totales globales y matriz campaña x bancal.
- `/parcelas/` CRUD de parcelas.
- `/gastos/` CRUD de gastos + filtros por campaña.
- `/ingresos/` CRUD de ingresos + filtros por campaña.
- `/reportes/rentabilidad` Informe de rentabilidad detallado.
- `/graficas/` Análisis visual (semanal y comparativa ingresos vs gastos).

---

## 3. Uso de la aplicación

## Requisitos previos

- Python 3.11 o superior
- PostgreSQL disponible
- Base de datos creada para el proyecto

## Configuración del entorno

1. Copia el archivo de ejemplo:

```bash
cp .env.example .env
```

2. Edita `.env` con tu conexión real:

```env
DATABASE_URL=postgresql+asyncpg://usuario:password@localhost:5432/truficultura
```

## Instalación de dependencias

Con `uv` (recomendado si usas `uv.lock`):

```bash
uv sync
```

Alternativa con `venv` + `pip`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Aplicar migraciones

```bash
alembic upgrade head
```

## Ejecutar la aplicación

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Abrir en navegador:

- http://localhost:8000

---

## 4. Modo debug, importaciones y operaciones frecuentes

## Modo desarrollo/debug

Arranque con autoreload:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Con mayor nivel de logs:

```bash
uvicorn app.main:app --reload --log-level debug
```

## Importación de datos CSV

Todos los assets de importación están en `import_data/`.

### 1) Importar gastos históricos

```bash
python3 import_data/import_gastos.py
```

Lee:

- `import_data/gastos_previos.csv`

### 2) Importar campaña 2025/2026 (gastos + ingresos)

```bash
python3 import_data/import_2025_2026.py
```

Lee:

- `import_data/gastos_2025_2026.csv`
- `import_data/ingresos_2025_2026.csv`

Comportamiento del import:

- Fechas en formato `dd/mm/yyyy`.
- Números en formato europeo (coma decimal).
- Si un bancal no existe, se importa con bancal nulo y se muestra aviso.

## Migraciones en desarrollo

Crear migración automática:

```bash
alembic revision --autogenerate -m "descripcion_del_cambio"
```

Aplicar migraciones:

```bash
alembic upgrade head
```

Volver una migración atrás:

```bash
alembic downgrade -1
```

## Comandos útiles

```bash
# Verificar que la app levanta
curl -I http://localhost:8000

# Comprobar sintaxis de scripts de importación
python3 -m py_compile import_data/import_gastos.py import_data/import_2025_2026.py

# Ejecutar pruebas unitarias de servicios
.venv/bin/python -m pytest -q tests/services

# Ejecutar pruebas de integración (SQLite real)
.venv/bin/python -m pytest -q tests/integration

# Ejecutar toda la suite
.venv/bin/python -m pytest -q tests/
```

## Pruebas unitarias (services first)

Se añadió una suite de tests unitarios para la capa de servicios en `tests/services/`.

Cobertura actual:

- CRUD de `parcelas_service`.
- CRUD y contexto de listados de `gastos_service` e `ingresos_service`.
- Cálculo de contexto en `dashboard_service` y `reportes_service`.
- Generación de contexto serializado de `graficas_service`.

Ejecutar pruebas:

```bash
.venv/bin/python -m pytest -q tests/services
```

Resultado actual de referencia:

- 11 tests pasando.

---

## Pruebas de integración (BD SQLite real)

Se añadió una suite de tests de integración en `tests/integration/` que ejercita los servicios contra una base de datos SQLite real creada en `tmp_path` por pytest (sin necesidad de levantar PostgreSQL).

Requiere `aiosqlite` (incluido en dependencias de desarrollo):

```bash
uv pip install "aiosqlite>=0.20.0"  # si no está ya instalado
```

Escenarios cubiertos:

- **CRUD completo**: crea parcela, gasto e ingreso; verifica que aparecen en los contextos de listado; elimina la parcela y comprueba que `get_parcela` devuelve `None`.
- **Dashboard y rentabilidad**: dos parcelas con reparto 60/40 (`porcentaje`), gastos asignados y sin asignar, ingresos. Valida totales `grand_gastos`, `grand_ingresos` y `rentabilidad`.
- **Gráficas**: crea un registro de cada tipo y valida que `build_graficas_context` devuelve `ing_values`, `gas_values` y `week_labels` correctos.

Ejecutar pruebas de integración:

```bash
.venv/bin/python -m pytest -q tests/integration
```

Resultado actual de referencia:

- 3 tests pasando.

Suite completa (unitarios + integración):

```bash
.venv/bin/python -m pytest -q tests/
```

- 14 tests pasando (11 unitarios + 3 de integración).

---

## Notas de implementación y mantenimiento

- La app usa sesiones asíncronas por request, con commit/rollback automático en dependencia de BD.
- El filtro Jinja `campaign_label` permite representar campañas como `2025/26`.
- Las plantillas comparten layout base (`base.html`) y usan Bootstrap para UI consistente.
- El dashboard y reportes agregan datos en Python tras consulta a BD.

---

## Futuras mejoras recomendadas

- Añadir autenticación y control de acceso.
- Ampliar tests de integración con un contenedor PostgreSQL real para cubrir comportamientos específicos de pgSQL (full-text search, tipos nativos).
- Añadir validaciones más estrictas en formularios (frontend y backend).
- Incorporar exportación de reportes (CSV/PDF).
- Tipar los contextos de plantillas con dataclasses o Pydantic para evitar errores de claves.

---

## Licencia

Definir según necesidades del proyecto.
