"""Servicio de avisos (notifications).

Responsable de:
  - CRUD de avisos: crear, listar, marcar como leído, descartar.
  - Gestión de preferencias por usuario.
  - Generación de nuevos avisos (entrada del cron diario).

Cada checker sigue el patrón:
  1. Resolver las preferencias del usuario (con fallback a defaults).
  2. Consultar la BD con los filtros necesarios.
  3. Llamar a _create_if_not_exists() si se cumple la condición.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brule import BruleRecord
from app.models.irrigation import IrrigationRecord
from app.models.notification import (
    NOTIFICATION_TYPES,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    Notification,
    NotificationPreference,
)
from app.models.plant import Plant
from app.models.plot import Plot
from app.models.plot_harvest import PlotHarvest
from app.models.rainfall import RainfallRecord
from app.models.tenant import Tenant, TenantMembership
from app.models.truffle_event import TruffleEvent
from app.models.user import User
from app.utils import campaign_label, campaign_year

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default preferences: used when no row exists in notification_preferences
# ---------------------------------------------------------------------------

_DEFAULTS: dict[str, dict[str, Any]] = {
    "campaign_start": {
        "enabled": True,
        "email_enabled": False,
        "threshold_days": None,
        "threshold_value": None,
    },
    "no_truffle_events": {
        "enabled": True,
        "email_enabled": True,
        "threshold_days": 7,
        "threshold_value": None,
    },
    "low_water_balance": {
        "enabled": True,
        "email_enabled": True,
        "threshold_days": 5,
        "threshold_value": 2.0,  # m³ total lluvia+riego en el periodo
    },
    "user_inactive": {
        "enabled": True,
        "email_enabled": False,
        "threshold_days": 30,
        "threshold_value": None,
    },
    "no_rainfall_data": {
        "enabled": True,
        "email_enabled": False,
        "threshold_days": 14,
        "threshold_value": None,
    },
    "campaign_end_reminder": {
        "enabled": True,
        "email_enabled": False,
        "threshold_days": None,
        "threshold_value": None,
    },
    "stressed_plant_no_replacement": {
        "enabled": True,
        "email_enabled": False,
        "threshold_days": 30,
        "threshold_value": None,
    },
    "no_irrigation_summer": {
        "enabled": True,
        "email_enabled": False,
        "threshold_days": 14,
        "threshold_value": None,
    },
    "no_brule_measurement": {
        "enabled": True,
        "email_enabled": False,
        "threshold_days": 28,
        "threshold_value": None,
    },
    "low_harvest_vs_previous": {
        "enabled": True,
        "email_enabled": False,
        "threshold_days": None,
        "threshold_value": 50.0,  # % de la media histórica
    },
}


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def get_unread_count(user_id: int, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
            Notification.is_dismissed.is_(False),
        )
    )
    return result.scalar() or 0


async def list_notifications(
    user_id: int,
    db: AsyncSession,
    *,
    include_dismissed: bool = False,
    limit: int = 50,
) -> list[Notification]:
    q = select(Notification).where(Notification.user_id == user_id)
    if not include_dismissed:
        q = q.where(Notification.is_dismissed.is_(False))
    q = q.order_by(Notification.created_at.desc()).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_notification(
    notification_id: int, user_id: int, db: AsyncSession
) -> Optional[Notification]:
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def mark_read(notification_id: int, user_id: int, db: AsyncSession) -> bool:
    notif = await get_notification(notification_id, user_id, db)
    if notif is None:
        return False
    notif.is_read = True
    await db.flush()
    return True


async def mark_all_read(user_id: int, db: AsyncSession) -> int:
    result = await db.execute(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
        )
    )
    rows = result.scalars().all()
    for n in rows:
        n.is_read = True
    await db.flush()
    return len(rows)


async def dismiss(notification_id: int, user_id: int, db: AsyncSession) -> bool:
    notif = await get_notification(notification_id, user_id, db)
    if notif is None:
        return False
    notif.is_dismissed = True
    notif.is_read = True
    await db.flush()
    return True


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------


async def get_preferences(
    user_id: int, tenant_id: int, db: AsyncSession
) -> dict[str, dict[str, Any]]:
    """Return resolved preferences for all notification types.

    Missing rows fall back to _DEFAULTS so the caller always gets a complete dict.
    """
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.tenant_id == tenant_id,
        )
    )
    rows = {p.notification_type: p for p in result.scalars().all()}

    prefs: dict[str, dict[str, Any]] = {}
    for ntype in NOTIFICATION_TYPES:
        defaults = _DEFAULTS[ntype]
        if ntype in rows:
            row = rows[ntype]
            prefs[ntype] = {
                "enabled": row.enabled,
                "email_enabled": row.email_enabled,
                "threshold_days": row.threshold_days
                if row.threshold_days is not None
                else defaults["threshold_days"],
                "threshold_value": row.threshold_value
                if row.threshold_value is not None
                else defaults["threshold_value"],
            }
        else:
            prefs[ntype] = dict(defaults)
    return prefs


async def upsert_preference(
    user_id: int,
    tenant_id: int,
    notification_type: str,
    *,
    enabled: bool,
    email_enabled: bool,
    threshold_days: Optional[int] = None,
    threshold_value: Optional[float] = None,
    db: AsyncSession,
) -> NotificationPreference:
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.notification_type == notification_type,
        )
    )
    pref = result.scalar_one_or_none()
    if pref is None:
        pref = NotificationPreference(
            user_id=user_id,
            tenant_id=tenant_id,
            notification_type=notification_type,
        )
        db.add(pref)
    pref.enabled = enabled
    pref.email_enabled = email_enabled
    pref.threshold_days = threshold_days
    pref.threshold_value = threshold_value
    await db.flush()
    return pref


# ---------------------------------------------------------------------------
# Internal: create notification only if dedup_key doesn't already exist
# ---------------------------------------------------------------------------


async def _create_if_not_exists(
    user_id: int,
    tenant_id: int,
    notification_type: str,
    dedup_key: str,
    title: str,
    message: str,
    severity: str = SEVERITY_INFO,
    extra_data: Optional[dict] = None,
    *,
    email_enabled: bool = False,
    user_email: Optional[str] = None,
    db: AsyncSession,
) -> Optional[Notification]:
    """Insert the notification only if the dedup_key is new for this user.

    Returns the new Notification if created, None if it already existed.
    """
    existing = await db.execute(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.dedup_key == dedup_key,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return None

    notif = Notification(
        user_id=user_id,
        tenant_id=tenant_id,
        notification_type=notification_type,
        severity=severity,
        title=title,
        message=message,
        extra_data=extra_data,
        dedup_key=dedup_key,
    )
    db.add(notif)
    await db.flush()

    if email_enabled and user_email:
        await _send_notification_email(
            to=user_email,
            title=title,
            message=message,
            severity=severity,
        )
        notif.email_sent = True
        await db.flush()

    logger.info(
        "[notifications] Creado aviso type=%s dedup_key=%s user_id=%d",
        notification_type,
        dedup_key,
        user_id,
    )
    return notif


async def _send_notification_email(
    to: str, title: str, message: str, severity: str
) -> None:
    from app.services.email_service import send_email

    severity_label = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(severity, "ℹ️")
    html_body = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
      <h2 style="color: #5c3d1e;">{severity_label} {title}</h2>
      <p style="color: #333; font-size: 16px;">{message}</p>
      <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
      <p style="color: #888; font-size: 12px;">
        Este aviso ha sido generado automáticamente por Trufiq.<br>
        Puedes gestionar tus preferencias de avisos desde
        <a href="https://trufiq.app/notifications/preferences">tu panel de preferencias</a>.
      </p>
    </div>
    """
    try:
        await send_email(to=to, subject=f"Trufiq · {title}", html_body=html_body)
    except Exception:
        logger.exception("[notifications] Fallo enviando email de aviso a %s", to)


