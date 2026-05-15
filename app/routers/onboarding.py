"""HTTP endpoints for the AI-driven historical-data onboarding flow.

Phase 0 implements only the skeleton:

* ``GET  /onboarding/``            — landing / list previous sessions
* ``POST /onboarding/upload``      — upload Excel, parse, create session
* ``GET  /onboarding/{id}``        — dispatcher view (renders depending on status)
* ``POST /onboarding/{id}/cancel`` — mark a session as cancelled

Subsequent phases will add ``/resolve``, ``/preview`` and ``/confirm`` endpoints.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_subscription  # noqa: F401  (re-exported for dependency_overrides in tests)
from app.database import get_db
from app.jinja import templates
from app.models.user import User
from app.plan_access import (
    ONBOARDING_MONTHLY_LIMITS,
    OnboardingQuotaExceededException,
    WriteAccessDeniedException,
    get_plan_mode,
    is_read_only,
    require_feature,
)
from app.config import settings
from app.services import onboarding_service
from app.services.email_service import send_email
from app.services.import_service import (
    import_expenses_csv,
    import_incomes_csv,
    import_plots_csv,
)
from app.services.onboarding.agent import build_graph
from app.services.onboarding.entity_schemas import ENTITY_SCHEMAS
from app.services.onboarding.excel_parser import parse_workbook
from app.services.onboarding.sheet_inference import infer_sheet_metadata
from app.services.onboarding.transformer import transform_to_csv
from app.services.plots_service import list_plots

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


_ACCEPTED_EXTENSIONS = (".xlsx", ".xls", ".xlsm")
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB safety cap


# Read-access dep: enforce the onboarding_ia feature gate (premium/enterprise).
require_onboarding_read = require_feature("onboarding_ia")


async def require_onboarding_write(
    user: User = Depends(require_onboarding_read),
) -> User:
    """Write access for onboarding: feature gate + not read-only."""
    if is_read_only(user):
        raise WriteAccessDeniedException()
    return user


def _monthly_quota_for(user: User) -> int | None:
    """Return the monthly onboarding-session quota for the user's plan (None = unlimited)."""
    return ONBOARDING_MONTHLY_LIMITS.get(get_plan_mode(user))


@router.get("/", response_class=HTMLResponse)
async def onboarding_index(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_onboarding_read),
):
    sessions = await onboarding_service.list_sessions(
        db, tenant_id=current_user.active_tenant_id
    )
    quota_limit = _monthly_quota_for(current_user)
    if quota_limit is None:
        quota_used = 0  # unlimited; no need to query
    else:
        quota_used = await onboarding_service.count_sessions_this_month(
            db, tenant_id=current_user.active_tenant_id
        )
    return templates.TemplateResponse(
        request,
        "onboarding/index.html",
        {
            "request": request,
            "sessions": sessions,
            "error": None,
            "quota_limit": quota_limit,
            "quota_used": quota_used,
        },
    )


