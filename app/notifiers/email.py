"""Sends alerts via SMTP. Blocking (smtplib has no async API) - called via
asyncio.to_thread from alerting.py, same reasoning as the blocking I/O in
checks/ftp_check.py.
"""

import smtplib
from email.message import EmailMessage

from .. import models
from ..security import decrypt_secret

# Port 465 is "implicit TLS" (SMTPS) - the server expects a TLS handshake as
# the very first bytes on the connection, not a plaintext SMTP greeting
# followed by STARTTLS. Connecting with plain SMTP() and then calling
# starttls() against a port-465 server gets the connection dropped
# immediately (smtplib surfaces this as "Connection unexpectedly closed"),
# which is what this always did regardless of port before this check existed.
_IMPLICIT_TLS_PORTS = {465}


def send_email(channel: "models.NotificationChannel", subject: str, body: str) -> None:
    config = channel.config or {}
    host = (config.get("smtp_host") or "").strip()
    if not host:
        raise ValueError("Email channel has no SMTP host configured")
    port = int(config.get("smtp_port") or 587)
    username = (config.get("smtp_username") or "").strip() or None
    password = decrypt_secret(channel.secret_encrypted)
    use_tls = bool(config.get("use_tls", True))
    from_addr = (config.get("from_address") or "").strip() or username or "checkarr@localhost"
    to_addrs = [a.strip() for a in (config.get("to_addresses") or "").split(",") if a.strip()]
    if not to_addrs:
        raise ValueError("Email channel has no recipient address(es) configured")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg.set_content(body)

    if port in _IMPLICIT_TLS_PORTS:
        with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
            if username and password:
                smtp.login(username, password)
            smtp.send_message(msg)
        return

    with smtplib.SMTP(host, port, timeout=15) as smtp:
        if use_tls:
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(msg)