# ---------------------------------------------------------------------------
# Checkers
# ---------------------------------------------------------------------------


async def _check_campaign_start(
    today: datetime.date,
    tenant: Tenant,
    members: list[User],
    db: AsyncSession,
) -> int:
    """Fires once per campaign year on any day in May."""
    if today.month != 5:
        return 0

    cy = campaign_year(today)
    label = campaign_label(cy)
    created = 0
    for user in members:
        prefs = await get_preferences(user.id, tenant.id, db)
        pref = prefs["campaign_start"]
        if not pref["enabled"]:
            continue
        dedup_key = f"campaign_start:{cy}"
        notif = await _create_if_not_exists(
            user_id=user.id,
            tenant_id=tenant.id,
            notification_type="campaign_start",
            dedup_key=dedup_key,
            title=f"Campaña {label} en marcha",
            message=(
                f"Ha comenzado la campaña agrícola {label}. "
                "Es un buen momento para revisar tus parcelas y planificar la temporada."
            ),
            severity=SEVERITY_INFO,
            email_enabled=pref["email_enabled"],
            user_email=user.email,
            db=db,
        )
        if notif:
            created += 1
    return created


async def _check_campaign_end_reminder(
    today: datetime.date,
    tenant: Tenant,
    members: list[User],
    db: AsyncSession,
) -> int:
    """Fires once per April (end of campaign)."""
    if today.month != 4:
        return 0

    cy = campaign_year(today)
    label = campaign_label(cy)
    created = 0
    for user in members:
        prefs = await get_preferences(user.id, tenant.id, db)
        pref = prefs["campaign_end_reminder"]
        if not pref["enabled"]:
            continue
        dedup_key = f"campaign_end_reminder:{today.year}-04"
        notif = await _create_if_not_exists(
            user_id=user.id,
            tenant_id=tenant.id,
            notification_type="campaign_end_reminder",
            dedup_key=dedup_key,
            title=f"Campaña {label} llegando a su fin",
            message=(
                f"Abril es el último mes de la campaña {label}. "
                "Recuerda registrar los últimos datos de cosecha y cerrar tus gastos e ingresos."
            ),
            severity=SEVERITY_INFO,
            email_enabled=pref["email_enabled"],
            user_email=user.email,
            db=db,
        )
        if notif:
            created += 1
    return created


