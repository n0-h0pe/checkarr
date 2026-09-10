import asyncio
import ftplib
import time

from .base import STATUS_FAIL, STATUS_OK, CheckOutcome


def _ftp_list_entries(
    host: str, port: int, username: str | None, password: str | None, path: str, use_tls: bool
) -> list[str]:
    """Blocking - ftplib has no async API, so this runs off the event loop
    via asyncio.to_thread in check_ftp_path below."""
    ftp = ftplib.FTP_TLS(timeout=15) if use_tls else ftplib.FTP(timeout=15)
    try:
        ftp.connect(host, port)
        ftp.login(username or "anonymous", password or "")
        if use_tls:
            ftp.prot_p()  # encrypt the data channel too, not just the login
        return ftp.nlst(path) if path else ftp.nlst()
    finally:
        try:
            ftp.quit()
        except Exception:  # noqa: BLE001 - best-effort clean close, connection may already be dead
            ftp.close()


async def check_ftp_path(config: dict) -> CheckOutcome:
    """The FTP equivalent of filesystem_path: confirms a directory exists
    and has a minimum number of entries, but over FTP/FTPS instead of a bind
    mount - for a NAS or share exposed over FTP rather than one this
    container has direct filesystem access to.
    """
    host = (config.get("host") or "").strip()
    if not host:
        return CheckOutcome(STATUS_FAIL, "No FTP host configured", 0)

    port = int(config.get("port") or 21)
    username = config.get("username")
    password = config.get("password")
    path = (config.get("path") or "").strip()
    min_entries = config.get("min_entries", 1)
    use_tls = bool(config.get("use_tls"))
    label = f"ftp{'s' if use_tls else ''}://{host}:{port}{path or '/'}"

    start = time.perf_counter()
    try:
        entries = await asyncio.to_thread(_ftp_list_entries, host, port, username, password, path, use_tls)
    except ftplib.error_perm as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"{label}: permission or path error - {exc}", elapsed)
    except ftplib.all_errors as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"Could not reach {label}: {exc}", elapsed)
    elapsed = (time.perf_counter() - start) * 1000

    if len(entries) < min_entries:
        return CheckOutcome(
            STATUS_FAIL,
            f"{label} has only {len(entries)} entrie(s), expected at least {min_entries} "
            "- possible unmounted/failed drive",
            elapsed,
        )
    return CheckOutcome(STATUS_OK, f"{label} accessible with {len(entries)} entrie(s)", elapsed)
