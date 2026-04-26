from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense
from app.models.income import Income
from app.models.irrigation import IrrigationRecord
from app.models.plant import Plant
from app.models.plot import Plot
from app.models.plot_event import PlotEvent
from app.models.truffle_event import TruffleEvent
from app.models.plot_harvest import PlotHarvest
from app.models.rainfall import RainfallRecord
from app.models.recurring_expense import RecurringExpense
from app.models.well import Well
from app.schemas.plot_event import EventType
from app.services.llm_adapter import LLMAdapter
from app.utils import (
    campaign_label,
    campaign_year,
    distribute_unassigned_expenses,
    format_eu,
)

_MAX_HISTORY_TURNS = 5
_MAX_MESSAGE_LEN = 1000

_APP_KNOWLEDGE = """Eres el asistente de Truficultura, una aplicación web para gestionar \
explotaciones trufícolas. Respondes siempre en español, con claridad y concisión. \
No ejecutas acciones: solo explicas y consultas datos en modo lectura.

REGLAS DE RESPUESTA:
- Si en el contexto aparecen "DATOS ACTUALES DEL USUARIO", debes responder usando esos datos.
- No digas que no tienes acceso a los datos si la información relevante ya está resumida en el contexto.
- Solo indica que falta información cuando el dato no esté registrado o no aparezca en el contexto agregado.
- Si preguntan por categorías de gasto, categorías de ingreso, personas con más gasto o resúmenes por parcela, utiliza los apartados agregados del contexto para responder directamente.
- Si el usuario pide un resumen, prioriza dar la respuesta con cifras y después, si hace falta, aclara limitaciones concretas.

MÓDULOS DE LA APLICACIÓN:
- Parcelas (bancales): gestión de parcelas con nombre, número de parcela, polígono y recinto SIGPAC, \
referencia catastral, hidrante, sector, número de plantas, fechas de plantación e inicio de \
producción, superficie en ha y municipio. Cada parcela tiene un porcentaje calculado \
automáticamente (plantas propias / total plantas del usuario).
- Mapa de plantas: cada parcela tiene un mapa visual de plantas con etiquetas (A1, B3…). \
Las plantas se gestionan individualmente. Se puede imprimir o descargar el QR de cada planta.
- Producción — Eventos de trufa (por planta): registro de eventos de trufa por planta individual, \
con peso estimado en gramos, fuente (manual o QR), historial y filtros por campaña/parcela/planta. \
Los eventos se pueden deshacer. Fuente QR significa que se registró escaneando el código QR.
- Producción — Cosecha por bancal: registro de cosechas a nivel de parcela completa \
(fecha + peso en gramos), sin asociar a una planta concreta. La vista de producción total \
combina eventos por planta y cosechas por bancal.
- Presencia de planta: registro diario de si una planta concreta tiene trufa (campo de datos \
para análisis). Único por planta y fecha.
- Escaneo QR: cada planta lleva un QR firmado criptográficamente. Al escanearlo, si el usuario \
no está autenticado, redirige al login y retoma automáticamente el escaneo.
- Riego: registro de riegos por parcela con volumen de agua en m³ y notas. Cada parcela puede \
activar o desactivar el riego. Se integra con los eventos de parcela (tipo "riego").
- Pozos / Labores de pozo: registro de labores de pozo por parcela con número de pozos por \
planta y fecha. Se integra con los eventos de parcela (tipo "pozo").
- Eventos de parcela (labores): historial de labores agrícolas por parcela. Tipos disponibles: \
labrado, picado, poda, vallado, instalación de goteo (installed_drip), riego, pozo. \
Cada evento tiene fecha, notas y puede marcarse como recurrente.
- Lluvia / Pluviometría: registro de precipitaciones por parcela o por municipio. Fuentes: \
manual (el propio usuario), AEMET (red meteorológica oficial española), Ibericam (red privada). \
Los registros AEMET/Ibericam se asocian al municipio. Incluye vista de calendario mensual y \
listado filtrable por año, parcela, fuente y municipio.
- Ingresos: fecha, parcela (opcional), categoría de trufa (Extra, A, B…), kg y €/kg. \
El total (€) se calcula automáticamente: cantidad_kg × euros_kg.
- Gastos: fecha, descripción, persona, parcela (opcional), importe y categoría \
(Pozos, Vallado, Labrar, Instalación riego, Perros, Plantel, Riego, Regadío Social, Otros). \
Se puede adjuntar un justificante (imagen o PDF). Los gastos sin parcela son "generales" \
y se distribuyen entre todas las parcelas proporcionalmente al número de plantas.
- Gastos recurrentes: plantillas de gastos periódicos con frecuencia semanal, mensual o anual. \
Un proceso automático (cron) las convierte en gastos reales según su configuración. \
Se pueden activar o desactivar individualmente sin borrarlas.
- Prorrateo de gastos: un gasto grande se puede dividir en N años/campañas, creando N gastos \
individuales vinculados. Eliminar el grupo de prorrateo borra todos sus gastos hijos.
- Rentabilidad / Reportes: informe por campaña y parcela con ingresos, gastos directos, \
gastos generales distribuidos y rentabilidad neta ajustada.
- KPIs: panel de indicadores clave por campaña: ROI (%), €/kg medio, m³ de agua por kg vendido, \
crecimiento de kg respecto a la campaña anterior y total kg vendidos.
- Gráficas: evolución semanal de ingresos, comparativa acumulada ingresos vs gastos por campaña, \
mix de ingresos y gastos por categoría, y comparativa entre parcelas.
- Analítica de parcelas: análisis de correlaciones entre riego y producción (bandas de agua \
bajo/medio/alto), impacto de poda y labrado en producción, umbrales de riego óptimos, \
comparativa multi-parcela y detalle por parcela y campaña.
- Importar/Exportar: CSV con punto y coma como separador, formato numérico europeo (1.250,50) \
y fechas dd/mm/aaaa.
- Admin (solo administrador): gestión de usuarios (alta, baja, activar/desactivar, cambio de \
contraseña, confirmación de email). El primer usuario registrado se convierte en administrador.

CAMPAÑA AGRÍCOLA:
- Va de mayo a abril del año siguiente.
- Ejemplo: cualquier fecha entre mayo 2025 y abril 2026 pertenece a la campaña 2025, \
que se muestra como "2025/26".
- El 15 de marzo de 2026 pertenece a la campaña 2025/26.

DISTRIBUCIÓN DE GASTOS GENERALES:
- Los gastos sin parcela asignada se reparten proporcionalmente según el porcentaje de cada parcela.
- El porcentaje se calcula automáticamente: (plantas de la parcela / total plantas del usuario) × 100.

MULTI-USUARIO:
- Cada usuario solo ve y gestiona sus propios datos.
- El primer usuario registrado se convierte automáticamente en administrador.
- IMPORTANTE DE SEGURIDAD: Los datos que aparecen en el contexto "DATOS ACTUALES DEL USUARIO" \
son EXCLUSIVAMENTE del usuario autenticado en esta sesión. \
Nunca mezcles, combines ni infieras datos de otros usuarios. \
Si alguien pregunta por datos de otro usuario o del sistema en general, responde únicamente \
con los datos del contexto proporcionado o indica que no dispones de esa información.
"""

