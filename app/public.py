"""A second, deliberately minimal ASGI app for the public-facing dashboard
port. It shares the database and query helpers with the main app but never
imports the services router (service/check CRUD, API key handling) - so
even a probing request can't reach anything mutating or secret-bearing,
regardless of what the frontend shows or hides.
"""

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import schemas
from .config import settings
from .database import get_db
from .queries import get_active_issues, get_history, get_public_layout, get_service_statuses, resolve_layout_for_viewport
from .routers.meta import get_meta
from .version import VERSION

public_app = FastAPI(title="Checkarr Status", docs_url=None, redoc_url=None, openapi_url=None)
public_app.mount("/static", StaticFiles(directory="app/static"), name="static")
# Read-only here (uploading is an admin-only route, see routers/icon_uploads.py)
# - just needs to be servable wherever a service with a custom icon shows up.
public_app.mount("/custom-icons", StaticFiles(directory=str(settings.icons_path)), name="custom-icons")
templates = Jinja2Templates(directory="app/templates")


@public_app.get("/api/status", response_model=list[schemas.ServiceStatusOut])
def status(db: Session = Depends(get_db)):
    return get_service_statuses(db)


@public_app.get("/api/history", response_model=list[schemas.CheckResultOut])
def history(
    service_ids: list[int] = Query([]),
    check_id: int | None = Query(None),
    minutes: int = Query(1440, ge=1, le=10080),
    limit: int = Query(100, ge=1, le=5000),
    before_id: int | None = Query(None),
    statuses: list[str] = Query([]),
    db: Session = Depends(get_db),
):
    return get_history(db, service_ids, check_id, minutes, limit, before_id, statuses)


@public_app.get("/api/notifications", response_model=list[schemas.ActiveIssueOut])
def notifications(db: Session = Depends(get_db)):
    return get_active_issues(db)


@public_app.get("/api/meta")
def meta(db: Session = Depends(get_db)):
    return get_meta(db)


@public_app.get("/api/dashboard-layouts/active", response_model=schemas.DashboardLayoutOut)
def active_layout(mobile: bool | None = Query(None), db: Session = Depends(get_db)):
    """Whichever layout is pinned in Dashboard Settings for this viewport -
    Desktop or Mobile, each pinned separately (see get_public_layout) - or
    the default, if that one isn't set. Its own `is_compact`/`is_mobile`
    flags are what tell the frontend how to render it, no separate settings
    fetch needed for that. `mobile` also still runs through
    resolve_layout_for_viewport as a safety net - so a phone visitor can
    never end up rendered the free-form desktop grid even if the Desktop
    pin somehow ended up pointed at a non-Mobile layout."""
    return resolve_layout_for_viewport(db, get_public_layout(db, mobile), mobile)


@public_app.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "public.html", {"page": "dashboard", "version": VERSION})


@public_app.get("/history", response_class=HTMLResponse)
def history_page(request: Request):
    return templates.TemplateResponse(request, "public.html", {"page": "history", "version": VERSION})


@public_app.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request):
    return templates.TemplateResponse(request, "public.html", {"page": "notifications", "version": VERSION})


@public_app.get("/healthz")
def healthz():
    return {"status": "ok"}
