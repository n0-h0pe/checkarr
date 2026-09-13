"""Sends alerts via Pushbullet. Blocking (httpx sync client), same reasoning
as email.py - called via asyncio.to_thread from alerting.py.
"""

import httpx

from .. import models
from ..security import resolve_secret


def send_pushbullet(channel: "models.NotificationChannel", subject: str, body: str) -> None:
    access_token = resolve_secret(channel.secret_env_var, channel.secret_encrypted)
    if not access_token:
        raise ValueError("Pushbullet channel has no access token configured")

    resp = httpx.post(
        "https://api.pushbullet.com/v2/pushes",
        headers={"Access-Token": access_token},
        json={"type": "note", "title": subject, "body": body},
        timeout=15,
    )
    resp.raise_for_status()
