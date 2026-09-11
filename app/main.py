import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import scheduler as scheduler_module
from .config import settings
from .database import init_db
from .routers import checks_bulk, dashboard_layouts, dashboard_settings, downtime, log_pruning, meta, notification_channels, notifications, plex_auth, services, status
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
templates = Jinja2Templates(directory="app/templates")

app.include_router(services.router)
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


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"version": VERSION})


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
