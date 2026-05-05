from datetime import UTC, datetime, timedelta
import json
from urllib.parse import urlencode

from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from app.i18n import get_current_locale, gettext_func, ngettext_func
from app.plan_access import PLAN_HIERARCHY, _FEATURE_PLANS
from app.utils import campaign_label, campaign_months, format_eu

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["campaign_label"] = campaign_label
templates.env.filters["campaign_months"] = campaign_months
templates.env.filters["format_eu"] = format_eu


def _tojson_safe(value: object) -> Markup:
    """Serialize *value* to JSON and escape <, >, & so the result is safe
    to embed directly inside a <script> block without XSS risk.
    """
    serialized = json.dumps(value)
    serialized = (
        serialized
        .replace("<", r"\u003c")
        .replace(">", r"\u003e")
        .replace("&", r"\u0026")
    )
    return Markup(serialized)


templates.env.filters["tojson_safe"] = _tojson_safe
templates.env.add_extension("jinja2.ext.i18n")
templates.env.install_gettext_callables(gettext_func, ngettext_func, newstyle=True)
templates.env.globals["get_current_locale"] = get_current_locale
templates.env.globals["AVAILABLE_LOCALES"] = ["es", "en", "fr"]


def sort_url(request, field: str, current_sort: str, current_order: str) -> str:
    """Build a URL that sorts the current page by ``field``, toggling direction."""
    params = {
        k: v
        for k, v in request.query_params.items()
        if v and k not in ("sort", "order")
    }
    if current_sort == field:
        params["order"] = "asc" if current_order == "desc" else "desc"
    else:
        params["order"] = "desc"
    params["sort"] = field
    return str(request.url.path) + "?" + urlencode(params)


templates.env.globals["sort_url"] = sort_url
templates.env.globals["now_utc"] = lambda: datetime.now(UTC)
templates.env.globals["timedelta_one_day"] = timedelta(days=1)


def _session_plan_mode(session: dict) -> str:
    """Compute plan mode from session dict (for Jinja2 templates)."""
    if session.get("role") == "admin":
        return "enterprise"
    sub_status = session.get("subscription_status", "")
    if sub_status == "trialing":
        trial_days_left = session.get("trial_days_left")
        if trial_days_left is not None and trial_days_left >= 0:
            return "trial"
        return "read_only"
    if sub_status == "active":
        sub_days_left = session.get("subscription_days_left")
        if sub_days_left is not None and sub_days_left < 0:
            return "read_only"
        plan = session.get("tenant_plan")
        if plan in ("basic", "premium", "enterprise"):
            return plan
        return "basic"
    return "read_only"


def _session_has_feature(session: dict, feature: str) -> bool:
    """Check if the session's plan includes *feature* (for Jinja2 templates)."""
    mode = _session_plan_mode(session)
    if mode == "trial":
        return True
    effective_plan = "basic" if mode == "read_only" else mode
    allowed = _FEATURE_PLANS.get(feature, set(PLAN_HIERARCHY))
    return effective_plan in allowed


templates.env.globals["session_plan_mode"] = _session_plan_mode
templates.env.globals["session_has_feature"] = _session_has_feature
