from fastapi.templating import Jinja2Templates

from app.utils import campaign_label, campaign_months

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["campaign_label"] = campaign_label
templates.env.filters["campaign_months"] = campaign_months
templates.env.add_extension("jinja2.ext.i18n")
