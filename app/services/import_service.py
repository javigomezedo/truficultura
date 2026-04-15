from __future__ import annotations

import csv
import datetime
import io
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import _
from app.models.expense import Expense
from app.models.income import Income
from app.models.irrigation import IrrigationRecord
from app.models.plant import Plant
from app.models.plot import Plot
from app.models.truffle_event import TruffleEvent
from app.models.well import Well
from app.utils import parse_row_config


def _parse_date_opt(s: str) -> Optional[datetime.date]:
    s = s.strip()
    if not s:
        return None
    return _parse_date(s)


def _parse_int(s: str) -> int:
    s = s.strip()
    if not s:
        return 0
    return int(s.replace(".", "").replace(",", "."))


def _parse_date(s: str) -> datetime.date:
    return datetime.datetime.strptime(s.strip(), "%d/%m/%Y").date()


def _parse_num(s: str) -> float:
    s = s.strip()
    if not s:
        return 0.0
    return float(s.replace(".", "").replace(",", "."))


def _parse_datetime(s: str) -> datetime.datetime:
    dt = datetime.datetime.strptime(s.strip(), "%d/%m/%Y %H:%M:%S")
    return dt.replace(tzinfo=datetime.timezone.utc)


async def _load_plots(db: AsyncSession, user_id: int) -> dict[str, int]:
    result = await db.execute(select(Plot).where(Plot.user_id == user_id))
    return {p.name.lower(): p.id for p in result.scalars().all()}


def _warning(message: str, **kwargs: object) -> str:
    return _(message, **kwargs)


