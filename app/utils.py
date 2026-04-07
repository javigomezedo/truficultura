import datetime
from collections import defaultdict


def campaign_year(date: datetime.date) -> int:
    """Return the campaign year (April-March). E.g.: Feb-2023 -> 2022, Nov-2022 -> 2022."""
    return date.year if date.month >= 4 else date.year - 1


def campaign_label(year: int) -> str:
    """Format the campaign year. E.g.: 2022 -> '2022/23'."""
    return f"{year}/{str(year + 1)[-2:]}"


def campaign_months(year: int) -> str:
    """Return the month range for a campaign. E.g.: 2022 -> 'Abril 2022 - Marzo 2023'."""
    start_month = "Abril"
    end_month = "Marzo"
    return f"{start_month} {year} - {end_month} {year + 1}"


def row_label_from_index(n: int) -> str:
    """Convert a 0-based row index to an Excel-style column label.

    0 -> 'A', 1 -> 'B', ..., 25 -> 'Z', 26 -> 'AA', 27 -> 'AB', ...
    """
    label = ""
    n += 1  # work in 1-based space
    while n > 0:
        n -= 1
        label = chr(ord("A") + n % 26) + label
        n //= 26
    return label


def generate_plant_labels(row_counts: list[int]) -> list[list[str]]:
    """Given a list of plant counts per row, return a 2D list of plant labels.

    Example: [4, 5, 3] -> [['A1','A2','A3','A4'], ['B1','B2','B3','B4','B5'], ['C1','C2','C3']]
    """
    grid: list[list[str]] = []
    for row_idx, count in enumerate(row_counts):
        rl = row_label_from_index(row_idx)
        grid.append([f"{rl}{col + 1}" for col in range(count)])
    return grid


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
