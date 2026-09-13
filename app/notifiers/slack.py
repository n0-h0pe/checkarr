"""Sends alerts via a Slack incoming webhook. Blocking (httpx sync client),
same reasoning as email.py - called via asyncio.to_thread from alerting.py.
"""

import httpx

from .. import models
from ..security import resolve_secret


def send_slack(channel: "models.NotificationChannel", subject: str, body: str) -> None:
    webhook_url = resolve_secret(channel.secret_env_var, channel.secret_encrypted)
    if not webhook_url:
        raise ValueError("Slack channel has no webhook URL configured")

    resp = httpx.post(webhook_url, json={"text": f"*{subject}*\n{body}"}, timeout=15)
    resp.raise_for_status()
