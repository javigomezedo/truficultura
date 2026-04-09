from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense
from app.models.income import Income
from app.models.plot import Plot
from app.services.llm_adapter import LLMAdapter
from app.utils import campaign_label, campaign_year

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
    "mío",
    "mía",
    "cuánto he",
    "cuánto tengo",
    "cuánto llevo",
    "cuál fue mi",
    "cuál es mi",
    "cuáles son mis",
    "mi mejor",
    "mi peor",
    "mejor campaña",
    "peor campaña",
    "mis datos",
    "mi rentabilidad",
}


def _classify_intent(message: str) -> str:
    """Return 'datos' if the query is about the user's own data, else 'uso'."""
    lowered = message.lower()
    for kw in _DATA_KEYWORDS:
        if kw in lowered:
            return "datos"
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

    income_by_campaign: dict[int, float] = defaultdict(float)
    for inc in incomes:
        income_by_campaign[campaign_year(inc.date)] += inc.total

    expense_by_campaign: dict[int, float] = defaultdict(float)
    for exp in expenses:
        expense_by_campaign[campaign_year(exp.date)] += exp.amount

    lines: list[str] = []
    if plots:
        names = ", ".join(p.name for p in plots)
        total_plants = sum(p.num_plants for p in plots)
        lines.append(
            f"Parcelas ({len(plots)}): {names}. Total plantas: {total_plants}."
        )

    all_years = sorted(
        set(list(income_by_campaign.keys()) + list(expense_by_campaign.keys())),
        reverse=True,
    )
    if all_years:
        lines.append("Resumen por campaña (valores agregados):")
        for year in all_years:
            inc = income_by_campaign.get(year, 0.0)
            exp = expense_by_campaign.get(year, 0.0)
            profit = inc - exp
            lines.append(
                f"  {campaign_label(year)}: ingresos {inc:.2f}€ | "
                f"gastos {exp:.2f}€ | rentabilidad {profit:.2f}€"
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
    intent = _classify_intent(message)
    user_ctx = ""
    if intent == "datos":
        user_ctx = await _build_user_context(db, user_id)
    messages = _compose_messages(message, history, user_ctx)
    response = await adapter.complete(messages)
    return {"response": response, "intent": intent}
