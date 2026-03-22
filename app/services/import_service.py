from __future__ import annotations

import csv
import datetime
import io
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense
from app.models.income import Income
from app.models.plot import Plot


def _parse_date(s: str) -> datetime.date:
    return datetime.datetime.strptime(s.strip(), "%d/%m/%Y").date()


def _parse_num(s: str) -> float:
    s = s.strip()
    if not s:
        return 0.0
    return float(s.replace(".", "").replace(",", "."))


async def _load_plots(db: AsyncSession) -> dict[str, int]:
    result = await db.execute(select(Plot))
    return {p.name.lower(): p.id for p in result.scalars().all()}


async def import_expenses_csv(
    db: AsyncSession, content: bytes
) -> tuple[list[Expense], list[str]]:
    """Parse expenses CSV and persist rows.

    Expected format (semicolon-delimited, no header):
        fecha;concepto;persona;bancal;cantidad[;categoria]

    - fecha:    DD/MM/YYYY
    - concepto: description text
    - persona:  person name
    - bancal:   plot name (optional — leave empty for general expenses)
    - cantidad: amount in European format (e.g. 1.250,00)
    - categoria: expense category (optional, e.g. Riego)
    """
    plots = await _load_plots(db)
    rows: list[Expense] = []
    warnings: list[str] = []

    reader = csv.reader(io.StringIO(content.decode("utf-8")), delimiter=";")
    for i, line in enumerate(reader, 1):
        if not any(line):
            continue
        if len(line) < 5:
            warnings.append(
                f"Línea {i}: se esperaban 5 columnas, se encontraron {len(line)} — omitida"
            )
            continue

        fecha_s, concepto, persona, bancal, cantidad_s = line[:5]
        categoria = line[5].strip() if len(line) > 5 else None
        bancal = bancal.strip()
        plot_id: Optional[int] = None

        if bancal:
            plot_id = plots.get(bancal.lower())
            if plot_id is None:
                warnings.append(
                    f"Línea {i}: bancal '{bancal}' no encontrado — importado sin bancal"
                )

        try:
            row = Expense(
                date=_parse_date(fecha_s),
                description=concepto.strip(),
                person=persona.strip(),
                plot_id=plot_id,
                amount=_parse_num(cantidad_s),
                category=categoria or None,
            )
            rows.append(row)
        except (ValueError, KeyError) as exc:
            warnings.append(f"Línea {i}: error al parsear — {exc} — omitida")

    db.add_all(rows)
    return rows, warnings


async def import_incomes_csv(
    db: AsyncSession, content: bytes
) -> tuple[list[Income], list[str]]:
    """Parse incomes CSV and persist rows.

    Expected format (semicolon-delimited, no header):
        fecha;bancal;kg;categoria;euros_kg

    - fecha:    DD/MM/YYYY
    - bancal:   plot name (optional)
    - kg:       kilograms in European format (e.g. 2,500)
    - categoria: category label (optional)
    - euros_kg: price per kg in European format (e.g. 120,00)
    """
    plots = await _load_plots(db)
    rows: list[Income] = []
    warnings: list[str] = []

    reader = csv.reader(io.StringIO(content.decode("utf-8")), delimiter=";")
    for i, line in enumerate(reader, 1):
        if not any(line):
            continue
        if len(line) < 5:
            warnings.append(
                f"Línea {i}: se esperaban 5 columnas, se encontraron {len(line)} — omitida"
            )
            continue

        fecha_s, bancal, kg_s, categoria, euros_kg_s = line[:5]
        bancal = bancal.strip()
        plot_id: Optional[int] = plots.get(bancal.lower()) if bancal else None

        if bancal and plot_id is None:
            warnings.append(
                f"Línea {i}: bancal '{bancal}' no encontrado — importado sin bancal"
            )

        try:
            kg = _parse_num(kg_s)
            euros_per_kg = _parse_num(euros_kg_s)
            row = Income(
                date=_parse_date(fecha_s),
                plot_id=plot_id,
                amount_kg=kg,
                category=categoria.strip() or None,
                euros_per_kg=euros_per_kg,
                total=round(kg * euros_per_kg, 2),
            )
            rows.append(row)
        except (ValueError, KeyError) as exc:
            warnings.append(f"Línea {i}: error al parsear — {exc} — omitida")

    db.add_all(rows)
    return rows, warnings
