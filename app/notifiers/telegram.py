"""Sends alerts via a Telegram bot. Blocking (httpx sync client), same
reasoning as email.py - called via asyncio.to_thread from alerting.py.
"""

import httpx

from .. import models
from ..security import resolve_secret


def send_telegram(channel: "models.NotificationChannel", subject: str, body: str) -> None:
    bot_token = resolve_secret(channel.secret_env_var, channel.secret_encrypted)
    if not bot_token:
        raise ValueError("Telegram channel has no bot token configured")
    chat_id = (channel.config or {}).get("chat_id") or ""
    if not str(chat_id).strip():
        raise ValueError("Telegram channel has no chat ID configured")

    resp = httpx.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": f"{subject}\n\n{body}"},
        timeout=15,
    )
    resp.raise_for_status()
