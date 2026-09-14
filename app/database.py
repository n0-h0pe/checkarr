import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

logger = logging.getLogger("checkarr.database")

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from . import models  # noqa: F401  (ensure models are registered)

    Base.metadata.create_all(bind=engine)
    _run_migrations()
    _migrate_dashboard_layout_cards()
    _ensure_default_layouts()

    from .queries import (
        get_or_create_all_services_group,
        get_or_create_dashboard_settings,
        get_or_create_log_pruning_settings,
        get_or_create_self_monitoring_state,
        get_or_create_ui_settings,
    )

    db = SessionLocal()
    try:
        get_or_create_all_services_group(db)
        get_or_create_log_pruning_settings(db)
        get_or_create_dashboard_settings(db)
        get_or_create_self_monitoring_state(db)
        get_or_create_ui_settings(db)
    finally:
        db.close()


def _table_columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()}


def _run_migrations() -> None:
    """Lightweight in-place schema patches for upgrades of an existing DB.

    No Alembic here - this project's schema is simple enough that additive,
    idempotent ALTER TABLEs cover it. Columns the ORM no longer declares are
    generally left in place (harmless - the ORM just ignores them), except
    where an old NOT NULL constraint would reject new rows, which is worth
    actually dropping.
    """
    with engine.begin() as conn:
        service_cols = _table_columns(conn, "services")
        if "local_url" not in service_cols:
            conn.exec_driver_sql("ALTER TABLE services ADD COLUMN local_url VARCHAR(500)")
            service_cols.add("local_url")
        if "remote_url" not in service_cols:
            conn.exec_driver_sql("ALTER TABLE services ADD COLUMN remote_url VARCHAR(500)")
        if "base_url" in service_cols:
            # Pre-existing single-URL services: carry the old value forward
            # as their "local" address so they keep working unchanged.
            conn.exec_driver_sql(
                "UPDATE services SET local_url = base_url WHERE local_url IS NULL AND base_url IS NOT NULL"
            )
            # base_url was NOT NULL - leaving it in place would reject every
            # future insert (the ORM no longer supplies it). Drop it outright
            # (needs SQLite 3.35+, true for any Python 3.9+ build) now that
            # its data has been copied forward.
            try:
                conn.exec_driver_sql("ALTER TABLE services DROP COLUMN base_url")
            except Exception:
                logger.exception(
                    "Could not drop legacy services.base_url column (old SQLite?) - "
                    "inserting new services will fail until this is resolved manually."
                )

        if "check_both_targets" not in service_cols:
            conn.exec_driver_sql(
                "ALTER TABLE services ADD COLUMN check_both_targets BOOLEAN DEFAULT 0"
            )
        if "username" not in service_cols:
            conn.exec_driver_sql("ALTER TABLE services ADD COLUMN username VARCHAR(255)")
        if "jellyfin_admin_password_encrypted" not in service_cols:
            conn.exec_driver_sql("ALTER TABLE services ADD COLUMN jellyfin_admin_password_encrypted TEXT")
        if "api_key_env_var" not in service_cols:
            conn.exec_driver_sql("ALTER TABLE services ADD COLUMN api_key_env_var VARCHAR(255)")
        if "jellyfin_admin_password_env_var" not in service_cols:
            conn.exec_driver_sql("ALTER TABLE services ADD COLUMN jellyfin_admin_password_env_var VARCHAR(255)")
        if "icon_type" not in service_cols:
            conn.exec_driver_sql("ALTER TABLE services ADD COLUMN icon_type VARCHAR(20)")
        if "icon_value" not in service_cols:
            conn.exec_driver_sql("ALTER TABLE services ADD COLUMN icon_value VARCHAR(255)")
        if "verify_ssl" in service_cols:
            # The per-service "Verify SSL certificates" toggle is gone - the
            # new dedicated ssl_certificate check now owns cert validation,
            # and ordinary checks no longer enforce cert trust at all (see
            # poller.py). Same drop-if-possible pattern as legacy base_url
            # above; harmless to leave in place on an old SQLite that can't
            # drop columns; the ORM just no longer reads or writes it.
            try:
                conn.exec_driver_sql("ALTER TABLE services DROP COLUMN verify_ssl")
            except Exception:
                logger.exception("Could not drop legacy services.verify_ssl column (old SQLite?) - harmless, it's just unused now.")

        check_cols = _table_columns(conn, "check_definitions")
        if "interval_seconds" not in check_cols:
            conn.exec_driver_sql("ALTER TABLE check_definitions ADD COLUMN interval_seconds INTEGER")
        if "sort_order" not in check_cols:
            conn.exec_driver_sql("ALTER TABLE check_definitions ADD COLUMN sort_order INTEGER DEFAULT 0")

        result_cols = _table_columns(conn, "check_results")
        if "in_sdt" not in result_cols:
            conn.exec_driver_sql("ALTER TABLE check_results ADD COLUMN in_sdt BOOLEAN DEFAULT 0")
        if "suppressed_by_threshold" not in result_cols:
            conn.exec_driver_sql("ALTER TABLE check_results ADD COLUMN suppressed_by_threshold BOOLEAN DEFAULT 0")

        layout_cols = _table_columns(conn, "dashboard_layouts")
        if "columns" not in layout_cols:
            conn.exec_driver_sql("ALTER TABLE dashboard_layouts ADD COLUMN columns INTEGER")
        if "card_service_ids" not in layout_cols:
            conn.exec_driver_sql("ALTER TABLE dashboard_layouts ADD COLUMN card_service_ids TEXT")
        if "is_default" not in layout_cols:
            conn.exec_driver_sql("ALTER TABLE dashboard_layouts ADD COLUMN is_default BOOLEAN DEFAULT 0")
        if "is_compact" not in layout_cols:
            conn.exec_driver_sql("ALTER TABLE dashboard_layouts ADD COLUMN is_compact BOOLEAN DEFAULT 0")
        if "is_mobile" not in layout_cols:
            conn.exec_driver_sql("ALTER TABLE dashboard_layouts ADD COLUMN is_mobile BOOLEAN DEFAULT 0")
        if "theme" not in layout_cols:
            conn.exec_driver_sql("ALTER TABLE dashboard_layouts ADD COLUMN theme VARCHAR(20)")

        downtime_cols = _table_columns(conn, "downtime_schedules")
        if "is_instant" not in downtime_cols:
            conn.exec_driver_sql("ALTER TABLE downtime_schedules ADD COLUMN is_instant BOOLEAN DEFAULT 0")

        channel_cols = _table_columns(conn, "notification_channels")
        if "secret_env_var" not in channel_cols:
            conn.exec_driver_sql("ALTER TABLE notification_channels ADD COLUMN secret_env_var VARCHAR(255)")

        # dashboard_settings is guaranteed to exist by create_all() above by
        # the time this runs. An install that already ran an earlier build
        # of it briefly had `public_compact` (a flat force-compact flag),
        # then `public_require_compact` (a restriction on which layouts
        # could be pinned - compactness lives on the layout itself, see
        # DashboardLayout.is_compact above), before the public dashboard's
        # Desktop/Mobile pins were split into two separate columns and that
        # restriction was dropped as redundant. Both old columns, if
        # present, are simply left in place unused, same as every other
        # renamed/retired column in this function.
        settings_cols = _table_columns(conn, "dashboard_settings")
        if "public_require_compact" not in settings_cols:
            conn.exec_driver_sql("ALTER TABLE dashboard_settings ADD COLUMN public_require_compact BOOLEAN DEFAULT 0")
        if "public_layout_id_mobile" not in settings_cols:
            conn.exec_driver_sql("ALTER TABLE dashboard_settings ADD COLUMN public_layout_id_mobile INTEGER")
        if "uptime_bar_count" not in settings_cols:
            conn.exec_driver_sql("ALTER TABLE dashboard_settings ADD COLUMN uptime_bar_count INTEGER DEFAULT 20")
        if "public_theme_override" not in settings_cols:
            conn.exec_driver_sql("ALTER TABLE dashboard_settings ADD COLUMN public_theme_override VARCHAR(20)")


