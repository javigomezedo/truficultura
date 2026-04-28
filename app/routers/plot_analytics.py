from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_subscription
from app.database import get_db
from app.models.user import User
from app.services.plot_analytics_service import (
    detect_irrigation_thresholds,
    get_all_plot_thresholds,
    get_campaign_dataset,
    get_irrigation_vs_production_analysis,
    get_multi_plot_comparison,
    get_plot_detail_context,
    get_pruning_vs_production_analysis,
    get_tilling_vs_production_analysis,
)
from app.utils import campaign_label

router = APIRouter(prefix="/plot-analytics", tags=["plot_analytics"])
templates = Jinja2Templates(directory="app/templates")


def _parse_optional_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _format_num(value: float | int | None, decimals: int = 1) -> str:
    if value is None:
        return "—"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{decimals}f}"


def _management_group_label(group_key: str) -> str:
    labels = {
        "sin_labrado": "Sin labrado",
        "con_labrado": "Con labrado",
    }
    return labels.get(group_key, group_key)


def _build_overview_explanation(
    irrigation_analysis: dict,
    pruning_analysis: dict,
    management_analysis: dict,
    irrigation_thresholds: dict,
) -> dict:
    bullets: list[str] = []
    actions: list[str] = []

    sample_size = irrigation_analysis.get("sample_size", 0)
    if sample_size < 5:
        bullets.append(
            "Hay pocos datos comparables. Toma estas conclusiones como orientación inicial, no como regla fija."
        )
    else:
        bullets.append(
            f"El análisis usa {sample_size} registros (bancal × campaña) con agua y producción registradas, así que la foto ya es razonablemente sólida."
        )

    delta_percent = pruning_analysis.get("delta_percent")
    if delta_percent is None:
        bullets.append(
            "Con los datos actuales no se puede medir bien la diferencia entre campañas con poda y sin poda."
        )
    elif delta_percent >= 10:
        bullets.append(
            f"Cuando hubo poda, la producción media fue un {abs(delta_percent):.1f}% mayor."
        )
        actions.append(
            "Repite el patrón de poda de las campañas que mejor funcionaron y registra fecha y tipo de poda."
        )
    elif delta_percent <= -10:
        bullets.append(
            f"En tus datos, las campañas con poda produjeron un {abs(delta_percent):.1f}% menos de media."
        )
        actions.append(
            "Revisa intensidad y momento de poda: puede que se esté podando tarde o en exceso."
        )
    else:
        bullets.append(
            "La diferencia entre podar y no podar es pequeña en tus registros actuales."
        )

    threshold_status = irrigation_thresholds.get("status")
    plateau_start = irrigation_thresholds.get("plateau_start_m3")
    if threshold_status != "ok":
        bullets.append(
            "Todavía no hay suficientes registros para detectar el punto donde más riego deja de compensar."
        )
    elif plateau_start is None:
        bullets.append(
            "No se detecta un techo claro de riego: en tu histórico, más agua no muestra un punto de saturación evidente."
        )
    else:
        bullets.append(
            f"A partir de ~{_format_num(plateau_start, 1)} m³ por campaña, el riego extra aporta poca mejora de producción."
        )
        actions.append(
            f"Mantén el riego por debajo de ~{_format_num(plateau_start, 1)} m³: superar ese umbral no mejoró la cosecha en campañas anteriores."
        )

    water_bands = irrigation_analysis.get("water_bands", [])
    bands_with_data = [b for b in water_bands if b.get("count", 0) > 0]
    if len(bands_with_data) >= 2:
        best_band = max(bands_with_data, key=lambda b: b.get("avg_production_kg", 0.0))
        band_labels = {"bajo": "bajo", "medio": "moderado", "alto": "elevado"}
        best_label = band_labels.get(best_band["band"], best_band["band"])
        best_avg = best_band.get("avg_production_kg", 0.0)
        best_max = best_band.get("max_m3")
        best_min = best_band.get("min_m3", 0.0)

        if best_band["band"] == "bajo":
            range_str = f"≤ {_format_num(best_max, 1)} m³"
        elif best_band["band"] == "medio":
            range_str = f"{_format_num(best_min, 1)}–{_format_num(best_max, 1)} m³"
        else:
            range_str = f"> {_format_num(best_min, 1)} m³"

        if best_band["band"] != "alto":
            bullets.append(
                f"Curiosamente, el riego {best_label} ({range_str}) obtuvo la mejor producción media ({_format_num(best_avg, 1)} kg): regar más no siempre da más trufa."
            )
            actions.append(
                f"Prueba a no superar el rango de riego {best_label} ({range_str}) y observa si la eficiencia mejora."
            )
        else:
            bullets.append(
                f"El riego elevado ({range_str}) fue el que más producción generó de media ({_format_num(best_avg, 1)} kg), aunque esto puede variar por parcela."
            )

    groups = management_analysis.get("groups", [])
    best_group = None
    best_avg = None
    for group in groups:
        if group.get("count", 0) <= 0:
            continue
        group_avg = group.get("avg_production_kg", 0.0)
        if best_avg is None or group_avg > best_avg:
            best_avg = group_avg
            best_group = group

    if best_group is not None:
        group_name = _management_group_label(best_group.get("group", ""))
        bullets.append(
            f"El patrón de labores con mejor producción media fue: {group_name.lower()} ({_format_num(best_group.get('avg_production_kg'), 1)} kg de media)."
        )
        actions.append(
            "Compara ese patrón con las parcelas menos productivas para copiar las prácticas que sí funcionan."
        )

    if not actions:
        actions.append(
            "Sigue registrando datos de forma constante: con más campañas, las recomendaciones serán más fiables."
        )

    return {
        "summary": "Resumen fácil",
        "bullets": bullets,
        "actions": actions,
    }


