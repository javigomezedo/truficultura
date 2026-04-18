# Plan de Integración AEMET + Simulación de Riego

Fecha: 18/04/2026
Proyecto: Truficultura

## 1. Objetivo

Incorporar datos meteorológicos (AEMET) y una capa de simulación para decidir si regar o no en cada turno externo de riego, y en caso afirmativo, cuántas horas regar.

El objetivo final es mejorar la precisión del agua estimada que recibe cada parcela/planta, combinando:

- Riego aplicado (datos internos)
- Lluvia observada y predicha (AEMET)
- Caudal real por parcela (litros/segundo)
- Restricciones de turnos externos (ventana disponible)

## 2. Contexto Operativo (regla de negocio clave)

El riego no se decide libremente en cualquier momento:

- Una entidad externa (empresa/comunidad de regantes) abre un turno de riego.
- Cada usuario decide por parcela:
  - si quiere regar o no
  - cuántas horas dentro de la ventana disponible

Por tanto, la recomendación debe estar orientada a turnos, no solo a consumo histórico.

## 3. Dato Crítico Nuevo

Añadir en parcela con riego activo el caudal de entrada de agua en litros/segundo (`caudal_lps`).

Este dato permitirá convertir tiempo de riego en volumen real aplicado.

## 4. Fórmulas Base

### 4.1 Conversión de caudal a volumen

- Litros por hora: `litros_hora = caudal_lps * 3600`
- Litros aplicados: `litros_aplicados = litros_hora * horas_riego`
- m3 aplicados: `m3_aplicados = litros_aplicados / 1000`

### 4.2 Conversión de lluvia a volumen por parcela

- `lluvia_m3 = lluvia_mm * area_ha * 10`

(Recordatorio: 1 mm de lluvia sobre 1 ha equivale a 10 m3)

### 4.3 Balance hídrico esperado

- `agua_total_m3 = riego_m3 + lluvia_m3`
- `agua_efectiva_m3 = riego_m3 + (lluvia_m3 * coef_aprovechamiento)`

### 4.4 Recomendación de horas

- `horas_recomendadas = litros_deficit / (caudal_lps * 3600)`
- `horas_final = min(horas_recomendadas, horas_max_turno)`

## 5. Alcance Funcional (MVP)

1. Registrar y mantener `caudal_lps` por parcela.
2. Importar/guardar lluvia observada y predicción AEMET.
3. Registrar turnos externos de riego.
4. Simular por turno y parcela:
   - no regar
   - regar X horas
   - recomendación automática de horas
5. Mostrar impacto en KPIs y gráficas básicas de agua total (riego + lluvia).

## 6. Backlog por Épicas

## Epic A. Datos base y configuración hídrica

### Historia A1: Caudal por parcela

Como usuario, quiero informar el caudal en litros/segundo de cada parcela con riego para que el sistema estime volumen por tiempo.

Criterios de aceptación:

- Si `has_irrigation = true`, `caudal_lps` es obligatorio.
- Si `has_irrigation = false`, `caudal_lps` puede ir vacío.
- `caudal_lps` debe ser mayor que 0 cuando esté informado.
- Visible en alta/edición de parcela.

### Historia A2: Persistencia meteorológica

Como sistema, quiero almacenar lluvia observada y predicción por fecha/ubicación para cálculo offline y trazable.

Criterios de aceptación:

- Persistencia diaria idempotente.
- Guarda fuente, timestamp y estado de calidad.
- Soporta backfill histórico por rango de fechas.

## Epic B. Turnos y decisiones de riego

### Historia B1: Turnos externos

Como sistema, quiero registrar ventanas de riego disponibles (inicio, fin, duración) para simular decisiones realistas.

Criterios de aceptación:

- CRUD de turnos.
- Validación de duración positiva.
- Estado del turno (activo/cerrado/cancelado).

### Historia B2: Decisión de usuario por turno/parcela

Como usuario, quiero guardar si riego y cuántas horas para cada turno.

Criterios de aceptación:

- Decisión única por turno/parcela.
- Si riega, horas > 0.
- Horas no superan máximo del turno.

## Epic C. Simulación y recomendación

### Historia C1: Recomendación regar/no regar

Como usuario, quiero una recomendación basada en agua actual + lluvia prevista + turno.

