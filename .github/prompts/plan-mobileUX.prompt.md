# Plan: Mobile UX Improvements

## Audit findings

### scan/confirm.html
- Weight input: `type="number"` but missing `inputmode="decimal"` (the mapa modal has it; confirm.html doesn't)
- Missing `enterkeyhint="done"` on weight input
- Quick-add buttons use `btn-sm` — small touch targets
- Input should be `form-control-lg` to prevent iOS auto-zoom (font-size <16px triggers zoom)
- Form is already `col-lg-6 col-xl-5` → full-width on mobile ✓

### scan/success.html
- Buttons in `d-flex gap-2` → side by side on all viewports; should stack on xs
- `container py-5` is overly spaced on mobile

### mapa.html (plant map)
- Cell size: `@media (max-width: 576px)` keeps cells at 32×32px — below 44px iOS/Google touch target minimum
- Missing `touch-action: manipulation` on cells (causes 300ms tap delay on mobile)
- View mode toggle (5 buttons: Peso, Presencia, Brulé, Estado, Especie) uses `d-flex flex-wrap gap-1` — wraps to 2 rows on small screens
- Filter bar + view mode toggle in same form row gets cramped
- Row labels use `position: sticky; left: 0` ✓ — map is horizontally scrollable ✓
- Register weight modal uses `w-100 w-sm-auto` ✓

### produccion/form_bancal.html
- 3-column table (Bancal, Gramos, Notas) → Notes column wastes space on mobile
- Inputs already have `inputmode="decimal"` ✓
- Missing `enterkeyhint="done"` on grams inputs

### reportes/trufas.html (por planta)
- 6-column main table: Fecha, Parcela, Planta, Peso, Origen, Acciones — all show on mobile
- Summary table 5 cols including "Top plantas" (badge list) → breaks on small screens
- "Origen" badge is rarely needed in the field

### reportes/rentabilidad.html
- Main matrix already has `table-responsive` + `sticky-col` for campaign column ✓
- `white-space: nowrap` on all cells → horizontally scrollable ✓
- Not a field-use screen; secondary priority
- Two bottom summary tables (by year, by plot) at `col-lg-6` → full width on mobile ✓

---

## Plan

### Phase 1 — QR Scan Flow [HIGH, field-critical]
Files: `app/templates/scan/confirm.html`, `app/templates/scan/success.html`

1. **scan/confirm.html**:
   - Change weight input to `form-control-lg` class
   - Add `inputmode="decimal"` + `enterkeyhint="done"` to weight input
   - Enlarge quick-add buttons: change `btn-sm` → `btn` (no size modifier) on this screen
   - Remove restrictive `col-lg-6 col-xl-5` wrapper or add `px-3` for breathing room

2. **scan/success.html**:
   - Change button wrapper `d-flex gap-2` → `d-grid gap-2 d-sm-flex` so buttons are full-width stacked on mobile
   - Reduce top/bottom padding on mobile

### Phase 2 — Plant Map [HIGH, field-critical]
File: `app/templates/parcelas/mapa.html`

3. Increase cell size in the `@media (max-width: 576px)` block: 32px → 44px
4. Add `touch-action: manipulation` to `.tf-map-cell` via inline style block
5. View mode toggle: wrap the 5 buttons in `overflow-x: auto; white-space: nowrap` container (scrollable row) instead of `flex-wrap`
6. Move view mode toggle outside the filter form on mobile (via CSS display or separate HTML block) to avoid layout conflicts

### Phase 3 — Harvest Form [MEDIUM]
File: `app/templates/produccion/form_bancal.html`

7. Add `d-none d-sm-table-cell` to Notas `<th>` and all Notas `<td>` — hide on xs, show from sm
8. Add `enterkeyhint="done"` to grams inputs

### Phase 4 — Production by Plant [MEDIUM]
File: `app/templates/reportes/trufas.html`

9. Main table: add `d-none d-md-table-cell` to "Origen" column (th + td)
10. Summary table: add `d-none d-md-table-cell` to "Top plantas" column (th + td)
11. Shrink/simplify "Añadir por planta" button: icon-only on xs (`d-none d-sm-inline` on text)

### Phase 5 — Profitability [LOW, not field-use]
File: `app/templates/reportes/rentabilidad.html`

12. Add a mobile hint below the matrix explaining it scrolls horizontally (or a `<i class="bi bi-arrows-expand-vertical">` indicator)
13. On xs: add a brief card summary (campaign totals only) above the scrollable matrix, collapsible

### Phase 6 — Barra de navegación inferior móvil [HIGH]
Files: `app/templates/base.html`, `app/static/css/app.css`

- Añadir barra fija `position: fixed; bottom: 0; left: 0; right: 0` visible solo en móvil (`d-flex d-lg-none`)
- Solo mostrarla cuando el usuario está autenticado (bloque `{% if request.session.get("username") %}`)
- 4 accesos directos: Inicio (`/`), Mapa (`/maps/`), Cosecha (`/harvests/new`), Campo (`/plot-events/`)
- Añadir `padding-bottom: calc(64px + env(safe-area-inset-bottom))` al `<main>` en móvil para que el contenido no quede tapado
- El botón del asistente flotante (`.tf-assistant-launch`) debe subir para no solaparse: `bottom: calc(64px + 1rem)` en móvil
- Respetar `safe-area-inset-bottom` (iPhone X+)

### Phase 7 — PWA manifest [LOW]
Files: `app/static/manifest.json` (new), `app/templates/base.html`

- Crear `app/static/manifest.json`: `name`, `short_name`, `start_url`, `display: standalone`, `background_color`, `theme_color`, iconos referenciando `/static/img/favicon.svg`
- Añadir en `base.html` `<head>`: `<link rel="manifest" href="/static/manifest.json">`
- Añadir `<meta name="theme-color" content="#261c13">` (color navbar)
- Añadir `<meta name="apple-mobile-web-app-capable" content="yes">` y `<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">`
- Nota: el ícono SVG funciona en Chrome/Android; iOS requiere PNG (192×192 y 512×512). Si no hay PNGs, usar el SVG igualmente — es suficiente para una primera versión.

---

## Archivos afectados

| Archivo | Fases |
|---|---|
| `app/templates/scan/confirm.html` | 1 |
| `app/templates/scan/success.html` | 1 |
| `app/templates/parcelas/mapa.html` | 2 |
| `app/templates/produccion/form_bancal.html` | 3 |
| `app/templates/reportes/trufas.html` | 4 |
| `app/templates/reportes/rentabilidad.html` | 5 |
| `app/templates/base.html` | 6, 7 |
| `app/static/css/app.css` | 6 |
| `app/static/manifest.json` (nuevo) | 7 |

## Verificación

1. Chrome DevTools → 375px (iPhone 14): verificar barra inferior con los 4 accesos y que no tapa el contenido
2. Safari iOS real o simulador: verificar "Añadir a pantalla de inicio" y que abre en modo standalone
3. `/scan/{token}`: teclado decimal, botones grandes, botones de éxito apilados
4. `/plots/{id}/map`: celdas 44px, toggle de modo scrollable horizontal, sin delay en tap
5. `/harvests/new`: columna Notas oculta en xs
6. `/truffles/`: columna Origen oculta en móvil, Top plantas oculto en xs
7. `pytest` full suite — solo son cambios de template, no deben romperse tests
