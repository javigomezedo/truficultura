from __future__ import annotations

import csv
import datetime
import io
import zipfile
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import _
from app.models.expense import Expense
from app.models.expense_proration_group import ExpenseProrationGroup
from app.models.brule import BruleRecord
from app.models.income import Income
from app.models.irrigation import IrrigationRecord
from app.models.plant import Plant, PlantStatus, HostSpecies
from app.models.plant_presence import PlantPresence
from app.models.plot import Plot
from app.models.plot_event import PlotEvent
from app.models.plot_harvest import PlotHarvest
from app.models.rainfall import RainfallRecord
from app.models.recurring_expense import FREQUENCIES, RecurringExpense
from app.models.truffle_event import TruffleEvent
from app.models.truffle_quality import TruffleQuality
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


async def _load_plots(db: AsyncSession, tenant_id: int) -> dict[str, int]:
    result = await db.execute(select(Plot).where(Plot.tenant_id == tenant_id))
    return {p.name.lower(): p.id for p in result.scalars().all()}


def _warning(message: str, **kwargs: object) -> str:
    return _(message, **kwargs)


async def import_expenses_csv(
    db: AsyncSession, content: bytes, tenant_id: int
) -> tuple[list[Expense], list[str]]:
    """Parse expenses CSV and persist rows.

    Expected format (semicolon-delimited, no header):
        fecha;concepto;persona;bancal;cantidad[;categoria[;grupo_prorrateo]]

    - fecha:           DD/MM/YYYY
    - concepto:        description text
    - persona:         person name
    - bancal:          plot name (optional — leave empty for general expenses)
    - cantidad:        amount in European format (e.g. 1.250,00)
    - categoria:       expense category (optional, e.g. Riego)
    - grupo_prorrateo: proration group key exported as "P-{id}" (optional).
                       Rows sharing the same key are linked to a reconstructed
                       ExpenseProrationGroup.
    """
    plots = await _load_plots(db, tenant_id)
    rows: list[Expense] = []
    warnings: list[str] = []

    # Parse all lines first so we can reconstruct proration groups in one pass.
    ParsedLine = dict  # typing alias
    parsed: list[ParsedLine] = []

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
        grupo_key: Optional[str] = line[6].strip() or None if len(line) > 6 else None
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
            parsed.append(
                {
                    "date": _parse_date(fecha_s),
                    "description": concepto.strip(),
                    "person": persona.strip(),
                    "plot_id": plot_id,
                    "amount": _parse_num(cantidad_s),
                    "category": categoria or None,
                    "grupo_key": grupo_key,
                }
            )
        except (ValueError, KeyError):
            warnings.append(
                _warning("Línea {line}: error al parsear los datos — omitida", line=i)
            )

    # Build proration groups for rows that share a grupo_key.
    proration_groups: dict[str, ExpenseProrationGroup] = {}
    for pl in parsed:
        gk = pl["grupo_key"]
        if gk and gk not in proration_groups:
            group_rows = [r for r in parsed if r["grupo_key"] == gk]
            group = ExpenseProrationGroup(
                tenant_id=tenant_id,
                description=group_rows[0]["description"],
                total_amount=sum(r["amount"] for r in group_rows),
                years=len(group_rows),
                start_year=min(r["date"].year for r in group_rows),
            )
            db.add(group)
            proration_groups[gk] = group

    # Flush to obtain group IDs before creating child expenses.
    if proration_groups:
        await db.flush()

    # Create expense records, linking prorated ones to their group.
    for pl in parsed:
        gk = pl["grupo_key"]
        group = proration_groups.get(gk) if gk else None
        row = Expense(
            tenant_id=tenant_id,
            date=pl["date"],
            description=pl["description"],
            person=pl["person"],
            plot_id=pl["plot_id"],
            amount=pl["amount"],
            category=pl["category"],
            proration_group_id=group.id if group else None,
        )
        rows.append(row)

    db.add_all(rows)
    return rows, warnings