async def _check_no_truffle_events(
    today: datetime.date,
    tenant: Tenant,
    members: list[User],
    db: AsyncSession,
) -> int:
    """Temporada alta (dic-mar): sin eventos de trufa en los últimos N días."""
    if today.month not in (12, 1, 2, 3):
        return 0

    created = 0
    iso_year, iso_week, _ = today.isocalendar()

    for user in members:
        prefs = await get_preferences(user.id, tenant.id, db)
        pref = prefs["no_truffle_events"]
        if not pref["enabled"]:
            continue

        threshold_days = pref["threshold_days"] or 7
        since = today - datetime.timedelta(days=threshold_days)

        # Check if there's any truffle event for this tenant in the period
        result = await db.execute(
            select(func.count(TruffleEvent.id)).where(
                TruffleEvent.tenant_id == tenant.id,
                TruffleEvent.undone_at.is_(None),
                func.date(TruffleEvent.created_at) >= since,
                func.date(TruffleEvent.created_at) <= today,
            )
        )
        count = result.scalar() or 0
        if count > 0:
            continue

        dedup_key = f"no_truffle_events:{iso_year}-W{iso_week:02d}"
        notif = await _create_if_not_exists(
            user_id=user.id,
            tenant_id=tenant.id,
            notification_type="no_truffle_events",
            dedup_key=dedup_key,
            title=f"Sin eventos de trufa en {threshold_days} días",
            message=(
                f"Llevas {threshold_days} días sin registrar ningún evento de recolección. "
                "¿Todo bien en la finca? Recuerda registrar cada salida."
            ),
            severity=SEVERITY_WARNING,
            extra_data={"threshold_days": threshold_days},
            email_enabled=pref["email_enabled"],
            user_email=user.email,
            db=db,
        )
        if notif:
            created += 1
    return created


