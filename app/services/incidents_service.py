from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.incident import Incident


async def create_incident(
    db: AsyncSession,
    tenant_id: int,
    user_id: int,
    title: str,
    description: str,
    category: str,
    severity: str,
    attachment_filename: Optional[str] = None,
    attachment_data: Optional[bytes] = None,
    attachment_content_type: Optional[str] = None,
) -> Incident:
    incident = Incident(
        tenant_id=tenant_id,
        user_id=user_id,
        title=title,
        description=description,
        category=category,
        severity=severity,
        attachment_filename=attachment_filename,
        attachment_data=attachment_data,
        attachment_content_type=attachment_content_type,
    )
    db.add(incident)
    await db.commit()
    await db.refresh(incident)
    return incident


async def get_incidents_by_tenant(
    db: AsyncSession,
    tenant_id: int,
) -> list[Incident]:
    result = await db.execute(
        select(Incident)
        .where(Incident.tenant_id == tenant_id)
        .options(selectinload(Incident.user))
        .order_by(desc(Incident.created_at))
    )
    return list(result.scalars().all())


async def get_incident_by_id(
    db: AsyncSession,
    incident_id: int,
) -> Optional[Incident]:
    result = await db.execute(
        select(Incident)
        .where(Incident.id == incident_id)
        .options(selectinload(Incident.user), selectinload(Incident.tenant))
    )
    return result.scalar_one_or_none()


async def get_all_incidents_admin(
    db: AsyncSession,
    resolved: Optional[bool] = None,
    tenant_id: Optional[int] = None,
    category: Optional[str] = None,
    severity: Optional[str] = None,
) -> list[Incident]:
    stmt = (
        select(Incident)
        .options(selectinload(Incident.user), selectinload(Incident.tenant))
        .order_by(desc(Incident.created_at))
    )
    if resolved is not None:
        stmt = stmt.where(Incident.resolved == resolved)
    if tenant_id is not None:
        stmt = stmt.where(Incident.tenant_id == tenant_id)
    if category:
        stmt = stmt.where(Incident.category == category)
    if severity:
        stmt = stmt.where(Incident.severity == severity)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def resolve_incident(
    db: AsyncSession,
    incident: Incident,
    admin_response: str,
) -> Incident:
    incident.resolved = True
    incident.admin_response = admin_response
    incident.resolved_at = datetime.datetime.now(datetime.timezone.utc)
    await db.commit()
    await db.refresh(incident)
    return incident