@router.post("/upload", response_class=HTMLResponse)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_onboarding_write),
):
    filename = (file.filename or "").strip()
    if not filename.lower().endswith(_ACCEPTED_EXTENSIONS):
        return await _render_index_with_error(
            request,
            db,
            current_user,
            "Formato no soportado. Sube un fichero Excel (.xlsx, .xls, .xlsm).",
        )

    # Monthly quota check (per plan).
    quota_limit = _monthly_quota_for(current_user)
    if quota_limit is not None:
        used = await onboarding_service.count_sessions_this_month(
            db, tenant_id=current_user.active_tenant_id
        )
        if used >= quota_limit:
            raise OnboardingQuotaExceededException(
                limit=quota_limit, plan=get_plan_mode(current_user)
            )

    content = await file.read()
    if not content:
        return await _render_index_with_error(
            request, db, current_user, "El fichero está vacío."
        )
    if len(content) > _MAX_UPLOAD_BYTES:
        return await _render_index_with_error(
            request, db, current_user, "El fichero supera el tamaño máximo (10 MB)."
        )

    try:
        workbook = parse_workbook(content)
    except ValueError as exc:
        return await _render_index_with_error(request, db, current_user, str(exc))

    # First parsed sheet is the "reference" — its headers drive the LLM
    # mapping and the user-facing column selectors. All other sheets are
    # assumed to share the same structure (typical of one-sheet-per-campaign
    # workbooks).
    parsed = workbook.sheets[0]
    parsed_sheets_state: list[dict[str, object]] = []
    for s in workbook.sheets:
        meta = infer_sheet_metadata(s.sheet_name)
        parsed_sheets_state.append(
            {
                "sheet_name": s.sheet_name,
                "headers": s.headers,
                "header_row_index": s.header_row_index,
                "sample_rows": s.sample_rows,
                "total_data_rows": s.total_data_rows,
                "inferred_plot_name": meta.plot_name,
                "inferred_campaign_year": meta.campaign_year_start,
                "inferred_campaign_label": meta.campaign_label,
            }
        )

    initial_state: dict[str, object] = {
        "original_filename": filename,
        "sheet_name": parsed.sheet_name,
        "headers": parsed.headers,
        "sample_rows": parsed.sample_rows,
        "total_rows": parsed.total_data_rows,
        "header_row_index": parsed.header_row_index,
        "parsed_sheets": parsed_sheets_state,
        "last_node": "parse_excel",
    }
    session = await onboarding_service.create_session(
        db,
        tenant_id=current_user.active_tenant_id,
        created_by_user_id=current_user.id,
        original_filename=filename,
        initial_state=initial_state,
        status="uploaded",
        raw_file=content,
    )
    await db.flush()

    # Run the LLM-powered detection + mapping agent inline. If the LLM is
    # unavailable (no API key, network error, ...) we keep the session in
    # the 'uploaded' state so the user can still retry from the detail page.
    if settings.OPENAI_API_KEY:
        try:
            graph = build_graph()
            new_state = await asyncio.to_thread(graph, dict(initial_state))
            await onboarding_service.update_session_state(
                db,
                session,
                state=new_state,
                status="awaiting_user",
                entity_type=new_state.get("entity_type"),
            )
        except Exception as exc:  # noqa: BLE001
            await onboarding_service.update_session_state(
                db,
                session,
                status="error",
                error_message=f"Fallo en el agente IA: {exc}",
            )

    await db.commit()

    return RedirectResponse(url=f"/onboarding/{session.id}", status_code=303)