async def _check_low_water_balance(
    today: datetime.date,
    tenant: Tenant,
    members: list[User],
    db: AsyncSession,
) -> int:
    """Detecta parcelas con riego que han recibido poca agua (lluvia+riego) en los últimos N días."""
    created = 0

    # Gather prefs from first member to determine thresholds (all members share tenant config)
    # We check per-user later for enabled/email_enabled
    if not members:
        return 0

    # Get all irrigated plots for the tenant
    plots_result = await db.execute(
        select(Plot).where(
            Plot.tenant_id == tenant.id,
            Plot.has_irrigation.is_(True),
        )
    )
    plots = list(plots_result.scalars().all())
    if not plots:
        return 0

    for user in members:
        prefs = await get_preferences(user.id, tenant.id, db)
        pref = prefs["low_water_balance"]
        if not pref["enabled"]:
            continue

        threshold_days = pref["threshold_days"] or 5
        threshold_value = (
            pref["threshold_value"] if pref["threshold_value"] is not None else 2.0
        )
        since = today - datetime.timedelta(days=threshold_days)

        low_plots: list[str] = []
        for plot in plots:
            # Sum irrigation water in period
            irr_result = await db.execute(
                select(func.coalesce(func.sum(IrrigationRecord.water_m3), 0.0)).where(
                    IrrigationRecord.tenant_id == tenant.id,
                    IrrigationRecord.plot_id == plot.id,
                    IrrigationRecord.date >= since,
                    IrrigationRecord.date <= today,
                )
            )
            irrigation_m3 = float(irr_result.scalar() or 0.0)

            # Sum rainfall in period for the plot's municipio
            rain_m3 = 0.0
            if plot.municipio_cod and plot.area_ha:
                rain_result = await db.execute(
                    select(
                        func.coalesce(func.sum(RainfallRecord.precipitation_mm), 0.0)
                    ).where(
                        RainfallRecord.municipio_cod == plot.municipio_cod,
                        RainfallRecord.date >= since,
                        RainfallRecord.date <= today,
                    )
                )
                total_mm = float(rain_result.scalar() or 0.0)
                # 1 mm of rain over area_ha → area_ha * 10 m³
                rain_m3 = total_mm * float(plot.area_ha) * 10.0

            total_m3 = irrigation_m3 + rain_m3
            if total_m3 < threshold_value:
                low_plots.append(plot.name)

        if not low_plots:
            continue

        dedup_key = f"low_water_balance:{today.isoformat()}"
        plots_str = ", ".join(low_plots)
        notif = await _create_if_not_exists(
            user_id=user.id,
            tenant_id=tenant.id,
            notification_type="low_water_balance",
            dedup_key=dedup_key,
            title="Balance hídrico bajo",
            message=(
                f"Las parcelas {plots_str} han recibido menos de {threshold_value:.1f} m³ "
                f"(lluvia + riego) en los últimos {threshold_days} días."
            ),
            severity=SEVERITY_WARNING,
            extra_data={
                "threshold_days": threshold_days,
                "threshold_value": threshold_value,
                "plots": low_plots,
            },
            email_enabled=pref["email_enabled"],
            user_email=user.email,
            db=db,
        )
        if notif:
            created += 1
    return created


async def _check_user_inactive(
    today: datetime.date,
    user: User,
    tenant_id: int,
    db: AsyncSession,
) -> int:
    """El usuario no se ha conectado en N días."""
    prefs = await get_preferences(user.id, tenant_id, db)
    pref = prefs["user_inactive"]
    if not pref["enabled"]:
        return 0

    threshold_days = pref["threshold_days"] or 30
    if user.last_seen_at is None:
        return 0

    last_seen_date = user.last_seen_at.date()
    days_absent = (today - last_seen_date).days
    if days_absent < threshold_days:
        return 0

    dedup_key = f"user_inactive:{today.year}-{today.month:02d}"
    notif = await _create_if_not_exists(
        user_id=user.id,
        tenant_id=tenant_id,
        notification_type="user_inactive",
        dedup_key=dedup_key,
        title=f"Llevas {days_absent} días sin conectarte",
        message=(
            f"Han pasado {days_absent} días desde tu última visita a Trufiq. "
            "Recuerda mantener los registros al día para obtener mejores análisis."
        ),
        severity=SEVERITY_INFO,
        extra_data={"days_absent": days_absent},
        email_enabled=pref["email_enabled"],
        user_email=user.email,
        db=db,
    )
    return 1 if notif else 0


