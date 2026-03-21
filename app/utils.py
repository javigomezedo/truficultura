import datetime
from collections import defaultdict


def campaign_year(fecha: datetime.date) -> int:
    """Devuelve el año de campaña (Abril-Marzo). Ej: feb-2023 -> 2022, nov-2022 -> 2022."""
    return fecha.year if fecha.month >= 4 else fecha.year - 1


def campaign_label(year: int) -> str:
    """Formatea el año de campaña. Ej: 2022 -> '2022/23'."""
    return f"{year}/{str(year + 1)[-2:]}"


def distribute_unassigned_gastos(
    gastos_by_cy_p: dict,
    parcelas: list,
) -> dict:
    """
    Distribuye los gastos sin bancal (parcela_id=None) entre las parcelas
    proporcionalmente a su campo 'porcentaje'.

    Devuelve un nuevo dict con la misma estructura pero sin la clave None.
    """
    total_pct = 100.0
    result: dict = defaultdict(lambda: defaultdict(float))

    for cy, by_p in gastos_by_cy_p.items():
        unassigned = by_p.get(None, 0.0)
        for pid, amount in by_p.items():
            if pid is None:
                continue
            result[cy][pid] += amount
        # Distribute unassigned proportionally
        if unassigned > 0:
            for p in parcelas:
                pct = p.porcentaje or 0.0
                result[cy][p.id] += unassigned * (pct / total_pct)

    return result
