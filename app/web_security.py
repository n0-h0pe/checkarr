"""HTTP-level protections shared by both apps (main.py, public.py).

Cross-site writes: the admin API has no login by default and, even with
HTTP Basic Auth on, a browser re-sends cached credentials on its own - so
without this, any web page the admin happened to visit could quietly POST
to it (a form or a body-less fetch needs no CORS preflight): prune history,
fire test notifications, upload files. Every state-changing request a
browser makes from somewhere other than this app's own pages is refused.
Modern browsers say where a request came from in Sec-Fetch-Site, which
survives any reverse proxy untouched; for one that doesn't send it, the
Origin header has to match the Host (or X-Forwarded-Host) instead. Clients
that send neither - curl, scripts - aren't browsers and aren't affected.

Headers: nosniff and a same-origin referrer policy everywhere, plus a
locked-down CSP on uploaded icons - an uploaded SVG is only ever drawn via
<img> (where scripts never run), but opened directly by its URL it would
otherwise be a page on this origin that can run its own scripts.
"""

from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_ICON_CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; sandbox"


def is_cross_site_write(method: str, headers: Headers) -> bool:
    if method in _SAFE_METHODS:
        return False
    site = headers.get("sec-fetch-site")
    if site is not None:
        return site not in ("same-origin", "none")
    origin = headers.get("origin")
    if not origin:
        return False
    return urlsplit(origin).netloc not in {headers.get("host"), headers.get("x-forwarded-host")}


class SecurityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        if is_cross_site_write(scope["method"], Headers(scope=scope)):
            response = JSONResponse({"detail": "Cross-site request refused"}, status_code=403)
            return await response(scope, receive, send)

        is_icon = scope["path"].startswith("/custom-icons/")

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("Referrer-Policy", "same-origin")
                if is_icon:
                    headers["Content-Security-Policy"] = _ICON_CSP
            await send(message)

        await self.app(scope, receive, send_with_headers)