async def _check_no_rainfall_data(
    today: datetime.date,
    tenant: Tenant,
    members: list[User],
    db: AsyncSession,
) -> int:
    """Sin registros de lluvia para ninguna parcela del tenant en los últimos N días."""
    created = 0

    # Get distinct municipio codes for this tenant's plots
    plots_result = await db.execute(
        select(Plot.municipio_cod).where(
            Plot.tenant_id == tenant.id,
            Plot.municipio_cod.isnot(None),
        )
    )
    municipios = [row[0] for row in plots_result.all() if row[0]]
    if not municipios:
        return 0

    for user in members:
        prefs = await get_preferences(user.id, tenant.id, db)
        pref = prefs["no_rainfall_data"]
        if not pref["enabled"]:
            continue

        threshold_days = pref["threshold_days"] or 14
        since = today - datetime.timedelta(days=threshold_days)

        result = await db.execute(
            select(func.count(RainfallRecord.id)).where(
                RainfallRecord.municipio_cod.in_(municipios),
                RainfallRecord.date >= since,
                RainfallRecord.date <= today,
            )
        )
        count = result.scalar() or 0
        if count > 0:
            continue

        dedup_key = f"no_rainfall_data:{today.year}-{today.month:02d}"
        notif = await _create_if_not_exists(
            user_id=user.id,
            tenant_id=tenant.id,
            notification_type="no_rainfall_data",
            dedup_key=dedup_key,
            title=f"Sin datos de lluvia en {threshold_days} días",
            message=(
                f"No se han registrado datos de precipitación en los últimos {threshold_days} días. "
                "Comprueba si la importación automática está funcionando correctamente."
            ),
            severity=SEVERITY_INFO,
            extra_data={"threshold_days": threshold_days},
            email_enabled=pref["email_enabled"],
            user_email=user.email,
            db=db,
        )
        if notif:
            created += 1
    return created


async def _check_stressed_plants(
    today: datetime.date,
    tenant: Tenant,
    members: list[User],
    db: AsyncSession,
) -> int:
    """Plantas con estado 'estresada' o 'muerta' sin baja_date desde hace N días."""
    created = 0

    for user in members:
        prefs = await get_preferences(user.id, tenant.id, db)
        pref = prefs["stressed_plant_no_replacement"]
        if not pref["enabled"]:
            continue

        threshold_days = pref["threshold_days"] or 30
        cutoff = today - datetime.timedelta(days=threshold_days)

        result = await db.execute(
            select(func.count(Plant.id)).where(
                Plant.tenant_id == tenant.id,
                Plant.status.in_(["estresada", "muerta"]),
                Plant.baja_date.is_(None),
            )
        )
        count = result.scalar() or 0
        if count == 0:
            continue

        dedup_key = f"stressed_plant_no_replacement:{today.year}-{today.month:02d}"
        notif = await _create_if_not_exists(
            user_id=user.id,
            tenant_id=tenant.id,
            notification_type="stressed_plant_no_replacement",
            dedup_key=dedup_key,
            title=f"{count} planta(s) estresada(s) o muerta(s) sin reemplazar",
            message=(
                f"Hay {count} planta(s) en estado estresada o muerta sin fecha de baja registrada. "
                "Considera revisarlas y actualizar su estado en el mapa de parcelas."
            ),
            severity=SEVERITY_INFO,
            extra_data={"count": count, "threshold_days": threshold_days},
            email_enabled=pref["email_enabled"],
            user_email=user.email,
            db=db,
        )
        if notif:
            created += 1
    return created