async def import_incomes_csv(
    db: AsyncSession, content: bytes, tenant_id: int
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
    plots = await _load_plots(db, tenant_id)
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
                tenant_id=tenant_id,
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
    db: AsyncSession, content: bytes, tenant_id: int, plant_limit: Optional[int] = None
) -> tuple[list[Plot], list[str]]:
    """Parse plots CSV and persist rows.

    Expected format (semicolon-delimited, no header, min 2 columns):
        nombre;fecha_plantacion[;poligono;parcela;ref_catastral;hidrante;sector;n_plantas;superficie_ha;inicio_produccion[;tiene_riego[;config_mapa[;recinto[;caudal_riego[;provincia_cod[;municipio_cod[;especie_huesped_defecto]]]]]]]]

    - nombre:                 plot name (required)
    - fecha_plantacion:       planting date DD/MM/YYYY (required)
    - poligono:               polygon reference (optional)
    - parcela:                plot number within polygon (optional)
    - ref_catastral:          official cadastral reference (optional)
    - hidrante:               hydrant identifier (optional)
    - sector:                 sector (optional)
    - n_plantas:              number of plants (optional, integer)
    - superficie_ha:          area in hectares (optional, decimal)
    - inicio_produccion:      production start date DD/MM/YYYY (optional)
    - tiene_riego:            1 or 0 (optional, default 0 — backward compatible)
    - config_mapa:            sparse map config (optional, e.g. A:1-4; B:2-5)
    - recinto:                SIGPAC recinto number (optional, default '1')
    - caudal_riego:           irrigation flow in m³/h (optional, decimal)
    - provincia_cod:          cadastral province code (optional)
    - municipio_cod:          cadastral municipality code (optional)
    - especie_huesped_defecto: default host species (optional): encina|roble|quejigo|coscoja|avellano|carpe|otros

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
            default_species_s = col(16)
            default_host_species: Optional[HostSpecies] = None
            if default_species_s:
                try:
                    default_host_species = HostSpecies(default_species_s.lower())
                except ValueError:
                    warnings.append(
                        _warning(
                            "Línea {line}: especie '{val}' no reconocida — parcela importada sin especie por defecto",
                            line=i,
                            val=default_species_s,
                        )
                    )
            row = Plot(
                tenant_id=tenant_id,
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
                recinto=col(12) or "1",
                caudal_riego=_parse_num(col(13)) or None,
                provincia_cod=col(14) or None,
                municipio_cod=col(15) or None,
                default_host_species=default_host_species,
            )
            rows.append(row)
            map_config = col(11)
            if map_config:
                pending_map_configs.append((row, map_config))
        except (ValueError, KeyError):
            warnings.append(
                _warning("Línea {line}: error al parsear los datos — omitida", line=i)
            )

    if plant_limit is not None:
        from app.services.plots_service import _get_effective_plant_total
        from app.plan_access import PlantLimitExceededException

        current_total = await _get_effective_plant_total(db, tenant_id)
        new_plants = sum(r.num_plants or 0 for r in rows)
        if current_total + new_plants > plant_limit:
            raise PlantLimitExceededException(plant_limit)

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
                    tenant_id=tenant_id,
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

    await _recalculate_percentages(db, tenant_id)
    return rows, warnings


async def import_wells_csv(
    db: AsyncSession, content: bytes, tenant_id: int
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
    result = await db.execute(select(Plot).where(Plot.tenant_id == tenant_id))
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
                tenant_id=tenant_id,
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

    _BATCH_SIZE = 50
    for i in range(0, len(rows), _BATCH_SIZE):
        db.add_all(rows[i : i + _BATCH_SIZE])
        await db.flush()
    return rows, warnings


async def import_irrigation_csv(
    db: AsyncSession, content: bytes, tenant_id: int
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
    result = await db.execute(select(Plot).where(Plot.tenant_id == tenant_id))
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
                tenant_id=tenant_id,
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

    _BATCH_SIZE = 50
    for i in range(0, len(rows), _BATCH_SIZE):
        db.add_all(rows[i : i + _BATCH_SIZE])
        await db.flush()

    return rows, warnings


async def import_truffles_csv(
    db: AsyncSession, content: bytes, tenant_id: int
) -> tuple[list[TruffleEvent], list[str]]:
    """Parse truffle production CSV and persist rows.

    Expected format (semicolon-delimited, no header):
        fecha_hora;bancal;planta;peso_g[;origen[;calidad]]

    - fecha_hora: DD/MM/YYYY HH:MM:SS
    - bancal:     plot name
    - planta:     plant label
    - peso_g:     weight in grams, European format
    - origen:     'manual' | 'qr' (optional, default 'manual')
    - calidad:    quality category (optional): extra|primera|segunda|blanda|agusanada
    """
    plots_result = await db.execute(select(Plot).where(Plot.tenant_id == tenant_id))
    plots: dict[str, Plot] = {p.name.lower(): p for p in plots_result.scalars().all()}

    plants_result = await db.execute(select(Plant).where(Plant.tenant_id == tenant_id))
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
        quality_s = line[5].strip().lower() if len(line) > 5 else ""

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
            quality: Optional[TruffleQuality] = None
            if quality_s:
                try:
                    quality = TruffleQuality(quality_s)
                except ValueError:
                    warnings.append(
                        _warning(
                            "Línea {line}: calidad '{val}' no reconocida — importada sin calidad",
                            line=i,
                            val=quality_s,
                        )
                    )
            row = TruffleEvent(
                plant_id=plant.id,
                plot_id=plot.id,
                tenant_id=tenant_id,
                source=origen,
                estimated_weight_grams=max(float(estimated_weight_grams), 0.0),
                created_at=created_at,
                undo_window_expires_at=created_at + datetime.timedelta(seconds=30),
                undone_at=None,
                quality=quality,
            )
            rows.append(row)
        except (ValueError, KeyError):
            warnings.append(
                _warning("Línea {line}: error al parsear los datos — omitida", line=i)
            )

    _BATCH_SIZE = 50
    for i in range(0, len(rows), _BATCH_SIZE):
        db.add_all(rows[i : i + _BATCH_SIZE])
        await db.flush()

    return rows, warnings


async def import_plot_events_csv(
    db: AsyncSession, content: bytes, tenant_id: int
) -> tuple[list[PlotEvent], list[str]]:
    """Parse plot events (labores) CSV and persist rows.

    Expected format (semicolon-delimited, no header):
        fecha;bancal;tipo_evento;notas[;es_recurrente]

    - fecha:         DD/MM/YYYY (required)
    - bancal:        plot name (required)
    - tipo_evento:   one of labrado, picado, poda, vallado, installed_drip, riego, pozo,
                     herbicida, tratamiento_fitosanitario, siega, abonado, dano_jabali (required)
    - notas:         optional free text notes
    - es_recurrente: 1 or 0 (optional; inferred from event type if omitted)

    Rows are skipped with a warning if:
    - the plot is not found for the current user
    - tipo_evento is not a recognised EventType value
    - a one-time event (vallado, installed_drip) already exists for that plot
    """
    from app.schemas.plot_event import EventType
    from app.services.plot_events_service import (
        ONE_TIME_EVENT_TYPES,
        _is_recurring_by_type,
    )

    plots_result = await db.execute(select(Plot).where(Plot.tenant_id == tenant_id))
    plots: dict[str, Plot] = {p.name.lower(): p for p in plots_result.scalars().all()}

    # Pre-load existing one-time events to avoid duplicates
    one_time_values = {et.value for et in ONE_TIME_EVENT_TYPES}
    existing_one_time_result = await db.execute(
        select(PlotEvent.plot_id, PlotEvent.event_type).where(
            PlotEvent.tenant_id == tenant_id,
            PlotEvent.event_type.in_(one_time_values),
        )
    )
    existing_one_time: set[tuple[int, str]] = {
        (plot_id, event_type) for plot_id, event_type in existing_one_time_result.all()
    }

    rows: list[PlotEvent] = []
    warnings: list[str] = []
    now = datetime.datetime.now(datetime.timezone.utc)

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

        fecha_s = line[0].strip()
        bancal = line[1].strip()
        tipo_s = line[2].strip().lower()
        notas = line[3].strip() if len(line) > 3 else None
        recurrente_s = line[4].strip() if len(line) > 4 else ""

        if not bancal:
            warnings.append(_warning("Línea {line}: bancal vacío — omitida", line=i))
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

        try:
            event_type = EventType(tipo_s)
        except ValueError:
            warnings.append(
                _warning(
                    "Línea {line}: tipo de evento '{tipo}' no reconocido — omitida",
                    line=i,
                    tipo=tipo_s,
                )
            )
            continue

        if event_type in ONE_TIME_EVENT_TYPES:
            key = (plot.id, event_type.value)
            if key in existing_one_time:
                warnings.append(
                    _warning(
                        "Línea {line}: el evento '{tipo}' ya existe para '{plot}' (solo se permite uno) — omitida",
                        line=i,
                        tipo=event_type.value,
                        plot=bancal,
                    )
                )
                continue
            existing_one_time.add(key)

        is_recurring = (
            bool(int(recurrente_s))
            if recurrente_s in ("0", "1")
            else _is_recurring_by_type(event_type)
        )

        try:
            row = PlotEvent(
                tenant_id=tenant_id,
                plot_id=plot.id,
                event_type=event_type.value,
                date=_parse_date(fecha_s),
                notes=notas or None,
                is_recurring=is_recurring,
                created_at=now,
                updated_at=now,
            )
            rows.append(row)
        except (ValueError, KeyError):
            warnings.append(
                _warning("Línea {line}: error al parsear los datos — omitida", line=i)
            )

    # Flush in batches to avoid a single massive INSERT statement that can
    # close the DB connection, and to prevent autoflush issues when the next
    # importer runs a SELECT.
    _BATCH_SIZE = 50
    for i in range(0, len(rows), _BATCH_SIZE):
        db.add_all(rows[i : i + _BATCH_SIZE])
        await db.flush()

    return rows, warnings


async def import_recurring_expenses_csv(
    db: AsyncSession, content: bytes, tenant_id: int
) -> tuple[list[RecurringExpense], list[str]]:
    """Parse recurring expenses CSV and persist rows.

    Expected format (semicolon-delimited, no header):
        concepto;frecuencia;bancal;persona;categoria;cantidad;activo

    - concepto:   description text
    - frecuencia: weekly / monthly / annual
    - bancal:     plot name (optional)
    - persona:    person name (optional)
    - categoria:  expense category (optional)
    - cantidad:   amount in European format (e.g. 125,00)
    - activo:     1 or 0 (optional, defaults to 1)
    """
    plots = await _load_plots(db, tenant_id)
    rows: list[RecurringExpense] = []
    warnings: list[str] = []

    reader = csv.reader(io.StringIO(content.decode("utf-8")), delimiter=";")
    for i, line in enumerate(reader, 1):
        if not any(line):
            continue
        if len(line) < 6:
            warnings.append(
                _warning(
                    "L\u00ednea {line}: se esperaban al menos 6 columnas, se recibieron {cols} \u2014 omitida",
                    line=i,
                    cols=len(line),
                )
            )
            continue

        concepto_s = line[0].strip()
        frecuencia_s = line[1].strip().lower()
        bancal_s = line[2].strip() if len(line) > 2 else ""
        persona_s = line[3].strip() if len(line) > 3 else ""
        categoria_s = line[4].strip() if len(line) > 4 else ""
        cantidad_s = line[5].strip() if len(line) > 5 else "0"
        activo_s = line[6].strip() if len(line) > 6 else "1"

        if not concepto_s:
            warnings.append(
                _warning(
                    "L\u00ednea {line}: el concepto est\u00e1 vac\u00edo \u2014 omitida",
                    line=i,
                )
            )
            continue

        if frecuencia_s not in FREQUENCIES:
            warnings.append(
                _warning(
                    "L\u00ednea {line}: frecuencia '{val}' desconocida, se usar\u00e1 'monthly'",
                    line=i,
                    val=frecuencia_s,
                )
            )
            frecuencia_s = "monthly"

        plot_id: Optional[int] = None
        if bancal_s:
            plot_id = plots.get(bancal_s.lower())
            if plot_id is None:
                warnings.append(
                    _warning(
                        "L\u00ednea {line}: bancal '{bancal}' no encontrado \u2014 se registra sin bancal",
                        line=i,
                        bancal=bancal_s,
                    )
                )

        try:
            amount = _parse_num(cantidad_s)
        except (ValueError, AttributeError):
            warnings.append(
                _warning(
                    "L\u00ednea {line}: cantidad '{val}' no es un n\u00famero v\u00e1lido \u2014 omitida",
                    line=i,
                    val=cantidad_s,
                )
            )
            continue

        is_active = activo_s != "0"

        obj = RecurringExpense(
            tenant_id=tenant_id,
            description=concepto_s,
            frequency=frecuencia_s,
            plot_id=plot_id,
            person=persona_s,
            category=categoria_s or None,
            amount=amount,
            is_active=is_active,
            last_run_date=None,
        )
        rows.append(obj)

    db.add_all(rows)
    return rows, warnings


async def import_harvests_csv(
    db: AsyncSession, content: bytes, tenant_id: int
) -> tuple[list[PlotHarvest], list[str]]:
    """Parse harvests CSV and persist rows (insert-always).

    Expected format (semicolon-delimited, no header):
        fecha;bancal;gramos;notas

    - fecha:   DD/MM/YYYY
    - bancal:  plot name
    - gramos:  weight in European format (e.g. 1.250,50)
    - notas:   optional free text
    """
    plots = await _load_plots(db, tenant_id)
    rows: list[PlotHarvest] = []
    warnings: list[str] = []

    reader = csv.reader(io.StringIO(content.decode("utf-8")), delimiter=";")
    for i, line in enumerate(reader, 1):
        if not any(line):
            continue
        if len(line) < 3:
            warnings.append(
                _warning(
                    "Línea {line}: se esperaban 3 columnas, se encontraron {count} — omitida",
                    line=i,
                    count=len(line),
                )
            )
            continue

        fecha_s, bancal, gramos_s = line[0], line[1], line[2]
        notas = line[3].strip() if len(line) > 3 else None
        bancal = bancal.strip()
        plot_id: Optional[int] = plots.get(bancal.lower()) if bancal else None

        if not bancal or plot_id is None:
            warnings.append(
                _warning(
                    "Línea {line}: bancal '{plot}' no encontrado — omitida",
                    line=i,
                    plot=bancal,
                )
            )
            continue

        try:
            grams = _parse_num(gramos_s)
            row = PlotHarvest(
                tenant_id=tenant_id,
                plot_id=plot_id,
                harvest_date=_parse_date(fecha_s),
                weight_grams=max(0.0, grams),
                notes=notas or None,
            )
            rows.append(row)
        except (ValueError, KeyError):
            warnings.append(
                _warning("Línea {line}: error al parsear los datos — omitida", line=i)
            )

    db.add_all(rows)
    return rows, warnings


async def import_presences_csv(
    db: AsyncSession, content: bytes, tenant_id: int
) -> tuple[list[PlantPresence], list[str]]:
    """Parse plant presence CSV and persist rows.

    Expected format (semicolon-delimited, no header):
        fecha;bancal;planta
    """
    plots_result = await db.execute(select(Plot).where(Plot.tenant_id == tenant_id))
    plots: dict[str, Plot] = {p.name.lower(): p for p in plots_result.scalars().all()}

    plants_result = await db.execute(select(Plant).where(Plant.tenant_id == tenant_id))
    plants_by_plot_label: dict[tuple[int, str], Plant] = {
        (p.plot_id, p.label.lower()): p for p in plants_result.scalars().all()
    }

    existing_result = await db.execute(
        select(PlantPresence.plant_id, PlantPresence.presence_date).where(
            PlantPresence.tenant_id == tenant_id
        )
    )
    existing: set[tuple[int, datetime.date]] = {
        (row.plant_id, row.presence_date) for row in existing_result.all()
    }

    rows: list[PlantPresence] = []
    warnings: list[str] = []

    reader = csv.reader(io.StringIO(content.decode("utf-8")), delimiter=";")
    for i, line in enumerate(reader, 1):
        if not any(line):
            continue
        if len(line) < 3:
            warnings.append(
                _warning(
                    "Línea {line}: se esperaban 3 columnas, se encontraron {count} — omitida",
                    line=i,
                    count=len(line),
                )
            )
            continue

        fecha_s = line[0].strip()
        bancal = line[1].strip()
        planta_label = line[2].strip()

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
            presence_date = _parse_date(fecha_s)
            key = (plant.id, presence_date)
            if key in existing:
                warnings.append(
                    _warning(
                        "Línea {line}: presencia ya registrada para planta '{plant}' el {date} — omitida",
                        line=i,
                        plant=planta_label,
                        date=fecha_s,
                    )
                )
                continue
            existing.add(key)
            row = PlantPresence(
                tenant_id=tenant_id,
                plot_id=plot.id,
                plant_id=plant.id,
                presence_date=presence_date,
                has_truffle=True,
            )
            rows.append(row)
        except (ValueError, KeyError):
            warnings.append(
                _warning("Línea {line}: error al parsear los datos — omitida", line=i)
            )

    db.add_all(rows)
    return rows, warnings


async def import_plants_csv(
    db: AsyncSession, content: bytes, tenant_id: int
) -> tuple[list[Plant], list[str]]:
    """Update Plant attributes from CSV. Does not create new plants.

    Expected format (semicolon-delimited, no header):
        bancal;etiqueta;estado;fecha_baja;especie_huesped

    - bancal:          plot name (required)
    - etiqueta:        plant label, e.g. "A1" (required)
    - estado:          plant status: viva|estresada|muerta|reemplazada (required)
    - fecha_baja:      date plant was retired DD/MM/YYYY (optional, empty for active)
    - especie_huesped: host species (optional): encina|roble|quejigo|coscoja|avellano|carpe|otros

    Rows are matched by (bancal, etiqueta). Unknown plots or plants are skipped.
    """
    plots_result = await db.execute(select(Plot).where(Plot.tenant_id == tenant_id))
    plots: dict[str, Plot] = {p.name.lower(): p for p in plots_result.scalars().all()}

    plants_result = await db.execute(select(Plant).where(Plant.tenant_id == tenant_id))
    plants_by_plot_label: dict[tuple[int, str], Plant] = {
        (p.plot_id, p.label.lower()): p for p in plants_result.scalars().all()
    }

    updated: list[Plant] = []
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

        bancal_s = line[0].strip()
        etiqueta_s = line[1].strip()
        estado_s = line[2].strip().lower()
        fecha_baja_s = line[3].strip() if len(line) > 3 else ""
        especie_s = line[4].strip().lower() if len(line) > 4 else ""

        if not bancal_s or not etiqueta_s:
            warnings.append(
                _warning("Línea {line}: bancal o etiqueta vacíos — omitida", line=i)
            )
            continue

        plot = plots.get(bancal_s.lower())
        if plot is None:
            warnings.append(
                _warning(
                    "Línea {line}: bancal '{plot}' no encontrado — omitida",
                    line=i,
                    plot=bancal_s,
                )
            )
            continue

        plant = plants_by_plot_label.get((plot.id, etiqueta_s.lower()))
        if plant is None:
            warnings.append(
                _warning(
                    "Línea {line}: planta '{plant}' no encontrada en bancal '{plot}' — omitida",
                    line=i,
                    plant=etiqueta_s,
                    plot=bancal_s,
                )
            )
            continue

        try:
            plant.status = PlantStatus(estado_s)
        except ValueError:
            warnings.append(
                _warning(
                    "Línea {line}: estado '{val}' no reconocido — omitida",
                    line=i,
                    val=estado_s,
                )
            )
            continue

        plant.baja_date = _parse_date_opt(fecha_baja_s)

        if especie_s:
            try:
                plant.host_species = HostSpecies(especie_s)
            except ValueError:
                warnings.append(
                    _warning(
                        "Línea {line}: especie '{val}' no reconocida — planta actualizada sin especie",
                        line=i,
                        val=especie_s,
                    )
                )

        updated.append(plant)

    return updated, warnings


async def import_brule_csv(
    db: AsyncSession, content: bytes, tenant_id: int
) -> tuple[list[BruleRecord], list[str]]:
    """Parse brulé measurement CSV and persist rows.

    Expected format (semicolon-delimited, no header):
        fecha;bancal;planta;diametro_cm

    - fecha:       DD/MM/YYYY (required)
    - bancal:      plot name (required)
    - planta:      plant label, e.g. "A1" (required)
    - diametro_cm: integer diameter in cm (required)

    Duplicate records (same plant + date) are skipped with a warning.
    """
    plots_result = await db.execute(select(Plot).where(Plot.tenant_id == tenant_id))
    plots: dict[str, Plot] = {p.name.lower(): p for p in plots_result.scalars().all()}

    plants_result = await db.execute(select(Plant).where(Plant.tenant_id == tenant_id))
    plants_by_plot_label: dict[tuple[int, str], Plant] = {
        (p.plot_id, p.label.lower()): p for p in plants_result.scalars().all()
    }

    # Pre-load existing records to detect UniqueConstraint conflicts
    existing_result = await db.execute(
        select(BruleRecord.plant_id, BruleRecord.record_date).where(
            BruleRecord.tenant_id == tenant_id
        )
    )
    existing: set[tuple[int, datetime.date]] = {
        (row.plant_id, row.record_date) for row in existing_result.all()
    }

    rows: list[BruleRecord] = []
    warnings: list[str] = []

    reader = csv.reader(io.StringIO(content.decode("utf-8")), delimiter=";")
    for i, line in enumerate(reader, 1):
        if not any(line):
            continue
        if len(line) < 4:
            warnings.append(
                _warning(
                    "Línea {line}: se esperaban 4 columnas, se encontraron {count} — omitida",
                    line=i,
                    count=len(line),
                )
            )
            continue

        fecha_s = line[0].strip()
        bancal_s = line[1].strip()
        planta_s = line[2].strip()
        diametro_s = line[3].strip()

        if not bancal_s or not planta_s:
            warnings.append(
                _warning("Línea {line}: bancal o planta vacíos — omitida", line=i)
            )
            continue

        plot = plots.get(bancal_s.lower())
        if plot is None:
            warnings.append(
                _warning(
                    "Línea {line}: bancal '{plot}' no encontrado — omitida",
                    line=i,
                    plot=bancal_s,
                )
            )
            continue

        plant = plants_by_plot_label.get((plot.id, planta_s.lower()))
        if plant is None:
            warnings.append(
                _warning(
                    "Línea {line}: planta '{plant}' no encontrada en bancal '{plot}' — omitida",
                    line=i,
                    plant=planta_s,
                    plot=bancal_s,
                )
            )
            continue

        try:
            record_date = _parse_date(fecha_s)
            diameter_cm = int(_parse_int(diametro_s))
        except (ValueError, KeyError):
            warnings.append(
                _warning("Línea {line}: error al parsear los datos — omitida", line=i)
            )
            continue

        key = (plant.id, record_date)
        if key in existing:
            warnings.append(
                _warning(
                    "Línea {line}: ya existe un registro de brulé para planta '{plant}' el {date} — omitida",
                    line=i,
                    plant=planta_s,
                    date=fecha_s,
                )
            )
            continue
        existing.add(key)

        rows.append(
            BruleRecord(
                tenant_id=tenant_id,
                plot_id=plot.id,
                plant_id=plant.id,
                record_date=record_date,
                diameter_cm=diameter_cm,
            )
        )

    _BATCH_SIZE = 50
    for i in range(0, len(rows), _BATCH_SIZE):
        db.add_all(rows[i : i + _BATCH_SIZE])
        await db.flush()

    return rows, warnings


async def import_rainfall_csv(
    db: AsyncSession, content: bytes, tenant_id: int
) -> tuple[list[RainfallRecord], list[str]]:
    """Parse manual rainfall records CSV and persist rows.

    Expected format (semicolon-delimited, no header):
        fecha;bancal;mm;notas

    - fecha:  DD/MM/YYYY (required)
    - bancal: plot name (optional — leave empty for general rainfall)
    - mm:     precipitation in millimetres, European format (required)
    - notas:  optional free text notes
    """
    plots = await _load_plots(db, tenant_id)
    rows: list[RainfallRecord] = []
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

        fecha_s = line[0].strip()
        bancal_s = line[1].strip()
        mm_s = line[2].strip()
        notas = line[3].strip() if len(line) > 3 else None

        plot_id: Optional[int] = None
        if bancal_s:
            plot_id = plots.get(bancal_s.lower())
            if plot_id is None:
                warnings.append(
                    _warning(
                        "Línea {line}: bancal '{plot}' no encontrado — importado sin bancal",
                        line=i,
                        plot=bancal_s,
                    )
                )

        try:
            row = RainfallRecord(
                tenant_id=tenant_id,
                plot_id=plot_id,
                date=_parse_date(fecha_s),
                precipitation_mm=_parse_num(mm_s),
                source="manual",
                notes=notas or None,
            )
            rows.append(row)
        except (ValueError, KeyError):
            warnings.append(
                _warning("Línea {line}: error al parsear los datos — omitida", line=i)
            )

    db.add_all(rows)
    return rows, warnings


async def import_all_csv_zip(
    db: AsyncSession, content: bytes, tenant_id: int
) -> tuple[dict[str, int], list[str]]:
    """Import all supported CSV files found in a ZIP payload.

    Supported filenames:
    - parcelas.csv
    - plantas.csv  (must come after parcelas.csv)
    - gastos.csv
    - ingresos.csv
    - riego.csv
    - pozos.csv
    - produccion.csv
    - labores.csv
    - gastos_recurrentes.csv
    - cosechas.csv
    - presencias.csv
    - brule.csv
    - lluvia.csv
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        return {}, [_warning("El archivo ZIP no es válido")]

    importers: list[tuple[str, object]] = [
        ("parcelas.csv", import_plots_csv),
        ("plantas.csv", import_plants_csv),
        ("gastos.csv", import_expenses_csv),
        ("ingresos.csv", import_incomes_csv),
        ("riego.csv", import_irrigation_csv),
        ("pozos.csv", import_wells_csv),
        ("produccion.csv", import_truffles_csv),
        ("labores.csv", import_plot_events_csv),
        ("gastos_recurrentes.csv", import_recurring_expenses_csv),
        ("cosechas.csv", import_harvests_csv),
        ("presencias.csv", import_presences_csv),
        ("brule.csv", import_brule_csv),
        ("lluvia.csv", import_rainfall_csv),
    ]

    imported_by_file: dict[str, int] = {}
    warnings: list[str] = []

    with zf:
        names_by_basename: dict[str, str] = {
            member.filename.rsplit("/", 1)[-1].lower(): member.filename
            for member in zf.infolist()
            if not member.is_dir()
        }

        for filename, importer in importers:
            member_name = names_by_basename.get(filename)
            if not member_name:
                continue

            try:
                file_content = zf.read(member_name)
                rows, file_warnings = await importer(db, file_content, tenant_id)
                imported_by_file[filename] = len(rows)
                warnings.extend([f"{filename}: {w}" for w in file_warnings])
                # Flush after each file so Postgres sees incremental work and
                # the connection doesn't time out idle-in-transaction.
                await db.flush()
            except (UnicodeDecodeError, ValueError) as exc:
                warnings.append(
                    _warning(
                        "{file}: error al procesar el archivo ({error})",
                        file=filename,
                        error=str(exc),
                    )
                )

    if not imported_by_file:
        warnings.append(
            _warning("El ZIP no contiene archivos CSV compatibles para importar")
        )

    return imported_by_file, warnings
