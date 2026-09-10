import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import scheduler as scheduler_module
from .config import settings
from .database import init_db
from .routers import meta, notifications, plex_auth, services, status
from .security import require_auth

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("healthchecker")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler_module.start()
    logger.info("HealthChecker started - polling every %ss by default", settings.default_poll_interval_seconds)
    yield
    scheduler_module.shutdown()


app = FastAPI(title="Media Estate HealthChecker", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(services.router)
app.include_router(status.router)
app.include_router(notifications.router)
app.include_router(meta.router)
app.include_router(plex_auth.router)


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
