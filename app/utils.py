import datetime
from collections import defaultdict


def campaign_year(date: datetime.date) -> int:
    """Return the campaign year (April-March). E.g.: Feb-2023 -> 2022, Nov-2022 -> 2022."""
    return date.year if date.month >= 4 else date.year - 1


def campaign_label(year: int) -> str:
    """Format the campaign year. E.g.: 2022 -> '2022/23'."""
    return f"{year}/{str(year + 1)[-2:]}"


def distribute_unassigned_expenses(
    expenses_by_cy_plot: dict,
    plots: list,
) -> dict:
    """
    Distribute expenses with no plot (plot_id=None) among plots
    proportionally according to the 'percentage' field.

    Returns a new dict with the same structure but without the None key.
    """
    total_pct = 100.0
    result: dict = defaultdict(lambda: defaultdict(float))

    for cy, by_p in expenses_by_cy_plot.items():
        unassigned = by_p.get(None, 0.0)
        for pid, amount in by_p.items():
            if pid is None:
                continue
            result[cy][pid] += amount
        # Distribute unassigned proportionally
        if unassigned > 0:
            for p in plots:
                pct = p.percentage or 0.0
                result[cy][p.id] += unassigned * (pct / total_pct)

    return result
