# Plan: Especie/variedad del árbol huésped

## Decisiones confirmadas

- **Enum**: `encina, roble, quejigo, coscoja, avellano, carpe, otros` (7 valores)
- **UI**: Nuevo modo de vista "especie" en el mapa + columna "Especie" en tabla de resumen + leyenda de colores
- **Parcela**: Campo `default_host_species` en `Plot` como valor por defecto (se hereda al generar plantas via `configure_plot_map`)
- **Analytics**: Card "Resumen por especie" debajo de la tabla (Especie | Plantas | Gramos | g/planta)
- **Export**: No por ahora
- **Última migración**: `0030` → la nueva será `0031`

---

## Paleta de colores

| Especie    | Color CSS                        | Hex       |
|------------|----------------------------------|-----------|
| encina     | rgba(25, 135, 84, 0.75)          | #198754   |
| roble      | rgba(139, 78, 20, 0.75)          | #8b4e14   |
| quejigo    | rgba(102, 126, 0, 0.75)          | #667e00   |
| coscoja    | rgba(220, 100, 60, 0.75)         | #dc643c   |
| avellano   | rgba(130, 60, 180, 0.75)         | #823cb4   |
| carpe      | rgba(32, 178, 170, 0.75)         | #20b2aa   |
| otros      | rgba(108, 117, 125, 0.75)        | #6c757d   |
| Sin asignar | bg-body-secondary (gris claro)  | —         |

---

## Fase 1 — Capa de datos

### `app/models/plant.py`
- Añadir enum `HostSpecies` con valores `encina, roble, quejigo, coscoja, avellano, carpe, otros`.
- Añadir columna `host_species: Mapped[Optional[HostSpecies]]` nullable después de `baja_date`.
- `SAEnum(HostSpecies, name="host_species_enum")`.

### `app/models/plot.py`
- Importar `HostSpecies` desde `app.models.plant` (importación directa en runtime, no bajo `TYPE_CHECKING`).
- Añadir columna `default_host_species: Mapped[Optional[HostSpecies]]` nullable.

### `alembic/versions/0031_add_host_species.py` *(crear)*
- `down_revision = "0030"`.
- `upgrade()`:
  - `CREATE TYPE host_species_enum AS ENUM ('encina','roble','quejigo','coscoja','avellano','carpe','otros')`
  - `ADD COLUMN plants.host_species host_species_enum NULL`
  - `ADD COLUMN plots.default_host_species host_species_enum NULL`
- `downgrade()`: `DROP COLUMN` de ambas columnas + `DROP TYPE host_species_enum`.

---

## Fase 2 — Schemas

### `app/schemas/plot.py`
- Añadir `default_host_species: Optional[str] = None` a `PlotBase`, `PlotCreate`, `PlotUpdate` y `PlotResponse`.
- Se usa `str` para evitar importación circular; la conversión al enum ocurre en el router.

---

## Fase 3 — Servicios

### `app/services/plants_service.py`
- Importar `HostSpecies`.
- Añadir `update_plant_species(db, plant_id, tenant_id, *, host_species: Optional[HostSpecies]) -> Optional[Plant]`:
  - Mismo patrón que `update_plant_status()`: fetch → mutar → flush → return.
- Añadir `get_species_summary(db, plot_id, tenant_id, *, selected_campaign: Optional[int]) -> list[dict]`:
  - Agrega `TruffleEvent` por `Plant.host_species` usando `_campaign_date_range` si hay campaña.
  - Devuelve `[{species, plant_count, total_grams, grams_per_plant}]` incluyendo un grupo `None` para "Sin asignar".
- En `configure_plot_map()`: al crear cada `Plant`, asignar `host_species = plot.default_host_species` (el objeto `Plot` ya está disponible como argumento).

### `app/services/plots_service.py`
- Añadir `default_host_species: Optional[HostSpecies] = None` a los parámetros de `create_plot()` y `update_plot()`.

---

## Fase 4 — Routers

### `app/routers/plants.py`
- Importar `HostSpecies`.
- `_build_map_summary_rows()`: añadir `"host_species": cell.plant.host_species` al dict de cada planta.
- `map_view()`:
  - Añadir `"especie"` como modo válido junto a `weight, presence, brule, estado`.
  - Llamar `plants_service.get_species_summary(db, plot_id, tenant_id, selected_campaign=selected)`.
  - Pasar `species_summary` y `host_species_choices = list(HostSpecies)` al contexto de la plantilla.
- Nuevo endpoint `POST /plots/{plot_id}/plants/{plant_id}/species`:
  - `host_species: str = Form(default="")` — vacío → `None`.
  - Parsear con try/except a `HostSpecies` o `None`.
  - Llamar `plants_service.update_plant_species()`.
  - `await db.commit()`.
  - Redirigir igual que `/status` (con `camp_param` si hay campaña).

### `app/routers/plots.py`
- Añadir `default_host_species: Optional[str] = Form(None)` en `create_plot()` y `update_plot()`.
- Convertir a `Optional[HostSpecies]` con try/except antes de pasar al servicio.
- Pasar `host_species_choices = list(HostSpecies)` al contexto de `new_plot_form()` y `edit_plot_form()`.

---