def _migrate_dashboard_layout_cards() -> None:
    """One-time backfill for dashboard_layouts.card_service_ids/is_default,
    added when per-layout card add/remove was introduced. Before this,
    every layout implicitly showed every service - preserve that as each
    existing layout's explicit starting set, and designate whichever layout
    was created first (the oldest id - reliably the one auto-seeded by
    get_or_create_active_layout, since no custom layout can exist before
    that) as the protected "All Services" layout, renaming it from its old
    default name if the user hasn't already renamed it themselves."""
    from . import models

    db = SessionLocal()
    try:
        layouts = db.query(models.DashboardLayout).order_by(models.DashboardLayout.id).all()
        if not layouts:
            return
        changed = False
        if not any(layout.is_default for layout in layouts):
            first = layouts[0]
            first.is_default = True
            if first.name == "Default":
                first.name = "All Services"
            changed = True
        all_service_ids = [sid for (sid,) in db.query(models.Service.id).all()]
        for layout in layouts:
            if layout.card_service_ids is None:
                layout.card_service_ids = [] if layout.is_default else list(all_service_ids)
                changed = True
        if changed:
            db.commit()
    finally:
        db.close()


def _ensure_default_layouts() -> None:
    """Guarantees every one of the four layout pools - (is_mobile,
    is_compact) each True/False, i.e. Desktop / Desktop-Compact / Mobile /
    Mobile-Compact - has its own protected "All Services" layout, run on
    every startup (idempotent: a pool that already has one is left alone).

    Before is_mobile existed, only the Desktop pool was guaranteed a
    default (seeded by get_or_create_active_layout, or backfilled onto the
    oldest layout by _migrate_dashboard_layout_cards above) - the other
    three pools would otherwise start out empty, and ensureActiveLayout's
    (common.js) viewport-driven fallback needs somewhere to land in every
    pool, not just the one an existing install happened to already have."""
    from . import models

    db = SessionLocal()
    try:
        changed = False
        for is_mobile in (False, True):
            for is_compact in (False, True):
                exists = (
                    db.query(models.DashboardLayout)
                    .filter_by(is_default=True, is_mobile=is_mobile, is_compact=is_compact)
                    .first()
                )
                if exists:
                    continue
                db.add(
                    models.DashboardLayout(
                        name="All Services",
                        sizes={},
                        card_service_ids=[],
                        is_default=True,
                        is_compact=is_compact,
                        is_mobile=is_mobile,
                        theme="dark",
                    )
                )
                changed = True
        if changed:
            db.commit()
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