async def _check_no_irrigation_summer(
    today: datetime.date,
    tenant: Tenant,
    members: list[User],
    db: AsyncSession,
) -> int:
    """Jul-Sep: sin riegos en parcelas con riego en los últimos N días."""
    if today.month not in (7, 8, 9):
        return 0

    created = 0

    plots_result = await db.execute(
        select(Plot).where(
            Plot.tenant_id == tenant.id,
            Plot.has_irrigation.is_(True),
        )
    )
    plots = list(plots_result.scalars().all())
    if not plots:
        return 0

    for user in members:
        prefs = await get_preferences(user.id, tenant.id, db)
        pref = prefs["no_irrigation_summer"]
        if not pref["enabled"]:
            continue

        threshold_days = pref["threshold_days"] or 14
        since = today - datetime.timedelta(days=threshold_days)

        result = await db.execute(
            select(func.count(IrrigationRecord.id)).where(
                IrrigationRecord.tenant_id == tenant.id,
                IrrigationRecord.date >= since,
                IrrigationRecord.date <= today,
            )
        )
        count = result.scalar() or 0
        if count > 0:
            continue

        dedup_key = f"no_irrigation_summer:{today.year}-{today.month:02d}"
        plot_names = ", ".join(p.name for p in plots)
        notif = await _create_if_not_exists(
            user_id=user.id,
            tenant_id=tenant.id,
            notification_type="no_irrigation_summer",
            dedup_key=dedup_key,
            title=f"Sin riego en {threshold_days} días (verano)",
            message=(
                f"Las parcelas con riego ({plot_names}) no tienen registros de riego "
                f"en los últimos {threshold_days} días. "
                "En verano el riego es crítico para la producción trufícola."
            ),
            severity=SEVERITY_WARNING,
            extra_data={
                "threshold_days": threshold_days,
                "plots": [p.name for p in plots],
            },
            email_enabled=pref["email_enabled"],
            user_email=user.email,
            db=db,
        )
        if notif:
            created += 1
    return created


async def _check_no_brule_measurement(
    today: datetime.date,
    tenant: Tenant,
    members: list[User],
    db: AsyncSession,
) -> int:
    """Sin medición de brûlé en los últimos N días."""
    created = 0

    for user in members:
        prefs = await get_preferences(user.id, tenant.id, db)
        pref = prefs["no_brule_measurement"]
        if not pref["enabled"]:
            continue

        threshold_days = pref["threshold_days"] or 28
        since = today - datetime.timedelta(days=threshold_days)

        result = await db.execute(
            select(func.count(BruleRecord.id)).where(
                BruleRecord.tenant_id == tenant.id,
                BruleRecord.record_date >= since,
            )
        )
        count = result.scalar() or 0
        if count > 0:
            continue

        # Only notify if we have at least one brule record historically
        has_any_result = await db.execute(
            select(func.count(BruleRecord.id)).where(
                BruleRecord.tenant_id == tenant.id,
            )
        )
        if (has_any_result.scalar() or 0) == 0:
            continue

        dedup_key = f"no_brule_measurement:{today.year}-{today.month:02d}"
        weeks = threshold_days // 7
        notif = await _create_if_not_exists(
            user_id=user.id,
            tenant_id=tenant.id,
            notification_type="no_brule_measurement",
            dedup_key=dedup_key,
            title=f"Sin medición de brûlé en {weeks} semana(s)",
            message=(
                f"Llevas {weeks} semana(s) sin registrar mediciones de brûlé. "
                "El seguimiento del brûlé ayuda a predecir la producción y el estado de las plantas."
            ),
            severity=SEVERITY_INFO,
            extra_data={"threshold_days": threshold_days},
            email_enabled=pref["email_enabled"],
            user_email=user.email,
            db=db,
        )
        if notif:
            created += 1
    return created


