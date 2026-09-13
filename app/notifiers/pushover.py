"""Sends alerts via Pushover. Blocking (httpx sync client), same reasoning
as email.py - called via asyncio.to_thread from alerting.py.
"""

import httpx

from .. import models
from ..security import resolve_secret


def send_pushover(channel: "models.NotificationChannel", subject: str, body: str) -> None:
    app_token = resolve_secret(channel.secret_env_var, channel.secret_encrypted)
    if not app_token:
        raise ValueError("Pushover channel has no application token configured")
    user_key = (channel.config or {}).get("user_key") or ""
    if not str(user_key).strip():
        raise ValueError("Pushover channel has no user key configured")

    resp = httpx.post(
        "https://api.pushover.net/1/messages.json",
        data={"token": app_token, "user": user_key, "title": subject, "message": body},
        timeout=15,
    )
    resp.raise_for_status()
