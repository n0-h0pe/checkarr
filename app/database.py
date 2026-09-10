import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

logger = logging.getLogger("healthchecker.database")

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

        check_cols = _table_columns(conn, "check_definitions")
        if "interval_seconds" not in check_cols:
            conn.exec_driver_sql("ALTER TABLE check_definitions ADD COLUMN interval_seconds INTEGER")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
