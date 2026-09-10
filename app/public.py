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
from .database import get_db
from .queries import get_history, get_notifications, get_service_statuses
from .routers.meta import get_meta

public_app = FastAPI(title="Media Estate Status", docs_url=None, redoc_url=None, openapi_url=None)
public_app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@public_app.get("/api/status", response_model=list[schemas.ServiceStatusOut])
def status(db: Session = Depends(get_db)):
    return get_service_statuses(db)


@public_app.get("/api/history", response_model=list[schemas.CheckResultOut])
def history(
    service_id: int = Query(...),
    check_id: int | None = Query(None),
    hours: int = Query(24, ge=1, le=24 * 30),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    return get_history(db, service_id, check_id, hours, limit)


@public_app.get("/api/notifications", response_model=list[schemas.NotificationOut])
def notifications(
    active_only: bool = Query(True),
    service_id: int | None = Query(None),
    limit: int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    return get_notifications(db, active_only, service_id, limit)


@public_app.get("/api/meta")
def meta():
    return get_meta()


@public_app.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "public.html", {"page": "dashboard"})


@public_app.get("/history", response_class=HTMLResponse)
def history_page(request: Request):
    return templates.TemplateResponse(request, "public.html", {"page": "history"})


@public_app.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request):
    return templates.TemplateResponse(request, "public.html", {"page": "notifications"})


@public_app.get("/healthz")
def healthz():
    return {"status": "ok"}
