import os
import time

from .base import STATUS_FAIL, STATUS_OK, STATUS_WARN, CheckOutcome


async def check_filesystem_path(config: dict) -> CheckOutcome:
    """Direct filesystem probe, for when the health checker container has the

    same media volumes bind-mounted as Radarr/Sonarr. A mount point that
    failed to mount typically still exists as an empty directory, so this
    checks both existence and a minimum number of entries.

    Prefer the arr_root_folder API check where possible - it reflects what
    Radarr/Sonarr itself sees and needs no extra volume mounts. Use this for
    paths outside the *arr apps (e.g. a raw NAS mount) or as a belt-and-braces
    second opinion.
    """
    path = config.get("path")
    min_entries = config.get("min_entries", 1)
    start = time.perf_counter()

    if not path:
        return CheckOutcome(STATUS_FAIL, "No path configured for filesystem check", 0)

    if not os.path.exists(path):
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"Path does not exist: {path}", elapsed)

    if not os.path.isdir(path):
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_WARN, f"Path exists but is not a directory: {path}", elapsed)

    try:
        entries = os.listdir(path)
    except OSError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"Could not list directory {path}: {exc}", elapsed)

    elapsed = (time.perf_counter() - start) * 1000
    if len(entries) < min_entries:
        return CheckOutcome(
            STATUS_FAIL,
            f"{path} has only {len(entries)} entrie(s), expected at least {min_entries} "
            "- possible unmounted/failed drive",
            elapsed,
        )
    return CheckOutcome(STATUS_OK, f"{path} accessible with {len(entries)} entrie(s)", elapsed)