Criterios de aceptación:

- Si lluvia prevista cubre objetivo, recomendar no regar.
- Si no cubre, recomendar horas necesarias.
- Justificación visible (déficit, lluvia prevista, volumen esperado).

### Historia C2: Escenarios comparativos

Como usuario, quiero comparar escenarios para decidir mejor.

Criterios de aceptación:

- Escenario 1: no regar.
- Escenario 2: regar horas recomendadas.
- Escenario 3: regar horas manuales.
- Mostrar litros y m3 resultantes en cada escenario.

## Epic D. KPIs, gráficas e informes

### Historia D1: KPIs de agua total

Como usuario, quiero ver KPIs de eficiencia con agua total y no solo con riego.

Criterios de aceptación:

- m3/kg (solo riego)
- m3/kg (riego + lluvia)
- m3/planta total
- % aporte lluvia sobre agua total

### Historia D2: Visualización temporal

Como usuario, quiero gráficas apiladas de riego y lluvia.

Criterios de aceptación:

- Serie semanal/mensual de riego + lluvia.
- Acumulado de agua total por campaña.

### Historia D3: Informes y análisis

Como usuario, quiero ver en informes la diferencia entre recomendación y ejecución real.

Criterios de aceptación:

- Comparativa recomendación vs horas decididas.
- Estimación de ahorro potencial de agua.
- Evolución por campaña y parcela.

## 7. Plan por Sprints

## Sprint 1 - Fundaciones de datos

- Añadir `caudal_lps` en parcela.
- Validaciones de dominio.
- Migración de base de datos.
- Ajustes de formularios y pruebas.

Entregable: parcelas con riego configurables con caudal válido.

## Sprint 2 - Integración AEMET

- Cliente AEMET (observado + predicción).
- Persistencia normalizada.
- Job de sincronización y backfill.
- Señalización de calidad de dato.

Entregable: serie meteorológica utilizable para cálculos.

## Sprint 3 - Turnos y decisiones

- Modelo y gestión de turnos externos.
- Modelo de decisión por turno/parcela.
- Pantalla de turnos próximos.

Entregable: flujo funcional de decisión por turno.

## Sprint 4 - Motor de simulación

- Cálculo de recomendación de horas con `caudal_lps`.
- Escenarios comparativos.
- Trazabilidad de inputs usados en recomendación.

Entregable: recomendación de regar/no y horas por turno.

## Sprint 5 - Explotación analítica

- KPIs de agua total.
- Gráficas de riego + lluvia.
- Informe de recomendación vs ejecución.
- Ajustes de análisis por parcela/campaña.

Entregable: impacto visible en producto y reporting.

## 8. Riesgos y Mitigaciones

1. Predicción meteorológica incierta
- Mitigación: escenarios conservador/medio/optimista.

2. Microclima no capturado por estación
- Mitigación: mapping por parcela a estación configurable y override manual.

3. Caudal mal calibrado
- Mitigación: mantener editable y auditar desviaciones históricas.

4. Falta de datos críticos
- Mitigación: estado "no calculable" y bloqueo de recomendación automática cuando corresponda.

## 9. Reglas de Calidad y Gobernanza de Datos

- No generar recomendación automática si falta `caudal_lps` en parcela con riego.
- No generar recomendación automática si falta dato meteo mínimo requerido.
- Guardar snapshot de predicción usado para cada simulación.
- Mantener trazabilidad de versión de fórmula/algoritmo.

## 10. Criterios de Éxito (MVP)

1. Para un turno futuro, el sistema recomienda si regar o no por parcela.
2. Si recomienda regar, devuelve horas recomendadas dentro del límite del turno.
3. Se muestran equivalencias en litros y m3.
4. Se visualiza agua total (riego + lluvia) en KPI y gráfica básica.
5. El usuario puede registrar decisión final y compararla con la recomendación.

## 11. Definición de Hecho (DoD)

- Migraciones con `upgrade()` y `downgrade()`.
- Tests unitarios de servicios nuevos y modificados.
- Tests de integración del flujo turno -> simulación -> decisión.
- Suite completa en verde:

` .venv/bin/python -m pytest -q tests/ `

- Documentación actualizada en README y documentación funcional.