@router.get("/{session_id}", response_class=HTMLResponse)
async def session_detail(
    session_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_onboarding_read),
):
    session = await onboarding_service.get_session(
        db, session_id, tenant_id=current_user.active_tenant_id
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    state = session.state_json or {}
    err_count = len(state.get("validation_errors") or [])
    warning_count = len(state.get("import_warnings") or [])

    # "Solicitar ayuda" se ofrece cuando hay señales de fricción:
    #   - sesión en error
    #   - ≥5 errores de validación
    #   - importada pero con errores/warnings (filas omitidas)
    #   - sesión estancada > 3 días en awaiting_user
    stale_threshold = timedelta(days=3)
    is_stale = (
        session.status == "awaiting_user"
        and session.updated_at is not None
        and (datetime.now(UTC) - session.updated_at) > stale_threshold
    )
    help_eligible = (
        session.status == "error"
        or err_count >= 5
        or (session.status == "imported" and (err_count > 0 or warning_count > 0))
        or is_stale
    )

    return templates.TemplateResponse(
        request,
        "onboarding/detail.html",
        {
            "request": request,
            "session": session,
            "state": state,
            "entity_schemas": ENTITY_SCHEMAS,
            "help_eligible": help_eligible,
            "stale_session": is_stale,
        },
    )


@router.post("/{session_id}/resolve")
async def resolve_mapping(
    session_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_onboarding_write),
):
    """Persist the user's edits to the column mapping (human-in-the-loop)."""
    session = await onboarding_service.get_session(
        db, session_id, tenant_id=current_user.active_tenant_id
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    state = dict(session.state_json or {})
    headers: list[str] = list(state.get("headers") or [])
    form = await request.form()

    # Optional: user may correct the entity type via the form too.
    entity_type = form.get("entity_type") or state.get("entity_type")

    resolved: list[dict[str, object]] = []
    for header in headers:
        target = (form.get(f"target__{header}") or "IGNORE").strip()
        resolved.append(
            {
                "source_column": header,
                "target_field": target or "IGNORE",
            }
        )
    state["resolved_mapping"] = resolved
    state["entity_type"] = entity_type
    state["last_node"] = "resolve_mapping"

    # Run the transform/validate step now so the user immediately sees the
    # preview + validation errors on the next render. When the workbook has
    # multiple sheets we transform each one with its inferred plot name as a
    # constant (e.g. ``bancal`` for ingresos) and concatenate the CSVs.
    if session.raw_file and entity_type in ENTITY_SCHEMAS:
        try:
            parsed_sheets = list(state.get("parsed_sheets") or [])
            if not parsed_sheets:
                parsed_sheets = [
                    {
                        "sheet_name": state.get("sheet_name"),
                        "header_row_index": int(state.get("header_row_index") or 1),
                        "inferred_plot_name": None,
                        "total_data_rows": state.get("total_rows") or 0,
                    }
                ]

            # Decide *per-entity, per-mapping* whether the plot is per-row or
            # sheet-level: if the user's resolved_mapping already binds some
            # column to ``bancal`` (the plot field), the plot is per-row and
            # any sheet-name inference must NOT override it nor block the
            # import. Otherwise, if the target schema has a ``bancal`` field
            # and we inferred one from the sheet name, we apply it as a
            # constant — and in that case we do validate that the plot
            # exists for this tenant.
            schema = ENTITY_SCHEMAS.get(entity_type)
            schema_field_ids = set(schema.field_ids()) if schema else set()
            mapped_targets = {
                (m.get("target_field") or "").strip()
                for m in resolved
                if (m.get("target_field") or "").strip() not in ("", "IGNORE")
            }
            plot_field = "bancal"
            plot_is_per_row = plot_field in mapped_targets
            uses_sheet_level_plot = (
                plot_field in schema_field_ids and not plot_is_per_row
            )

            existing_plots = await list_plots(db, current_user.active_tenant_id)
            existing_plot_names = {p.name.strip().lower() for p in existing_plots}
            missing_plots: dict[str, list[str]] = {}
            if uses_sheet_level_plot:
                for ps in parsed_sheets:
                    plot_name = (ps.get("inferred_plot_name") or "").strip()
                    if (
                        plot_name
                        and plot_name.lower() not in existing_plot_names
                    ):
                        missing_plots.setdefault(plot_name, []).append(
                            ps.get("sheet_name") or ""
                        )

            combined_csv: list[str] = []
            all_errors: list[dict[str, object]] = []
            per_sheet_summary: list[dict[str, object]] = []
            for ps in parsed_sheets:
                plot_name = (ps.get("inferred_plot_name") or "").strip() or None
                sheet_name = ps.get("sheet_name")
                if (
                    plot_name
                    and uses_sheet_level_plot
                    and plot_name in missing_plots
                ):
                    all_errors.append(
                        {
                            "row_index": 0,
                            "column": plot_field,
                            "sheet": sheet_name,
                            "message": (
                                f"La parcela '{plot_name}' (inferida de la hoja "
                                f"'{sheet_name}') no existe. Créala antes de "
                                f"importar o renombra la hoja."
                            ),
                        }
                    )
                    per_sheet_summary.append(
                        {
                            "sheet_name": sheet_name,
                            "inferred_plot_name": plot_name,
                            "rows_imported": 0,
                            "errors_count": 1,
                            "missing_plot": True,
                        }
                    )
                    continue

                constants: dict[str, object] = {}
                if plot_name and uses_sheet_level_plot:
                    constants[plot_field] = plot_name
                csv_text, errors = transform_to_csv(
                    content=session.raw_file,
                    sheet_name=sheet_name,
                    headers=headers,
                    header_row_index=int(ps.get("header_row_index") or 1),
                    entity_type=entity_type,
                    resolved_mapping=resolved,
                    constants=constants,
                )
                row_count = csv_text.count("\n")
                per_sheet_summary.append(
                    {
                        "sheet_name": sheet_name,
                        "inferred_plot_name": plot_name,
                        "rows_imported": row_count,
                        "errors_count": len(errors),
                        "missing_plot": False,
                    }
                )
                if csv_text:
                    combined_csv.append(csv_text)
                for err in errors:
                    err_with_sheet = dict(err)
                    err_with_sheet["sheet"] = sheet_name
                    all_errors.append(err_with_sheet)
            state["csv_output"] = "".join(combined_csv)
            state["validation_errors"] = all_errors
            state["transformed_rows"] = state["csv_output"].count("\n")
            state["per_sheet_summary"] = per_sheet_summary
            state["missing_plots"] = sorted(missing_plots.keys())
        except Exception as exc:  # noqa: BLE001
            state["validation_errors"] = [
                {"row_index": 0, "message": f"Fallo en la transformación: {exc}"}
            ]

    await onboarding_service.update_session_state(
        db,
        session,
        state=state,
        status="previewing",
        entity_type=entity_type,
        error_message="",
    )
    await db.commit()
    return RedirectResponse(url=f"/onboarding/{session_id}", status_code=303)


@router.post("/{session_id}/confirm")
async def confirm_import(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_onboarding_write),
):
    """Run the actual Trufiq import using the previously generated CSV."""
    session = await onboarding_service.get_session(
        db, session_id, tenant_id=current_user.active_tenant_id
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    state = dict(session.state_json or {})
    csv_text = state.get("csv_output") or ""
    entity_type = session.entity_type or state.get("entity_type")

    if not csv_text or not entity_type:
        raise HTTPException(
            status_code=400,
            detail="No hay CSV generado para importar; confirma primero el mapeo.",
        )

    missing_plots = list(state.get("missing_plots") or [])
    if missing_plots:
        raise HTTPException(
            status_code=400,
            detail=(
                "No se puede importar: las siguientes parcelas no existen — "
                + ", ".join(missing_plots)
                + ". Créalas primero o renombra las hojas correspondientes."
            ),
        )

    importer = {
        "gastos": import_expenses_csv,
        "ingresos": import_incomes_csv,
        "parcelas": import_plots_csv,
    }.get(entity_type)
    if importer is None:
        raise HTTPException(
            status_code=400,
            detail=f"Importación no soportada para la entidad '{entity_type}'.",
        )

    try:
        rows, warnings = await importer(
            db, csv_text.encode("utf-8"), current_user.active_tenant_id
        )
        state["import_warnings"] = warnings
        state["imported_count"] = len(rows)
        await onboarding_service.update_session_state(
            db,
            session,
            state=state,
            status="imported",
            error_message="",
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        await onboarding_service.update_session_state(
            db,
            session,
            status="error",
            error_message=f"Fallo en la importación: {exc}",
        )
        await db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RedirectResponse(url=f"/onboarding/{session_id}", status_code=303)


@router.post("/{session_id}/cancel")
async def cancel_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_onboarding_write),
):
    session = await onboarding_service.get_session(
        db, session_id, tenant_id=current_user.active_tenant_id
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    await onboarding_service.mark_cancelled(db, session)
    await db.commit()
    return RedirectResponse(url="/onboarding/", status_code=303)


@router.post("/{session_id}/run-agent")
async def run_agent(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_onboarding_write),
):
    """Re-run the LLM agent on an existing session (useful after errors)."""
    session = await onboarding_service.get_session(
        db, session_id, tenant_id=current_user.active_tenant_id
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="El servicio LLM no está configurado en este entorno.",
        )
    try:
        graph = build_graph()
        new_state = await asyncio.to_thread(graph, dict(session.state_json or {}))
        await onboarding_service.update_session_state(
            db,
            session,
            state=new_state,
            status="awaiting_user",
            entity_type=new_state.get("entity_type"),
            error_message="",
        )
    except Exception as exc:  # noqa: BLE001
        await onboarding_service.update_session_state(
            db,
            session,
            status="error",
            error_message=f"Fallo en el agente IA: {exc}",
        )
    await db.commit()
    return RedirectResponse(url=f"/onboarding/{session_id}", status_code=303)


