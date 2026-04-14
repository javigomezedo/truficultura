from fastapi.templating import Jinja2Templates

from app.utils import campaign_label, campaign_months, format_eu

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["campaign_label"] = campaign_label
templates.env.filters["campaign_months"] = campaign_months
templates.env.filters["format_eu"] = format_eu
templates.env.add_extension("jinja2.ext.i18n")
