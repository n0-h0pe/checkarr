"""Sends alerts as a generic JSON POST, for anything with an incoming
webhook that isn't one of the named integrations - Home Assistant, n8n, ntfy,
your own script, whatever's listening. Blocking (httpx sync client), same
reasoning as email.py - called via asyncio.to_thread from alerting.py.
"""

import httpx

from .. import models
from ..security import resolve_secret


def send_webhook(channel: "models.NotificationChannel", subject: str, body: str) -> None:
    url = resolve_secret(channel.secret_env_var, channel.secret_encrypted)
    if not url:
        raise ValueError("Webhook channel has no URL configured")

    resp = httpx.post(url, json={"subject": subject, "message": body}, timeout=15)
    resp.raise_for_status()
