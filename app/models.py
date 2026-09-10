from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)  # radarr/sonarr/prowlarr/plex/jellyfin/generic
    local_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    remote_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    check_both_targets: Mapped[bool] = mapped_column(Boolean, default=False)
    # Plaintext (not sensitive - usernames aren't secrets) login name for
    # services that authenticate with username+password/secret rather than
    # a bearer API key (qBittorrent, rTorrent via HTTP Basic Auth). The
    # paired secret always lives in api_key_encrypted regardless of what
    # it semantically is for a given service type (API key / token /
    # password) - one encrypted slot, reused.
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    verify_ssl: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    poll_interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    checks: Mapped[list["CheckDefinition"]] = relationship(
        back_populates="service", cascade="all, delete-orphan"
    )
    results: Mapped[list["CheckResult"]] = relationship(
        back_populates="service", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="service", cascade="all, delete-orphan"
    )

    def has_api_key(self) -> bool:
        return bool(self.api_key_encrypted)

    def get_targets(self) -> list[tuple[str, str]]:
        """(label, url) pairs for whichever of local/remote address are set."""
        targets: list[tuple[str, str]] = []
        if self.local_url:
            targets.append(("local", self.local_url.rstrip("/")))
        if self.remote_url:
            targets.append(("remote", self.remote_url.rstrip("/")))
        return targets


class CheckDefinition(Base):
    __tablename__ = "check_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    service: Mapped["Service"] = relationship(back_populates="checks")


class CheckResult(Base):
    __tablename__ = "check_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False)
    check_id: Mapped[int | None] = mapped_column(ForeignKey("check_definitions.id"), nullable=True)
    check_name: Mapped[str] = mapped_column(String(120))
    check_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(10))  # ok / warn / fail
    message: Mapped[str] = mapped_column(Text, default="")
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    service: Mapped["Service"] = relationship(back_populates="results")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(50))  # e.g. radarr_health
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(10))  # ok/notice/warning/error
    message: Mapped[str] = mapped_column(Text)
    wiki_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    service: Mapped["Service"] = relationship(back_populates="notifications")


class DashboardLayout(Base):
    """A named, saveable arrangement of dashboard card sizes. `sizes` maps
    service id (as a string, since JSON object keys must be strings) to
    {"w": int, "h": int} in grid units. Exactly one row has is_active=True
    at a time - that's what the dashboard (admin and public) renders."""

    __tablename__ = "dashboard_layouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sizes: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