async def _check_low_harvest(
    today: datetime.date,
    tenant: Tenant,
    members: list[User],
    db: AsyncSession,
) -> int:
    """Dic-Mar: cosecha campaña actual <X% de la media histórica."""
    if today.month not in (12, 1, 2, 3):
        return 0

    cy = campaign_year(today)

    # Current campaign total (kg via PlotHarvest)
    cy_start = datetime.date(cy, 5, 1)
    cy_end = datetime.date(cy + 1, 4, 30)
    current_result = await db.execute(
        select(func.coalesce(func.sum(PlotHarvest.weight_grams), 0.0)).where(
            PlotHarvest.tenant_id == tenant.id,
            PlotHarvest.harvest_date >= cy_start,
            PlotHarvest.harvest_date <= cy_end,
        )
    )
    current_g = float(current_result.scalar() or 0.0)
    if current_g == 0.0:
        return 0  # No data yet, no point alerting

    # Historical average (all completed campaigns before this one)
    prev_result = await db.execute(
        select(func.coalesce(func.sum(PlotHarvest.weight_grams), 0.0)).where(
            PlotHarvest.tenant_id == tenant.id,
            PlotHarvest.harvest_date < cy_start,
        )
    )
    historical_total_g = float(prev_result.scalar() or 0.0)

    # Count distinct campaign years with data
    campaigns_result = await db.execute(
        select(PlotHarvest.harvest_date).where(
            PlotHarvest.tenant_id == tenant.id,
            PlotHarvest.harvest_date < cy_start,
        )
    )
    past_dates = [row[0] for row in campaigns_result.all()]
    past_cy_years = {campaign_year(d) for d in past_dates}
    num_past = len(past_cy_years)

    if num_past == 0 or historical_total_g == 0.0:
        return 0  # No historical data to compare

    avg_g = historical_total_g / num_past
    pct = (current_g / avg_g) * 100.0

    created = 0
    for user in members:
        prefs = await get_preferences(user.id, tenant.id, db)
        pref = prefs["low_harvest_vs_previous"]
        if not pref["enabled"]:
            continue

        threshold_pct = (
            pref["threshold_value"] if pref["threshold_value"] is not None else 50.0
        )
        if pct >= threshold_pct:
            continue

        label = campaign_label(cy)
        dedup_key = f"low_harvest_vs_previous:{cy}-{today.month:02d}"
        notif = await _create_if_not_exists(
            user_id=user.id,
            tenant_id=tenant.id,
            notification_type="low_harvest_vs_previous",
            dedup_key=dedup_key,
            title=f"Cosecha baja en campaña {label}",
            message=(
                f"La cosecha actual de la campaña {label} es un {pct:.0f}% de la media histórica "
                f"({current_g / 1000:.1f} kg vs {avg_g / 1000:.1f} kg de media). "
                "Revisa el estado de las plantas y los eventos de trufa."
            ),
            severity=SEVERITY_WARNING,
            extra_data={
                "campaign_year": cy,
                "current_kg": current_g / 1000.0,
                "avg_kg": avg_g / 1000.0,
                "pct": pct,
            },
            email_enabled=pref["email_enabled"],
            user_email=user.email,
            db=db,
        )
        if notif:
            created += 1
    return created


# ---------------------------------------------------------------------------
# Main cron entry point
# ---------------------------------------------------------------------------


async def check_and_create_notifications(db: AsyncSession) -> int:
    """Run all checkers for all tenants. Returns total notifications created."""
    today = datetime.date.today()
    total_created = 0

    # Load all active tenants
    tenants_result = await db.execute(select(Tenant))
    tenants = list(tenants_result.scalars().all())

    for tenant in tenants:
        # Load active members for this tenant
        members_result = await db.execute(
            select(User)
            .join(TenantMembership, TenantMembership.user_id == User.id)
            .where(
                TenantMembership.tenant_id == tenant.id,
                User.is_active.is_(True),
            )
        )
        members = list(members_result.scalars().all())
        if not members:
            continue

        logger.info(
            "[notifications] Procesando tenant_id=%d (%s) con %d miembro(s)",
            tenant.id,
            tenant.name,
            len(members),
        )

        total_created += await _check_campaign_start(today, tenant, members, db)
        total_created += await _check_campaign_end_reminder(today, tenant, members, db)
        total_created += await _check_no_truffle_events(today, tenant, members, db)
        total_created += await _check_low_water_balance(today, tenant, members, db)
        total_created += await _check_no_rainfall_data(today, tenant, members, db)
        total_created += await _check_stressed_plants(today, tenant, members, db)
        total_created += await _check_no_irrigation_summer(today, tenant, members, db)
        total_created += await _check_no_brule_measurement(today, tenant, members, db)
        total_created += await _check_low_harvest(today, tenant, members, db)

        # user_inactive is per-user (not per-tenant)
        for user in members:
            total_created += await _check_user_inactive(today, user, tenant.id, db)

    logger.info("[notifications] Total avisos creados: %d", total_created)
    return total_created