# Substrings que indican que la pregunta es sobre los datos propios del usuario.
_DATA_KEYWORDS = {
    "mi ",
    "mis ",
    "mio",
    "mia",
    "cuanto he",
    "cuanto tengo",
    "cuanto llevo",
    "cual fue mi",
    "cual es mi",
    "cuales son mis",
    "mi mejor",
    "mi peor",
    "mejor campana",
    "peor campana",
    "mis datos",
    "mi rentabilidad",
    "cuanto he ganado",
    "cuanto he gastado",
    "cuantas parcelas tengo",
    "mis ingresos",
    "mis gastos",
    "mi produccion",
    "mis riegos",
    "tengo alguna parcela",
    "tengo parcelas",
    "categorias de gasto",
    "categoria de gasto",
    "categorias de ingreso",
    "categoria de ingreso",
    "facturacion",
    "resumen por parcela",
    "gastos por persona",
    "persona acumula mas gasto",
    "persona acumula mas gastos",
    "rentabilidad ajustada",
    "gastos generales",
    "parcela tiene peor rentabilidad",
    "riego activo",
    "baja produccion",
    "produccion registrada",
    "retorno",
    "labores relevantes",
    "parcelas tienen vallado",
    "lluvia",
    "lluvias",
    "pluvio",
    "precipitacion",
    "precipitaciones",
    "pluviometria",
    "recurrente",
    "recurrentes",
    "gastos recurrentes",
    "kpi",
    "kpis",
    "labrado",
    "picado",
    "poda",
    "vallado",
    "cosecha",
    "cosechas",
    "prorrateo",
    "prorratear",
    "analitica",
    "analisis de parcela",
    "presencia de planta",
    "cosecha por bancal",
    "produccion total",
}

