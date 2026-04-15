from urllib.parse import urlencode

from fastapi.templating import Jinja2Templates

from app.i18n import get_current_locale, gettext_func, ngettext_func
from app.utils import campaign_label, campaign_months, format_eu

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["campaign_label"] = campaign_label
templates.env.filters["campaign_months"] = campaign_months
templates.env.filters["format_eu"] = format_eu
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
