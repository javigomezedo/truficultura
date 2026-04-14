from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense
from app.models.income import Income
from app.models.irrigation import IrrigationRecord
from app.models.plot import Plot
from app.services.llm_adapter import LLMAdapter
from app.utils import campaign_label, campaign_year, format_eu

_MAX_HISTORY_TURNS = 5
_MAX_MESSAGE_LEN = 1000

_APP_KNOWLEDGE = """Eres el asistente de Truficultura, una aplicación web para gestionar \
explotaciones trufícolas. Respondes siempre en español, con claridad y concisión. \
No ejecutas acciones: solo explicas y consultas datos en modo lectura.

MÓDULOS DE LA APLICACIÓN:
- Parcelas: gestión de bancales (nombre, número de plantas, referencia catastral, sector, \
superficie, fechas de plantación e inicio de producción). Cada parcela tiene un mapa visual \
de plantas con etiquetas (A1, B3...).
- Producción (Trufas): registro de eventos de trufa por planta, con historial y filtros por \
campaña/parcela/planta. Se puede registrar manualmente o por escaneo QR.
- Riego: registro de riegos por parcela con volumen de agua y notas. Se activa parcela a parcela.
- Ingresos: fecha, parcela (opcional), categoría de trufa (Extra, A, B...), kg y €/kg. \
El total (€) se calcula automáticamente: cantidad_kg × euros_kg.
- Gastos: fecha, descripción, persona, parcela (opcional), importe y categoría. Los gastos \
sin parcela asignada son "generales" y se distribuyen entre todas las parcelas \
proporcionalmente al número de plantas.
- Rentabilidad: informe por campaña y parcela con ingresos, gastos y rentabilidad neta.
- Gráficas: evolución semanal y comparativa ingresos vs gastos por campaña.
- Importar/Exportar: CSV con punto y coma como separador, formato numérico europeo (1.250,50) \
y fechas dd/mm/aaaa.
- Admin (solo administrador): gestión de usuarios.

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
    "db:incomes",
    "db:expenses",
    "db:irrigation",
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

    if not plots and not incomes and not expenses and not irrigations:
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
        lines.append(
            f"Parcelas ({len(plots)}): {names}. Total plantas: {total_plants}."
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

    all_years = sorted(
        set(
            list(income_by_campaign.keys())
            + list(expense_by_campaign.keys())
            + list(irrigation_by_campaign.keys())
        ),
        reverse=True,
    )
    if all_years:
        lines.append("Resumen por campaña (valores agregados):")

        campaign_profitability: list[tuple[int, float]] = []
        for year in all_years:
            inc = income_by_campaign.get(year, 0.0)
            exp = expense_by_campaign.get(year, 0.0)
            profit = inc - exp
            water = irrigation_by_campaign.get(year, 0.0)
            campaign_profitability.append((year, profit))
            lines.append(
                f"  {campaign_label(year)}: ingresos {_format_eur(inc)} | "
                f"gastos {_format_eur(exp)} | rentabilidad {_format_eur(profit)}"
                + (f" | riego {water:.2f} m3" if water > 0 else "")
            )

        best_year, best_value = max(campaign_profitability, key=lambda item: item[1])
        worst_year, worst_value = min(campaign_profitability, key=lambda item: item[1])
        lines.append(
            "Campañas destacadas: "
            f"mejor {campaign_label(best_year)} ({_format_eur(best_value)}), "
            f"peor {campaign_label(worst_year)} ({_format_eur(worst_value)})."
        )

    if per_plot_rows:
        lines.append("Resumen por parcela (gastos directos):")
        for plot_id, name, inc, exp, profitability in sorted(
            per_plot_rows,
            key=lambda row: row[4],
            reverse=True,
        )[:3]:
            water = irrigation_by_plot.get(plot_id, 0.0)
            lines.append(
                f"  {name}: ingresos {_format_eur(inc)} | gastos {_format_eur(exp)} | "
                f"rentabilidad {_format_eur(profitability)}"
                + (f" | riego {water:.2f} m3" if water > 0 else "")
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