_USAGE_KEYWORDS = {
    "como",
    "donde",
    "que es",
    "pasos",
    "funciona",
    "dar de alta",
    "crear",
    "registrar",
    "importar",
    "exportar",
    "menu",
    "pantalla",
}

_DATA_PATTERNS = [
    re.compile(
        r"\b(cuanto|cuantos|cual|cuales)\b.*\b(tengo|he|llevo|fue|es|han sido)\b"
    ),
    re.compile(r"\b(mejor|peor)\b.*\b(campana|parcela)\b"),
    re.compile(r"\b(tengo|hay)\b.*\b(parcela|parcelas)\b.*\b(con|sin)\b"),
    re.compile(r"\b(categoria|categorias)\b.*\b(gasto|gastos|ingreso|ingresos)\b"),
    re.compile(r"\b(resumen)\b.*\b(parcela|parcelas)\b"),
    re.compile(r"\b(persona|personas)\b.*\b(gasto|gastos)\b"),
    re.compile(
        r"\b(peor|mejor)\b.*\b(rentabilidad)\b.*\b(ajustada|gastos generales)\b"
    ),
    re.compile(r"\b(gastos generales)\b.*\b(parcela|parcelas|rentabilidad)\b"),
    re.compile(
        r"\b(parcela|parcelas)\b.*\b(tiene|tienen)\b.*\b(riego|riego activo)\b.*\b(produccion|rentabilidad|baja)\b"
    ),
    re.compile(
        r"\b(que|cuales)\b.*\b(parcela|parcelas)\b.*\b(tiene|tienen)\b.*\b(vallado|pozo|labores|riego|produccion|rentabilidad)\b"
    ),
    re.compile(
        r"\b(donde)\b.*\b(gasto|gastando|gastos)\b.*\b(retorno|rentabilidad|menos)\b"
    ),
    re.compile(r"\b(lluvia|precipitacion|pluvio)\b.*\b(parcela|municipio|mes|ano|campana)\b"),
    re.compile(r"\b(recurrente|recurrentes)\b.*\b(gasto|gastos)\b"),
    re.compile(r"\b(kpi|kpis)\b"),
    re.compile(r"\b(analitica|analisis)\b.*\b(parcela|riego|poda|labrado)\b"),
    re.compile(r"\b(cosecha|cosechas)\b.*\b(bancal|parcela|campana)\b"),
    re.compile(r"\b(prorrateo|prorratear)\b"),
]

_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignora (todas )?las instrucciones", re.IGNORECASE),
    re.compile(r"olvida (todo|las reglas)", re.IGNORECASE),
    re.compile(r"actua como", re.IGNORECASE),
    re.compile(r"system prompt", re.IGNORECASE),
]

_SOURCES_USAGE = [
    "kb:app_core_guidance",
    "kb:campaign_rules",
]

_SOURCES_DATA = [
    "db:plots",
    "db:plants",
    "db:truffle_events",
    "db:plot_events",
    "db:wells",
    "db:incomes",
    "db:expenses",
    "db:irrigation",
    "db:rainfall",
    "db:recurring_expenses",
    "db:plot_harvests",
    "analytics:profitability_distributed",
    "analytics:kpi_snapshot",
    "analytics:charts_snapshot",
    "utils:campaign_year",
    "utils:campaign_label",
]


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    without_accents = "".join(
        ch for ch in normalized if unicodedata.category(ch) != "Mn"
    )
    return without_accents.lower().strip()


def _format_eur(value: float) -> str:
    return f"{format_eu(value, 2)}€"


def _sanitize_user_message(message: str) -> str:
    """Apply light prompt hardening and strip control characters.

    We keep semantics intact while removing common jailbreak phrases and
    unsupported non-printable chars.
    """
    clean = "".join(ch for ch in message if ch.isprintable() or ch in {"\n", "\t"})
    clean = clean.strip()
    for pattern in _PROMPT_INJECTION_PATTERNS:
        clean = pattern.sub("", clean)
    # Collapse excessive whitespace after substitutions.
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _build_traceability(intent: str) -> dict:
    """Build machine-readable trace metadata for UI transparency.

    retrieval_mode is set to "static" for now and can evolve to "rag" without
    changing API contracts.
    """
    if intent == "datos":
        return {
            "retrieval_mode": "static",
            "data_scope": "aggregated-user-data",
            "sources": _SOURCES_DATA,
        }
    return {
        "retrieval_mode": "static",
        "data_scope": "product-guidance",
        "sources": _SOURCES_USAGE,
    }