@router.get("/", response_class=HTMLResponse)
async def overview(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    campaign_from: Optional[str] = Query(default=None),
    campaign_to: Optional[str] = Query(default=None),
):
    campaign_from_value = _parse_optional_int(campaign_from)
    campaign_to_value = _parse_optional_int(campaign_to)

    dataset = await get_campaign_dataset(
        db,
        current_user.id,
        campaign_from=campaign_from_value,
        campaign_to=campaign_to_value,
    )
    irrigation_analysis = await get_irrigation_vs_production_analysis(
        db,
        current_user.id,
        campaign_from=campaign_from_value,
        campaign_to=campaign_to_value,
    )
    pruning_analysis = await get_pruning_vs_production_analysis(
        db,
        current_user.id,
        campaign_from=campaign_from_value,
        campaign_to=campaign_to_value,
    )
    management_analysis = await get_tilling_vs_production_analysis(
        db,
        current_user.id,
        campaign_from=campaign_from_value,
        campaign_to=campaign_to_value,
    )
    irrigation_thresholds = await detect_irrigation_thresholds(
        db,
        current_user.id,
        campaign_from=campaign_from_value,
        campaign_to=campaign_to_value,
    )
    all_plot_thresholds = await get_all_plot_thresholds(
        db,
        current_user.id,
        campaign_from=campaign_from_value,
        campaign_to=campaign_to_value,
    )

    campaign_options = sorted({row["campaign_year"] for row in dataset}, reverse=True)
    explanation = _build_overview_explanation(
        irrigation_analysis,
        pruning_analysis,
        management_analysis,
        irrigation_thresholds,
    )

    return templates.TemplateResponse(
        request,
        "analitica_parcelas/overview.html",
        {
            "request": request,
            "dataset": dataset,
            "campaign_options": campaign_options,
            "selected_campaign_from": campaign_from_value,
            "selected_campaign_to": campaign_to_value,
            "irrigation_analysis": irrigation_analysis,
            "pruning_analysis": pruning_analysis,
            "management_analysis": management_analysis,
            "irrigation_thresholds": irrigation_thresholds,
            "all_plot_thresholds": all_plot_thresholds,
            "explanation": explanation,
            "campaign_label": campaign_label,
        },
    )


@router.get("/dataset", response_class=JSONResponse)
async def dataset_json(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    campaign_from: Optional[str] = Query(default=None),
    campaign_to: Optional[str] = Query(default=None),
):
    campaign_from_value = _parse_optional_int(campaign_from)
    campaign_to_value = _parse_optional_int(campaign_to)

    rows = await get_campaign_dataset(
        db,
        current_user.id,
        campaign_from=campaign_from_value,
        campaign_to=campaign_to_value,
    )
    return rows


@router.get("/irrigation-impact", response_class=JSONResponse)
async def irrigation_impact_json(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    campaign_from: Optional[str] = Query(default=None),
    campaign_to: Optional[str] = Query(default=None),
):
    campaign_from_value = _parse_optional_int(campaign_from)
    campaign_to_value = _parse_optional_int(campaign_to)
    return await get_irrigation_vs_production_analysis(
        db,
        current_user.id,
        campaign_from=campaign_from_value,
        campaign_to=campaign_to_value,
    )


@router.get("/pruning-impact", response_class=JSONResponse)
async def pruning_impact_json(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    campaign_from: Optional[str] = Query(default=None),
    campaign_to: Optional[str] = Query(default=None),
):
    campaign_from_value = _parse_optional_int(campaign_from)
    campaign_to_value = _parse_optional_int(campaign_to)
    return await get_pruning_vs_production_analysis(
        db,
        current_user.id,
        campaign_from=campaign_from_value,
        campaign_to=campaign_to_value,
    )


@router.get("/management-impact", response_class=JSONResponse)
async def management_impact_json(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    campaign_from: Optional[str] = Query(default=None),
    campaign_to: Optional[str] = Query(default=None),
):
    campaign_from_value = _parse_optional_int(campaign_from)
    campaign_to_value = _parse_optional_int(campaign_to)
    return await get_tilling_vs_production_analysis(
        db,
        current_user.id,
        campaign_from=campaign_from_value,
        campaign_to=campaign_to_value,
    )