## Fase 5 — Templates

### `app/templates/parcelas/mapa.html`

1. **CSS** — Añadir 7 clases `.tf-map-cell-species-{nombre}` con la paleta de colores de la tabla de arriba.

2. **Botón de modo** — Añadir botón "Especie" en la barra de modos de vista (después de "Estado"):
   ```html
   <a href="...?view=especie" class="btn btn-sm {{ 'btn-success' if map_view_mode == 'especie' else 'btn-outline-secondary' }}">
     <i class="bi bi-tree me-1"></i>{{ _("Especie") }}
   </a>
   ```

3. **Leyenda** — En el `card-header` del grid, mostrar leyenda condicional:
   - Si `map_view_mode != 'especie'`: leyenda actual de estado (Viva, Estresada, Reemplazada, Muerta).
   - Si `map_view_mode == 'especie'`: leyenda de las 7 especies + "Sin asignar", mismo formato (cuadrado 16×16 + texto).

4. **Grid** — Bloque `{% elif map_view_mode == 'especie' %}` en las celdas:
   - Clase CSS según especie: `tf-map-cell-species-{plant.host_species.value}` o `bg-body-secondary` si `None`.
   - Atributos `data-species-mode="true"`, `data-plant-species="{value|''}"`, tooltip con nombre de especie.

5. **Modal "Especie huésped"** — Mismo patrón que el modal de estado:
   - `<select id="speciesSelect" name="host_species">` con opción vacía "Sin asignar" + 7 valores.
   - POST a `/plots/{plot.id}/plants/${plantId}/species`.
   - Campo oculto de campaña si aplica.

6. **JS** — Manejar clicks en `[data-species-mode="true"]`: rellenar modal con `cell.dataset.plantSpecies` y abrir `speciesModal`.

7. **Tabla de resumen** — Añadir columna "Especie" entre "Estado" y la acción:
   - Badge de color con el nombre de la especie, o `—` si `None`.

8. **Card "Resumen por especie"** — Debajo de la tabla de resumen, solo si `species_summary`:
   - Tabla: Especie | N° Plantas | Gramos (filtro actual) | g/planta.
   - Cada fila lleva el cuadrado de color de la especie.

### `app/templates/parcelas/form.html`

- En la sección "Datos de la parcela": añadir `<select>` con label "Especie huésped por defecto":
  - Opción vacía "— No especificar —".
  - Opciones iteradas desde `host_species_choices` pasadas por el router.
  - Valor seleccionado: `plot.default_host_species.value if plot and plot.default_host_species else ''`.

---

## Fase 6 — Tests

### `tests/services/test_plants_service.py`
- `test_update_plant_species_sets_species()`:
  - Mock `db.execute` → `result([plant])` donde `plant` es un `SimpleNamespace` con `host_species=None`.
  - Llamar `update_plant_species(db, plant_id=1, tenant_id=1, host_species=HostSpecies.encina)`.
  - Verificar `plant.host_species == HostSpecies.encina` y `db.flush` awaited.
  - Mismo patrón que `test_update_plant_status_sets_status_and_baja_date`.

### `tests/test_plants_router.py`
- `test_update_plant_species_redirects()`:
  - POST a `/plots/10/plants/3/species` con `host_species=encina`.
  - Mock `get_plot`, `get_plant`, `plants_service.update_plant_species`.
  - Verificar redirect 303 a `/plots/10/map?view=especie`.

---

## Archivos modificados / creados

| Archivo | Acción |
|---|---|
| `app/models/plant.py` | Modificar |
| `app/models/plot.py` | Modificar |
| `app/schemas/plot.py` | Modificar |
| `app/services/plants_service.py` | Modificar |
| `app/services/plots_service.py` | Modificar |
| `app/routers/plants.py` | Modificar |
| `app/routers/plots.py` | Modificar |
| `app/templates/parcelas/mapa.html` | Modificar |
| `app/templates/parcelas/form.html` | Modificar |
| `alembic/versions/0031_add_host_species.py` | **Crear** |

---

## Verificación

1. `uv run pytest tests/test_plants_router.py tests/services/test_plants_service.py -v` — nuevos tests pasan.
2. `uv run pytest` — suite completa sigue verde (58+ tests).
3. `alembic upgrade head` en BD de dev — migración sin errores.
4. Manual en navegador:
   - Crear parcela con especie por defecto "encina" → configurar mapa → plantas heredan encina.
   - Mapa en modo "especie" → leyenda visible, celdas verdes (encina).
   - Clic en celda → modal → cambiar a "roble" → guardar → celda cambia a marrón, leyenda sigue visible.
   - Asignar varias especies → card "Resumen por especie" muestra kg/planta por cada una.

---

## Consideraciones adicionales

- **Sin circular import**: `plot.py` importa `HostSpecies` de `plant.py` directamente; el `TYPE_CHECKING` en `plant.py` para `Plot` sigue siendo solo de anotaciones → sin ciclo en runtime.
- **`configure_plot_map`** recibe el objeto `Plot` ya cargado → `plot.default_host_species` disponible sin queries adicionales.
- **Leyenda siempre visible** mientras se está en el modo "especie", independientemente de si hay plantas asignadas o no.
