import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import scheduler as scheduler_module
from .config import settings
from .database import get_db, init_db
from .queries import get_or_create_ui_settings
from .routers import checks_bulk, dashboard_layouts, dashboard_settings, downtime, icon_uploads, log_pruning, meta, notification_channels, notifications, plex_auth, services, status, ui_settings
from .security import require_auth
from .version import VERSION

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("checkarr")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler_module.start()
    logger.info("Checkarr started - polling every %ss by default", settings.default_poll_interval_seconds)
    yield
    scheduler_module.shutdown()


app = FastAPI(title="Checkarr", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
# settings.icons_path creates the directory (under /config) the first time
# it's accessed if it doesn't exist yet - needed here since StaticFiles
# requires the directory to already exist at mount time, which runs at
# import time, before lifespan's init_db() would otherwise have a chance to
# set anything up. Also mounted on the public app (public.py) - a custom
# icon needs to load there too, wherever that service's card shows up.
app.mount("/custom-icons", StaticFiles(directory=str(settings.icons_path)), name="custom-icons")
templates = Jinja2Templates(directory="app/templates")

app.include_router(services.router)
app.include_router(icon_uploads.router)
app.include_router(status.router)
app.include_router(notifications.router)
app.include_router(meta.router)
app.include_router(plex_auth.router)
app.include_router(checks_bulk.router)
app.include_router(dashboard_layouts.router)
app.include_router(dashboard_settings.router)
app.include_router(notification_channels.router)
app.include_router(downtime.router)
app.include_router(log_pruning.router)
app.include_router(ui_settings.router)


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def index(request: Request, db: Session = Depends(get_db)):
    # Rendered server-side (not applied via JS after load) so the admin-wide
    # theme is there from the very first paint, no flash of the default dark
    # theme first - see Settings > Customizations / models.UiSettings. A
    # layout's own theme override (edit mode's theme picker) is JS-applied
    # instead, scoped to just #tab-dashboard, once that layout's data loads.
    theme = get_or_create_ui_settings(db).theme
    return templates.TemplateResponse(request, "index.html", {"version": VERSION, "theme": theme})


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