@router.get("/irrigation-thresholds", response_class=JSONResponse)
async def irrigation_thresholds_json(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    campaign_from: Optional[str] = Query(default=None),
    campaign_to: Optional[str] = Query(default=None),
):
    campaign_from_value = _parse_optional_int(campaign_from)
    campaign_to_value = _parse_optional_int(campaign_to)
    return await detect_irrigation_thresholds(
        db,
        current_user.id,
        campaign_from=campaign_from_value,
        campaign_to=campaign_to_value,
    )


@router.get("/comparison", response_class=JSONResponse)
async def comparison_json(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    campaign_from: Optional[str] = Query(default=None),
    campaign_to: Optional[str] = Query(default=None),
):
    campaign_from_value = _parse_optional_int(campaign_from)
    campaign_to_value = _parse_optional_int(campaign_to)
    return await get_multi_plot_comparison(
        db,
        current_user.id,
        campaign_from=campaign_from_value,
        campaign_to=campaign_to_value,
    )


@router.get("/comparison-view", response_class=HTMLResponse)
async def comparison_view(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    campaign_from: Optional[str] = Query(default=None),
    campaign_to: Optional[str] = Query(default=None),
):
    campaign_from_value = _parse_optional_int(campaign_from)
    campaign_to_value = _parse_optional_int(campaign_to)

    comparison = await get_multi_plot_comparison(
        db,
        current_user.id,
        campaign_from=campaign_from_value,
        campaign_to=campaign_to_value,
    )
    dataset = await get_campaign_dataset(
        db,
        current_user.id,
        campaign_from=campaign_from_value,
        campaign_to=campaign_to_value,
    )
    campaign_options = sorted({row["campaign_year"] for row in dataset}, reverse=True)

    return templates.TemplateResponse(
        request,
        "analitica_parcelas/comparison.html",
        {
            "request": request,
            "comparison": comparison,
            "campaign_options": campaign_options,
            "selected_campaign_from": campaign_from_value,
            "selected_campaign_to": campaign_to_value,
        },
    )


@router.get("/plot/{plot_id}", response_class=HTMLResponse)
async def plot_detail(
    request: Request,
    plot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    campaign_from: Optional[str] = Query(default=None),
    campaign_to: Optional[str] = Query(default=None),
):
    campaign_from_value = _parse_optional_int(campaign_from)
    campaign_to_value = _parse_optional_int(campaign_to)

    context = await get_plot_detail_context(
        db,
        current_user.id,
        plot_id,
        campaign_from=campaign_from_value,
        campaign_to=campaign_to_value,
    )
    plot_thresholds = await detect_irrigation_thresholds(
        db,
        current_user.id,
        campaign_from=campaign_from_value,
        campaign_to=campaign_to_value,
        plot_ids=[plot_id],
    )
    global_thresholds = await detect_irrigation_thresholds(
        db,
        current_user.id,
        campaign_from=campaign_from_value,
        campaign_to=campaign_to_value,
    )
    if context is None:
        return templates.TemplateResponse(
            request,
            "analitica_parcelas/plot_detail.html",
            {
                "request": request,
                "plot": None,
                "dataset": [],
                "labels": [],
                "production_series": [],
                "water_series": [],
                "pruning_series": [],
                "tilling_series": [],
                "digging_series": [],
                "scatter_points": [],
                "insights": {"status": "no_data", "messages": []},
                "campaign_label": campaign_label,
            },
            status_code=404,
        )

    return templates.TemplateResponse(
        request,
        "analitica_parcelas/plot_detail.html",
        {
            "request": request,
            **context,
            "plot_thresholds": plot_thresholds,
            "global_thresholds": global_thresholds,
            "campaign_label": campaign_label,
        },
    )


@router.get("/plot/{plot_id}/json", response_class=JSONResponse)
async def plot_detail_json(
    plot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    campaign_from: Optional[str] = Query(default=None),
    campaign_to: Optional[str] = Query(default=None),
):
    campaign_from_value = _parse_optional_int(campaign_from)
    campaign_to_value = _parse_optional_int(campaign_to)

    context = await get_plot_detail_context(
        db,
        current_user.id,
        plot_id,
        campaign_from=campaign_from_value,
        campaign_to=campaign_to_value,
    )
    if context is None:
        return JSONResponse(
            {"detail": "plot_not_found"},
            status_code=404,
        )

    return {
        "plot": {
            "id": context["plot"].id,
            "name": context["plot"].name,
        },
        "dataset": context["dataset"],
        "labels": context["labels"],
        "production_series": context["production_series"],
        "water_series": context["water_series"],
        "pruning_series": context["pruning_series"],
        "tilling_series": context["tilling_series"],
        "digging_series": context["digging_series"],
        "scatter_points": context["scatter_points"],
        "insights": context["insights"],
    }
