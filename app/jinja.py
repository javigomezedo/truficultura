from fastapi.templating import Jinja2Templates

from app.utils import campaign_label

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["campaign_label"] = campaign_label
templates.env.add_extension("jinja2.ext.i18n")
