"""Delivers alerts as a native OS notification in any admin browser tab
that's currently open with a live connection, over Server-Sent Events (see
the /api/notification-channels/stream route in routers/notification_channels.py,
and the EventSource the frontend opens against it in app.js).

There's no queue, retry, or persistence here - this is genuinely best-effort,
the same way a phone that's asleep just doesn't see a push notification. If
no admin tab is connected when an alert fires, it's simply missed; every
other enabled channel still gets it as normal. That's also why this is the
one notifier not called via asyncio.to_thread from alerting.py's perspective
in the way the others are - it still runs on that same worker thread (send_via_channel
doesn't special-case it), but the actual handoff to any connected tab happens
via call_soon_threadsafe below, since asyncio.Queue isn't safe to touch
directly from a thread other than the one running its event loop.
"""

import asyncio

from .. import models

# Every currently-connected admin tab gets its own queue (added in
# subscribe() when its EventSource connects, removed in unsubscribe() when
# it disconnects). Plain process memory, not persisted - there's nothing
# meaningful to survive a restart, a reconnecting tab just subscribes again.
_subscribers: set[asyncio.Queue] = set()

# Captured from the most recent subscribe() call, which always runs inside
# the admin app's own event loop (it's the coroutine backing the SSE route).
# send_browser_notification runs on a worker thread instead (see module
# docstring), so it can't safely call queue.put_nowait directly - it needs
# call_soon_threadsafe to hand the item back to that loop.
_loop: asyncio.AbstractEventLoop | None = None


def subscribe() -> asyncio.Queue:
    global _loop
    _loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.add(queue)
    return queue


def unsubscribe(queue: asyncio.Queue) -> None:
    _subscribers.discard(queue)


def send_browser_notification(channel: "models.NotificationChannel", subject: str, body: str) -> None:
    if not _subscribers or _loop is None:
        raise ValueError("No browser tab is currently connected to receive this notification")
    payload = {"subject": subject, "body": body}
    for queue in list(_subscribers):
        _loop.call_soon_threadsafe(queue.put_nowait, payload)