def _classify_intent(message: str) -> str:
    """Return 'datos' if the query is about the user's own data, else 'uso'."""
    lowered = _normalize_text(message)

    for pattern in _DATA_PATTERNS:
        if pattern.search(lowered):
            return "datos"

    for kw in _DATA_KEYWORDS:
        if kw in lowered:
            return "datos"

    for kw in _USAGE_KEYWORDS:
        if kw in lowered:
            return "uso"

    return "uso"


async def _build_user_context(db: AsyncSession, user_id: int) -> str:
    """Return a compact aggregated summary of the user's data to inject into the prompt.

    Only aggregated totals are sent — no raw records — to minimise data exposure.
    All queries are filtered strictly by user_id.
    """
    plots_result = await db.execute(
        select(Plot).where(Plot.user_id == user_id).order_by(Plot.name)
    )
    plots = plots_result.scalars().all()

    incomes_result = await db.execute(select(Income).where(Income.user_id == user_id))
    incomes = incomes_result.scalars().all()

    expenses_result = await db.execute(
        select(Expense).where(Expense.user_id == user_id)
    )
    expenses = expenses_result.scalars().all()

    irrigation_result = await db.execute(
        select(IrrigationRecord).where(IrrigationRecord.user_id == user_id)
    )
    irrigations = irrigation_result.scalars().all()

    plot_events_result = await db.execute(
        select(PlotEvent).where(PlotEvent.user_id == user_id)
    )
    plot_events = plot_events_result.scalars().all()

    wells_result = await db.execute(select(Well).where(Well.user_id == user_id))
    wells = wells_result.scalars().all()

    plants_result = await db.execute(select(Plant).where(Plant.user_id == user_id))
    plants = plants_result.scalars().all()

    truffle_events_result = await db.execute(
        select(TruffleEvent).where(TruffleEvent.user_id == user_id)
    )
    truffle_events = truffle_events_result.scalars().all()

    rainfall_result = await db.execute(
        select(RainfallRecord).where(RainfallRecord.user_id == user_id)
    )
    rainfall_records = rainfall_result.scalars().all()

    recurring_expenses_result = await db.execute(
        select(RecurringExpense).where(RecurringExpense.user_id == user_id)
    )
    recurring_expenses_list = recurring_expenses_result.scalars().all()

    plot_harvests_result = await db.execute(
        select(PlotHarvest).where(PlotHarvest.user_id == user_id)
    )
    plot_harvests = plot_harvests_result.scalars().all()

    if (
        not plots
        and not incomes
        and not expenses
        and not irrigations
        and not plot_events
        and not wells
        and not plants
        and not truffle_events
    ):
        return "Sin datos registrados aún."

    income_by_campaign: dict[int, float] = defaultdict(float)
    income_by_plot: dict[int | None, float] = defaultdict(float)
    for inc in incomes:
        total = inc.total
        income_by_campaign[campaign_year(inc.date)] += total
        income_by_plot[inc.plot_id] += total

    expense_by_campaign: dict[int, float] = defaultdict(float)
    expense_by_plot: dict[int | None, float] = defaultdict(float)
    unassigned_expenses_total = 0.0
    for exp in expenses:
        amount = exp.amount
        expense_by_campaign[campaign_year(exp.date)] += amount
        expense_by_plot[exp.plot_id] += amount
        if exp.plot_id is None:
            unassigned_expenses_total += amount

    irrigation_by_campaign: dict[int, float] = defaultdict(float)
    irrigation_by_plot: dict[int, float] = defaultdict(float)
    for record in irrigations:
        water = record.water_m3
        irrigation_by_campaign[campaign_year(record.date)] += water
        irrigation_by_plot[record.plot_id] += water

    income_kg_by_campaign: dict[int, float] = defaultdict(float)
    incomes_by_category: dict[str, dict[str, float]] = defaultdict(
        lambda: {"kg": 0.0, "eur": 0.0}
    )
    for inc in incomes:
        cy = campaign_year(inc.date)
        income_kg_by_campaign[cy] += inc.amount_kg
        category = inc.category or "Sin categoría"
        incomes_by_category[category]["kg"] += inc.amount_kg
        incomes_by_category[category]["eur"] += inc.total

    expenses_by_category: dict[str, float] = defaultdict(float)
    expenses_by_person: dict[str, float] = defaultdict(float)
    for exp in expenses:
        category = exp.category or "Sin categoría"
        person = exp.person or "Sin persona"
        expenses_by_category[category] += exp.amount
        expenses_by_person[person] += exp.amount

    wells_by_campaign: dict[int, int] = defaultdict(int)
    wells_by_plot: dict[int, int] = defaultdict(int)
    for well in wells:
        wells_by_campaign[campaign_year(well.date)] += well.wells_per_plant
        wells_by_plot[well.plot_id] += well.wells_per_plant

    plants_by_plot: dict[int, int] = defaultdict(int)
    plant_labels_by_id: dict[int, str] = {}
    for plant in plants:
        plants_by_plot[plant.plot_id] += 1
        if getattr(plant, "id", None) is not None and getattr(plant, "label", None):
            plant_labels_by_id[int(plant.id)] = str(plant.label)

    production_by_plot: dict[int, float] = defaultdict(float)
    production_by_campaign: dict[int, float] = defaultdict(float)
    qr_events_by_plant: dict[int, int] = defaultdict(int)
    production_events_total = 0
    production_events_qr = 0
    production_events_manual = 0
    estimated_weight_grams_total = 0.0
    for event in truffle_events:
        if event.undone_at is not None:
            continue
        production_events_total += 1
        estimated_weight_grams_total += event.estimated_weight_grams
        production_by_plot[event.plot_id] += event.estimated_weight_grams
        campaign = campaign_year(event.created_at.date())
        production_by_campaign[campaign] += event.estimated_weight_grams
        if event.source == "qr":
            production_events_qr += 1
            qr_events_by_plant[event.plant_id] += 1
        else:
            production_events_manual += 1

    fence_events_by_plot: dict[int, int] = defaultdict(int)
    management_events_by_campaign: dict[int, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for event in plot_events:
        campaign = campaign_year(event.date)
        management_events_by_campaign[campaign][event.event_type] += 1
        if event.event_type == EventType.VALLADO.value:
            fence_events_by_plot[event.plot_id] += 1

    management_events_totals: dict[str, int] = defaultdict(int)
    for per_campaign in management_events_by_campaign.values():
        for event_type, count in per_campaign.items():
            management_events_totals[event_type] += count

    expenses_raw: dict[int, dict[int | None, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    for exp in expenses:
        expenses_raw[campaign_year(exp.date)][exp.plot_id] += exp.amount
    distributed_expenses_by_campaign_plot = distribute_unassigned_expenses(
        expenses_raw, plots
    )

    distributed_expenses_by_campaign: dict[int, float] = {
        cy: sum(plot_amounts.values())
        for cy, plot_amounts in distributed_expenses_by_campaign_plot.items()
    }

    distributed_plot_profitability: dict[int, float] = defaultdict(float)
    for plot in plots:
        incomes_plot = income_by_plot.get(plot.id, 0.0)
        expenses_plot_distributed = sum(
            distributed_expenses_by_campaign_plot.get(cy, {}).get(plot.id, 0.0)
            for cy in distributed_expenses_by_campaign_plot.keys()
        )
        distributed_plot_profitability[plot.id] = (
            incomes_plot - expenses_plot_distributed
        )

    per_plot_rows: list[tuple[int, str, float, float, float]] = []
    for plot in plots:
        incomes_plot = income_by_plot.get(plot.id, 0.0)
        expenses_plot = expense_by_plot.get(plot.id, 0.0)
        profitability = incomes_plot - expenses_plot
        per_plot_rows.append(
            (plot.id, plot.name, incomes_plot, expenses_plot, profitability)
        )

    total_incomes = sum(inc.total for inc in incomes)
    total_expenses = sum(exp.amount for exp in expenses)
    total_irrigation = sum(r.water_m3 for r in irrigations)
    total_profitability = total_incomes - total_expenses

    lines: list[str] = []
    if plots:
        names = ", ".join(p.name for p in plots)
        total_plants = sum(p.num_plants for p in plots)
        irrigated_plots = sum(1 for p in plots if p.has_irrigation)
        total_area_ha = sum((p.area_ha or 0.0) for p in plots)
        with_sector = sum(1 for p in plots if (p.sector or "").strip())
        with_cadastral = sum(1 for p in plots if (p.cadastral_ref or "").strip())
        lines.append(
            f"Parcelas ({len(plots)}): {names}. Total plantas: {total_plants}."
        )
        lines.append(
            "Gestión de parcelas: "
            f"{irrigated_plots}/{len(plots)} con riego, "
            f"{with_sector} con sector, {with_cadastral} con referencia catastral, "
            f"superficie total {format_eu(total_area_ha, 2)} ha."
        )
        lines.append("Ficha de parcelas (resumen):")
        for plot in sorted(plots, key=lambda p: p.name)[:10]:
            lines.append(
                f"  {plot.name}: num={plot.plot_num or 'N/A'} | "
                f"sector={plot.sector or 'N/A'} | "
                f"catastral={plot.cadastral_ref or 'N/A'} | "
                f"hidrante={plot.hydrant or 'N/A'} | "
                f"riego={'sí' if plot.has_irrigation else 'no'} | "
                f"área={format_eu(plot.area_ha, 2) if plot.area_ha else 'N/A'} ha."
            )

    lines.append(
        "Resumen global: "
        f"ingresos {_format_eur(total_incomes)} | "
        f"gastos {_format_eur(total_expenses)} | "
        f"rentabilidad {_format_eur(total_profitability)} | "
        f"gastos generales {_format_eur(unassigned_expenses_total)}."
    )

    if total_irrigation > 0:
        lines.append(f"Riego total registrado: {total_irrigation:.2f} m3.")

    if rainfall_records:
        total_mm = sum(r.precipitation_mm for r in rainfall_records)
        lines.append(
            f"Lluvia (registros manuales): {len(rainfall_records)} registros | "
            f"precipitación total {format_eu(total_mm, 1)} mm."
        )

    if wells:
        lines.append(
            f"Pozos/labores de pozo registradas: {len(wells)} (total pozos por planta acumulados: {sum(w.wells_per_plant for w in wells)})."
        )

    if plants:
        lines.append(
            f"Mapa de plantas: {len(plants)} etiquetas de planta registradas en {len(set(p.plot_id for p in plants))} parcelas."
        )

    if plot_harvests:
        total_harvest_g = sum(h.weight_grams for h in plot_harvests)
        lines.append(
            f"Cosechas por bancal: {len(plot_harvests)} registros | "
            f"peso total {format_eu(total_harvest_g / 1000.0, 3)} kg."
        )

    if production_events_total > 0:
        lines.append(
            "Producción (eventos trufa): "
            f"{production_events_total} eventos activos | "
            f"manual {production_events_manual} | QR {production_events_qr} | "
            f"peso estimado {estimated_weight_grams_total:.1f} g."
        )

    if qr_events_by_plant:
        top_qr_plants = sorted(
            qr_events_by_plant.items(), key=lambda item: item[1], reverse=True
        )[:5]
        lines.append(
            "QR (plantas más escaneadas): "
            + " | ".join(
                f"{plant_labels_by_id.get(plant_id, f'plant#{plant_id}')}: {count}"
                for plant_id, count in top_qr_plants
            )
            + "."
        )

    if management_events_totals:
        lines.append(
            "Historial de labores (totales): "
            + ", ".join(
                f"{event_type} {count}"
                for event_type, count in sorted(management_events_totals.items())
            )
            + "."
        )

    if incomes_by_category:
        top_income_categories = sorted(
            incomes_by_category.items(),
            key=lambda item: item[1]["eur"],
            reverse=True,
        )[:3]
        lines.append(
            "Ingresos por categoría (top): "
            + " | ".join(
                f"{cat}: {_format_eur(vals['eur'])} ({format_eu(vals['kg'], 2)} kg)"
                for cat, vals in top_income_categories
            )
            + "."
        )

    if expenses_by_category:
        top_expense_categories = sorted(
            expenses_by_category.items(), key=lambda item: item[1], reverse=True
        )
        lines.append(
            "Gastos por categoría: "
            + " | ".join(
                f"{cat}: {_format_eur(amount)}"
                for cat, amount in top_expense_categories
            )
            + "."
        )

    if expenses_by_person:
        top_expense_people = sorted(
            expenses_by_person.items(), key=lambda item: item[1], reverse=True
        )
        lines.append(
            "Gastos por persona: "
            + " | ".join(
                f"{person}: {_format_eur(amount)}"
                for person, amount in top_expense_people
            )
            + "."
        )

    if recurring_expenses_list:
        active_count = sum(1 for r in recurring_expenses_list if r.is_active)
        lines.append(
            f"Gastos recurrentes: {len(recurring_expenses_list)} plantillas "
            f"({active_count} activas)."
        )

    fenced_plot_names = [
        plot.name for plot in plots if fence_events_by_plot.get(plot.id, 0) > 0
    ]
    if fenced_plot_names:
        lines.append(
            "Parcelas con vallado registrado: " + ", ".join(fenced_plot_names) + "."
        )
    else:
        lines.append("No hay eventos de vallado registrados por parcela.")

    all_years = sorted(
        set(
            list(income_by_campaign.keys())
            + list(expense_by_campaign.keys())
            + list(irrigation_by_campaign.keys())
            + list(distributed_expenses_by_campaign.keys())
            + list(income_kg_by_campaign.keys())
        ),
        reverse=True,
    )
    if all_years:
        lines.append("Resumen por campaña (valores agregados):")

        campaign_profitability: list[tuple[int, float]] = []
        campaign_profitability_distributed: list[tuple[int, float]] = []
        for year in all_years:
            inc = income_by_campaign.get(year, 0.0)
            exp = expense_by_campaign.get(year, 0.0)
            profit = inc - exp
            exp_distributed = distributed_expenses_by_campaign.get(year, exp)
            profit_distributed = inc - exp_distributed
            water = irrigation_by_campaign.get(year, 0.0)
            campaign_profitability.append((year, profit))
            campaign_profitability_distributed.append((year, profit_distributed))
            lines.append(
                f"  {campaign_label(year)}: ingresos {_format_eur(inc)} | "
                f"gastos {_format_eur(exp)} | rentabilidad {_format_eur(profit)}"
                + (
                    f" | rentab. ajustada {_format_eur(profit_distributed)}"
                    if exp_distributed != exp
                    else ""
                )
                + (f" | riego {water:.2f} m3" if water > 0 else "")
                + (
                    f" | pozos/planta {wells_by_campaign.get(year, 0)}"
                    if wells_by_campaign.get(year, 0) > 0
                    else ""
                )
                + (
                    f" | prod. estimada {production_by_campaign.get(year, 0.0):.1f} g"
                    if production_by_campaign.get(year, 0.0) > 0
                    else ""
                )
                + (
                    f" | kg vendidos {format_eu(income_kg_by_campaign.get(year, 0.0), 2)}"
                    if income_kg_by_campaign.get(year, 0.0) > 0
                    else ""
                )
            )

            events_snapshot = management_events_by_campaign.get(year)
            if events_snapshot:
                lines.append(
                    "    labores: "
                    + ", ".join(
                        f"{event_type} {count}"
                        for event_type, count in sorted(events_snapshot.items())
                    )
                )

        best_year, best_value = max(campaign_profitability, key=lambda item: item[1])
        worst_year, worst_value = min(campaign_profitability, key=lambda item: item[1])
        best_year_adj, best_value_adj = max(
            campaign_profitability_distributed, key=lambda item: item[1]
        )
        worst_year_adj, worst_value_adj = min(
            campaign_profitability_distributed, key=lambda item: item[1]
        )
        lines.append(
            "Campañas destacadas: "
            f"mejor {campaign_label(best_year)} ({_format_eur(best_value)}), "
            f"peor {campaign_label(worst_year)} ({_format_eur(worst_value)})."
        )
        lines.append(
            "Campañas destacadas (rentabilidad ajustada): "
            f"mejor {campaign_label(best_year_adj)} ({_format_eur(best_value_adj)}), "
            f"peor {campaign_label(worst_year_adj)} ({_format_eur(worst_value_adj)})."
        )

    if per_plot_rows:
        lines.append("Resumen por parcela (gastos directos):")
        for plot_id, name, inc, exp, profitability in sorted(
            per_plot_rows,
            key=lambda row: row[4],
            reverse=True,
        ):
            water = irrigation_by_plot.get(plot_id, 0.0)
            lines.append(
                f"  {name}: ingresos {_format_eur(inc)} | gastos {_format_eur(exp)} | "
                f"rentabilidad {_format_eur(profitability)}"
                + (f" | riego {water:.2f} m3" if water > 0 else "")
                + (
                    f" | pozos/planta {wells_by_plot.get(plot_id, 0)}"
                    if wells_by_plot.get(plot_id, 0) > 0
                    else ""
                )
                + (
                    f" | prod. estimada {production_by_plot.get(plot_id, 0.0):.1f} g"
                    if production_by_plot.get(plot_id, 0.0) > 0
                    else ""
                )
                + (
                    f" | mapa {plants_by_plot.get(plot_id, 0)} plantas"
                    if plants_by_plot.get(plot_id, 0) > 0
                    else ""
                )
                + (
                    f" | vallado {fence_events_by_plot.get(plot_id, 0)}"
                    if fence_events_by_plot.get(plot_id, 0) > 0
                    else ""
                )
            )

        distributed_top = sorted(
            (
                (
                    plot.id,
                    plot.name,
                    distributed_plot_profitability.get(plot.id, 0.0),
                )
                for plot in plots
            ),
            key=lambda item: item[2],
            reverse=True,
        )
        lines.append("Resumen por parcela (rentabilidad ajustada):")
        for _, name, profitability in distributed_top:
            lines.append(
                f"  {name}: rentabilidad ajustada {_format_eur(profitability)}"
            )

    total_income_kg = sum(inc.amount_kg for inc in incomes)
    roi_pct = (
        ((total_incomes - total_expenses) / total_expenses) * 100.0
        if total_expenses > 0
        else None
    )
    water_per_kg = (total_irrigation / total_income_kg) if total_income_kg > 0 else None
    average_price = (total_incomes / total_income_kg) if total_income_kg > 0 else None
    growth_pct = None
    if len(all_years) >= 2:
        latest_year = all_years[0]
        previous_year = all_years[1]
        latest_kg = income_kg_by_campaign.get(latest_year, 0.0)
        previous_kg = income_kg_by_campaign.get(previous_year, 0.0)
        if previous_kg > 0:
            growth_pct = ((latest_kg - previous_kg) / previous_kg) * 100.0
    lines.append(
        "KPIs rápidos: "
        f"ROI {format_eu(roi_pct, 2) if roi_pct is not None else 'N/A'}% | "
        f"€/kg medio {format_eu(average_price, 2) if average_price is not None else 'N/A'} | "
        f"m3/kg {format_eu(water_per_kg, 2) if water_per_kg is not None else 'N/A'} | "
        f"crec. kg {format_eu(growth_pct, 2) if growth_pct is not None else 'N/A'}% | "
        f"kg totales vendidos {format_eu(total_income_kg, 2)}."
    )

    weekly_points = len(
        {(inc.date.isocalendar().year, inc.date.isocalendar().week) for inc in incomes}
    )
    lines.append(
        "Gráficas disponibles (resumen): "
        f"{len(all_years)} campañas comparables, "
        f"{weekly_points} puntos semanales de ingreso para evolución, "
        f"{len(expenses_by_category)} categorías de gasto y {len(incomes_by_category)} categorías de ingreso."
    )
    lines.append(
        "Comparativas gráficas clave: evolución semanal, acumulado de ingresos, mix por categorías, "
        "comparativa ingresos vs gastos por parcela y tendencia KPI por campaña."
    )

    return "\n".join(lines) if lines else "Sin datos registrados aún."


def _compose_messages(
    message: str,
    history: list[dict],
    user_ctx: str,
) -> list[dict]:
    system_content = _APP_KNOWLEDGE
    if user_ctx:
        system_content += (
            "\n\nDATOS ACTUALES DEL USUARIO (solo lectura, valores agregados):\n"
            + user_ctx
        )
    messages: list[dict] = [{"role": "system", "content": system_content}]
    for turn in history[-_MAX_HISTORY_TURNS:]:
        messages.append(turn)
    messages.append({"role": "user", "content": message[:_MAX_MESSAGE_LEN]})
    return messages


async def chat(
    db: AsyncSession,
    user_id: int,
    message: str,
    history: list[dict],
    adapter: LLMAdapter,
) -> dict:
    """Orchestrate an assistant response: classify intent, build context, call LLM."""
    context = await prepare_chat_context(db, user_id, message, history)
    messages = context["messages"]
    response = await adapter.complete(messages)
    return {
        "response": response,
        "intent": context["intent"],
        "traceability": context["traceability"],
    }


async def prepare_chat_context(
    db: AsyncSession,
    user_id: int,
    message: str,
    history: list[dict],
) -> dict:
    """Build validated intent + prompt messages for complete/stream chat flows."""
    safe_message = _sanitize_user_message(message)
    intent = _classify_intent(safe_message)
    user_ctx = ""
    if intent == "datos":
        user_ctx = await _build_user_context(db, user_id)
    messages = _compose_messages(safe_message, history, user_ctx)
    return {
        "intent": intent,
        "messages": messages,
        "traceability": _build_traceability(intent),
    }
