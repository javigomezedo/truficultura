import datetime
from collections import defaultdict


def _expand_column_token(token: str) -> list[int]:
    token = token.strip()
    if not token:
        raise ValueError("Formato incorrecto")
    if "-" in token:
        parts = token.split("-", 1)
        if len(parts) != 2:
            raise ValueError("Formato incorrecto")
        start = int(parts[0].strip())
        end = int(parts[1].strip())
        if start <= 0 or end <= 0 or end < start:
            raise ValueError("Formato incorrecto")
        return list(range(start, end + 1))

    value = int(token)
    if value <= 0:
        raise ValueError("Formato incorrecto")
    return [value]


def parse_row_config(row_config: str) -> list[list[int]]:
    """Parse map row configuration.

    Supported formats:
    - Sparse rows with explicit columns: "2-5,8;1,3,4;7-9"
    - Sparse rows with optional prefixes: "A:2-5,8;B:1,3,4"
    """
    raw = (row_config or "").strip()
    if not raw:
        raise ValueError("Debes definir al menos una fila")

    if ";" not in raw and ":" not in raw and "-" not in raw:
        raise ValueError("Usa el formato nuevo: A:2-5,8; B:1,3,4")

    rows: list[list[int]] = []
    for chunk in [p.strip() for p in raw.split(";") if p.strip()]:
        payload = chunk.split(":", 1)[1].strip() if ":" in chunk else chunk
        if not payload:
            raise ValueError("Formato incorrecto")

        cols: list[int] = []
        try:
            for token in [t.strip() for t in payload.split(",") if t.strip()]:
                cols.extend(_expand_column_token(token))
        except ValueError as exc:
            raise ValueError("Formato incorrecto") from exc

        dedup_sorted = sorted(set(cols))
        if not dedup_sorted:
            raise ValueError("Debes definir al menos una fila")
        rows.append(dedup_sorted)

    if not rows:
        raise ValueError("Debes definir al menos una fila")
    return rows


def _compress_columns(columns: list[int]) -> str:
    if not columns:
        return ""
    ranges: list[str] = []
    start = prev = columns[0]
    for value in columns[1:]:
        if value == prev + 1:
            prev = value
            continue
        ranges.append(f"{start}-{prev}" if start != prev else str(start))
        start = prev = value
    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(ranges)


def format_sparse_row_config(row_columns: list[list[int]]) -> str:
    """Return canonical sparse configuration text from row columns."""
    rows: list[str] = []
    for idx, columns in enumerate(row_columns):
        label = row_label_from_index(idx)
        rows.append(f"{label}:{_compress_columns(sorted(set(columns)))}")
    return "; ".join(rows)


def campaign_year(date: datetime.date) -> int:
    """Return the campaign year (May-April). E.g.: Apr-2023 -> 2022, Nov-2022 -> 2022."""
    return date.year if date.month >= 5 else date.year - 1


def campaign_label(year: int) -> str:
    """Format the campaign year. E.g.: 2022 -> '2022/23'."""
    return f"{year}/{str(year + 1)[-2:]}"


def campaign_months(year: int) -> str:
    """Return the month range for a campaign. E.g.: 2022 -> 'Mayo 2022 - Abril 2023'."""
    start_month = "Mayo"
    end_month = "Abril"
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