@router.post("/{session_id}/request-help")
async def request_help(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_onboarding_write),
):
    """Send an email to support with the session context and mark it for follow-up."""
    session = await onboarding_service.get_session(
        db, session_id, tenant_id=current_user.active_tenant_id
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    support_to = settings.CONTACT_EMAIL or settings.ADMIN_EMAIL
    if support_to:
        state = session.state_json or {}
        validation_errors = state.get("validation_errors") or []
        subject = (
            f"[Trufiq] Ayuda con onboarding #{session.id} "
            f"(tenant {session.tenant_id})"
        )
        html = (
            f"<p>El usuario <strong>{getattr(current_user, 'email', current_user.id)}"
            f"</strong> ha pedido ayuda con una sesión de onboarding.</p>"
            f"<ul>"
            f"<li>Sesión: #{session.id}</li>"
            f"<li>Tenant: {session.tenant_id}</li>"
            f"<li>Fichero: {session.original_filename}</li>"
            f"<li>Estado: {session.status}</li>"
            f"<li>Entidad detectada: {session.entity_type or '—'}</li>"
            f"<li>Errores de validación: {len(validation_errors)}</li>"
            f"<li>Mensaje de error: {session.error_message or '—'}</li>"
            f"</ul>"
            f"<p>URL: {settings.APP_BASE_URL}/onboarding/{session.id}</p>"
        )
        try:
            await send_email(support_to, subject, html)
        except Exception:  # noqa: BLE001
            # Email failure must not break the user flow; the state flag still
            # records that help was requested so the UI can confirm.
            logger.exception(
                "onboarding.request_help.email_failed",
                extra={
                    "session_id": session.id,
                    "tenant_id": session.tenant_id,
                    "user_id": current_user.id,
                },
            )

    logger.info(
        "onboarding.request_help",
        extra={
            "session_id": session.id,
            "tenant_id": session.tenant_id,
            "user_id": current_user.id,
            "status": session.status,
            "entity_type": session.entity_type,
            "support_to": support_to or "<unset>",
        },
    )

    state = dict(session.state_json or {})
    state["help_requested_at"] = datetime.now(UTC).isoformat()
    await onboarding_service.update_session_state(db, session, state=state)
    await db.commit()
    return RedirectResponse(url=f"/onboarding/{session_id}", status_code=303)


async def _render_index_with_error(
    request: Request, db: AsyncSession, current_user: User, message: str
) -> HTMLResponse:
    sessions = await onboarding_service.list_sessions(
        db, tenant_id=current_user.active_tenant_id
    )
    quota_limit = _monthly_quota_for(current_user)
    quota_used = 0
    if quota_limit is not None:
        quota_used = await onboarding_service.count_sessions_this_month(
            db, tenant_id=current_user.active_tenant_id
        )
    return templates.TemplateResponse(
        request,
        "onboarding/index.html",
        {
            "request": request,
            "sessions": sessions,
            "error": message,
            "quota_limit": quota_limit,
            "quota_used": quota_used,
        },
        status_code=400,
    )
