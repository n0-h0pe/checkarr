"""Process entrypoint: runs the main admin app and (optionally) the
restricted public-dashboard app as two uvicorn servers sharing one event
loop, so `docker stop` still gets a clean, coordinated shutdown of both.
"""

import asyncio
import logging
import signal

import uvicorn

from .config import settings

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("checkarr.run")


def _build_server(app, port: int) -> uvicorn.Server:
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level=settings.log_level.lower())
    server = uvicorn.Server(config)
    # We install one set of signal handlers below covering every server
    # instead - letting each Server.serve() install its own would mean the
    # last one registered silently wins and the others never see SIGTERM.
    server.install_signal_handlers = lambda: None
    return server


async def _run() -> None:
    from .main import app as main_app

    servers = [_build_server(main_app, settings.port)]
    logger.info("Admin app will listen on port %s", settings.port)

    if settings.public_dashboard_enabled:
        from .public import public_app

        servers.append(_build_server(public_app, settings.public_port))
        logger.info("Public dashboard enabled on port %s", settings.public_port)
    else:
        logger.info("Public dashboard disabled (set HC_PUBLIC_DASHBOARD_ENABLED=true to enable)")

    loop = asyncio.get_running_loop()

    def _shutdown():
        for s in servers:
            s.should_exit = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            pass  # e.g. Windows - fine for local dev, Docker/Linux is what matters here

    await asyncio.gather(*(s.serve() for s in servers))


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