async def import_expenses_csv(
    db: AsyncSession, content: bytes, user_id: int
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
    plots = await _load_plots(db, user_id)
    rows: list[Expense] = []
    warnings: list[str] = []

    reader = csv.reader(io.StringIO(content.decode("utf-8")), delimiter=";")
    for i, line in enumerate(reader, 1):
        if not any(line):
            continue
        if len(line) < 5:
            warnings.append(
                _warning(
                    "Línea {line}: se esperaban 5 columnas, se encontraron {count} — omitida",
                    line=i,
                    count=len(line),
                )
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
                    _warning(
                        "Línea {line}: bancal '{plot}' no encontrado — importado sin bancal",
                        line=i,
                        plot=bancal,
                    )
                )

        try:
            row = Expense(
                user_id=user_id,
                date=_parse_date(fecha_s),
                description=concepto.strip(),
                person=persona.strip(),
                plot_id=plot_id,
                amount=_parse_num(cantidad_s),
                category=categoria or None,
            )
            rows.append(row)
        except (ValueError, KeyError):
            warnings.append(
                _warning("Línea {line}: error al parsear los datos — omitida", line=i)
            )

    db.add_all(rows)
    return rows, warnings


async def import_incomes_csv(
    db: AsyncSession, content: bytes, user_id: int
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
    plots = await _load_plots(db, user_id)
    rows: list[Income] = []
    warnings: list[str] = []

    reader = csv.reader(io.StringIO(content.decode("utf-8")), delimiter=";")
    for i, line in enumerate(reader, 1):
        if not any(line):
            continue
        if len(line) < 5:
            warnings.append(
                _warning(
                    "Línea {line}: se esperaban 5 columnas, se encontraron {count} — omitida",
                    line=i,
                    count=len(line),
                )
            )
            continue

        fecha_s, bancal, kg_s, categoria, euros_kg_s = line[:5]
        bancal = bancal.strip()
        plot_id: Optional[int] = plots.get(bancal.lower()) if bancal else None

        if bancal and plot_id is None:
            warnings.append(
                _warning(
                    "Línea {line}: bancal '{plot}' no encontrado — importado sin bancal",
                    line=i,
                    plot=bancal,
                )
            )

        try:
            kg = _parse_num(kg_s)
            euros_per_kg = _parse_num(euros_kg_s)
            row = Income(
                user_id=user_id,
                date=_parse_date(fecha_s),
                plot_id=plot_id,
                amount_kg=kg,
                category=categoria.strip() or None,
                euros_per_kg=euros_per_kg,
            )
            rows.append(row)
        except (ValueError, KeyError):
            warnings.append(
                _warning("Línea {line}: error al parsear los datos — omitida", line=i)
            )

    db.add_all(rows)
    return rows, warnings


async def import_plots_csv(
    db: AsyncSession, content: bytes, user_id: int
) -> tuple[list[Plot], list[str]]:
    """Parse plots CSV and persist rows.

    Expected format (semicolon-delimited, no header, min 2 columns):
        nombre;fecha_plantacion[;poligono;parcela;ref_catastral;hidrante;sector;n_plantas;superficie_ha;inicio_produccion[;tiene_riego[;config_mapa]]]

    - nombre:            plot name (required)
    - fecha_plantacion:  planting date DD/MM/YYYY (required)
    - poligono:          polygon reference (optional)
    - parcela:           plot number within polygon (optional)
    - ref_catastral:     official cadastral reference (optional)
    - hidrante:          hydrant identifier (optional)
    - sector:            sector (optional)
    - n_plantas:         number of plants (optional, integer)
    - superficie_ha:     area in hectares (optional, decimal)
    - inicio_produccion: production start date DD/MM/YYYY (optional)
    - tiene_riego:       1 or 0 (optional, default 0 — backward compatible)
    - config_mapa:       sparse map config (optional, e.g. A:1-4; B:2-5)

    Note: Percentage is automatically calculated based on total plant count.
    """
    rows: list[Plot] = []
    pending_map_configs: list[tuple[Plot, str]] = []
    warnings: list[str] = []

    reader = csv.reader(io.StringIO(content.decode("utf-8")), delimiter=";")
    for i, line in enumerate(reader, 1):
        if not any(line):
            continue
        if len(line) < 2:
            warnings.append(
                _warning(
                    "Línea {line}: se esperaban al menos 2 columnas, se encontraron {count} — omitida",
                    line=i,
                    count=len(line),
                )
            )
            continue

        def col(n: int) -> str:
            return line[n].strip() if len(line) > n else ""

        try:
            row = Plot(
                user_id=user_id,
                name=col(0),
                planting_date=_parse_date(col(1)),
                polygon=col(2),
                plot_num=col(3),
                cadastral_ref=col(4),
                hydrant=col(5),
                sector=col(6),
                num_plants=_parse_int(col(7)),
                area_ha=_parse_num(col(8)) or None,
                production_start=_parse_date_opt(col(9)),
                percentage=0.0,
                has_irrigation=bool(_parse_int(col(10))),
            )
            rows.append(row)
            map_config = col(11)
            if map_config:
                pending_map_configs.append((row, map_config))
        except (ValueError, KeyError):
            warnings.append(
                _warning("Línea {line}: error al parsear los datos — omitida", line=i)
            )

    db.add_all(rows)
    await db.flush()

    if pending_map_configs:
        from app.services import plants_service

        for row, map_config in pending_map_configs:
            try:
                row_columns = parse_row_config(map_config)
                await plants_service.configure_plot_map(
                    db,
                    row,
                    user_id=user_id,
                    row_columns=row_columns,
                )
            except ValueError:
                warnings.append(
                    _warning(
                        "Parcela '{plot}': config_mapa inválida — mapa omitido",
                        plot=row.name,
                    )
                )

    # Recalculate percentages after import
    from app.services.plots_service import _recalculate_percentages

    await _recalculate_percentages(db, user_id)
    return rows, warnings


async def import_wells_csv(
    db: AsyncSession, content: bytes, user_id: int
) -> tuple[list[Well], list[str]]:
    """Parse wells CSV and persist rows.

    Expected format (semicolon-delimited, no header):
        fecha;bancal;pozos_por_planta[;notas]

    - fecha:                  DD/MM/YYYY (required)
    - bancal:                 plot name (required)
    - pozos_por_planta:       integer number of wells per plant (required)
    - notas:                  optional free text notes

    Rows are skipped with a warning if the plot is not found for the current user.
    """
    result = await db.execute(select(Plot).where(Plot.user_id == user_id))
    plots_obj: dict[str, Plot] = {p.name.lower(): p for p in result.scalars().all()}

    rows: list[Well] = []
    warnings: list[str] = []

    reader = csv.reader(io.StringIO(content.decode("utf-8")), delimiter=";")
    for i, line in enumerate(reader, 1):
        if not any(line):
            continue
        if len(line) < 3:
            warnings.append(
                _warning(
                    "Línea {line}: se esperaban al menos 3 columnas, se encontraron {count} — omitida",
                    line=i,
                    count=len(line),
                )
            )
            continue

        fecha_s, bancal, wells_s = line[0], line[1].strip(), line[2]
        notas = line[3].strip() if len(line) > 3 else None

        if not bancal:
            warnings.append(
                _warning(
                    "Línea {line}: bancal vacío — omitida (el registro de pozos siempre requiere parcela)",
                    line=i,
                )
            )
            continue

        plot = plots_obj.get(bancal.lower())
        if plot is None:
            warnings.append(
                _warning(
                    "Línea {line}: bancal '{plot}' no encontrado — omitida",
                    line=i,
                    plot=bancal,
                )
            )
            continue

        try:
            row = Well(
                user_id=user_id,
                plot_id=plot.id,
                date=_parse_date(fecha_s),
                wells_per_plant=int(_parse_int(wells_s)),
                notes=notas or None,
                expense_id=None,
            )
            rows.append(row)
        except (ValueError, KeyError):
            warnings.append(
                _warning("Línea {line}: error al parsear los datos — omitida", line=i)
            )

    db.add_all(rows)
    return rows, warnings


async def import_irrigation_csv(
    db: AsyncSession, content: bytes, user_id: int
) -> tuple[list[IrrigationRecord], list[str]]:
    """Parse irrigation records CSV and persist rows.

    Expected format (semicolon-delimited, no header):
        fecha;bancal;agua_m3[;notas]

    - fecha:    DD/MM/YYYY (required)
    - bancal:   plot name (required — irrigation always requires a plot)
    - agua_m3:  water volume in m³, European format (required)
    - notas:    optional free text notes

    Rows are skipped (with a warning) if:
    - the plot is not found for the current user
    - the plot exists but has_irrigation=False
    """
    # We also need has_irrigation per plot — load full plot objects
    result = await db.execute(select(Plot).where(Plot.user_id == user_id))
    plots_obj: dict[str, Plot] = {p.name.lower(): p for p in result.scalars().all()}

    rows: list[IrrigationRecord] = []
    warnings: list[str] = []

    reader = csv.reader(io.StringIO(content.decode("utf-8")), delimiter=";")
    for i, line in enumerate(reader, 1):
        if not any(line):
            continue
        if len(line) < 3:
            warnings.append(
                _warning(
                    "Línea {line}: se esperaban al menos 3 columnas, se encontraron {count} — omitida",
                    line=i,
                    count=len(line),
                )
            )
            continue

        fecha_s, bancal, agua_m3_s = line[0], line[1].strip(), line[2]
        notas = line[3].strip() if len(line) > 3 else None

        if not bancal:
            warnings.append(
                _warning(
                    "Línea {line}: bancal vacío — omitida (el riego siempre requiere parcela)",
                    line=i,
                )
            )
            continue

        plot = plots_obj.get(bancal.lower())
        if plot is None:
            warnings.append(
                _warning(
                    "Línea {line}: bancal '{plot}' no encontrado — omitida",
                    line=i,
                    plot=bancal,
                )
            )
            continue

        if not plot.has_irrigation:
            warnings.append(
                _warning(
                    "Línea {line}: bancal '{plot}' no tiene riego habilitado — omitida",
                    line=i,
                    plot=bancal,
                )
            )
            continue

        try:
            row = IrrigationRecord(
                user_id=user_id,
                plot_id=plot.id,
                date=_parse_date(fecha_s),
                water_m3=_parse_num(agua_m3_s),
                notes=notas or None,
                expense_id=None,
            )
            rows.append(row)
        except (ValueError, KeyError):
            warnings.append(
                _warning("Línea {line}: error al parsear los datos — omitida", line=i)
            )

    db.add_all(rows)
    return rows, warnings


async def import_truffles_csv(
    db: AsyncSession, content: bytes, user_id: int
) -> tuple[list[TruffleEvent], list[str]]:
    """Parse truffle production CSV and persist rows.

    Expected format (semicolon-delimited, no header):
        fecha_hora;bancal;planta;peso_g[;origen]
    """
    plots_result = await db.execute(select(Plot).where(Plot.user_id == user_id))
    plots: dict[str, Plot] = {p.name.lower(): p for p in plots_result.scalars().all()}

    plants_result = await db.execute(select(Plant).where(Plant.user_id == user_id))
    plants_by_plot_label: dict[tuple[int, str], Plant] = {
        (p.plot_id, p.label.lower()): p for p in plants_result.scalars().all()
    }

    rows: list[TruffleEvent] = []
    warnings: list[str] = []

    reader = csv.reader(io.StringIO(content.decode("utf-8")), delimiter=";")
    for i, line in enumerate(reader, 1):
        if not any(line):
            continue
        if len(line) < 4:
            warnings.append(
                _warning(
                    "Línea {line}: se esperaban al menos 4 columnas, se encontraron {count} — omitida",
                    line=i,
                    count=len(line),
                )
            )
            continue

        fecha_hora_s = line[0].strip()
        bancal = line[1].strip()
        planta_label = line[2].strip()
        peso_s = line[3].strip()
        origen = (line[4].strip() if len(line) > 4 else "manual") or "manual"

        if not bancal:
            warnings.append(_warning("Línea {line}: bancal vacío — omitida", line=i))
            continue
        if not planta_label:
            warnings.append(_warning("Línea {line}: planta vacía — omitida", line=i))
            continue

        plot = plots.get(bancal.lower())
        if plot is None:
            warnings.append(
                _warning(
                    "Línea {line}: bancal '{plot}' no encontrado — omitida",
                    line=i,
                    plot=bancal,
                )
            )
            continue

        plant = plants_by_plot_label.get((plot.id, planta_label.lower()))
        if plant is None:
            warnings.append(
                _warning(
                    "Línea {line}: planta '{plant}' no encontrada en bancal '{plot}' — omitida",
                    line=i,
                    plant=planta_label,
                    plot=bancal,
                )
            )
            continue

        try:
            created_at = _parse_datetime(fecha_hora_s)
            estimated_weight_grams = _parse_num(peso_s)
            row = TruffleEvent(
                plant_id=plant.id,
                plot_id=plot.id,
                user_id=user_id,
                source=origen,
                estimated_weight_grams=max(float(estimated_weight_grams), 0.0),
                created_at=created_at,
                undo_window_expires_at=created_at + datetime.timedelta(seconds=30),
                undone_at=None,
            )
            rows.append(row)
        except (ValueError, KeyError):
            warnings.append(
                _warning("Línea {line}: error al parsear los datos — omitida", line=i)
            )

    db.add_all(rows)
    return rows, warnings
