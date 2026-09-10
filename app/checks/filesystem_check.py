import os
import time

from .base import STATUS_FAIL, STATUS_OK, STATUS_WARN, CheckOutcome


async def check_filesystem_path(config: dict) -> CheckOutcome:
    """Direct filesystem probe, for when the health checker container has the

    same media volumes bind-mounted as Radarr/Sonarr. A mount point that
    failed to mount typically still exists as an empty directory, so this
    checks both existence and a minimum number of entries.

    The path an app like Radarr sees for a folder is almost never the same
    path HealthChecker sees for the same underlying host directory (each
    container maps its own volumes independently, and they can coincidentally
    collide - e.g. a torrent client's /data meaning something totally
    different to Radarr's /data). So the *functional* check always runs
    against `healthchecker_path`; `service_path` is optional and purely for
    a human-readable label tying the two together.

    Prefer the arr_root_folder API check where possible - it reflects what
    Radarr/Sonarr itself sees and needs no extra volume mounts. Use this for
    paths outside the *arr apps (e.g. a raw NAS mount) or as a belt-and-braces
    second opinion.
    """
    path = config.get("healthchecker_path") or config.get("path")  # "path" = pre-split config
    service_path = config.get("service_path")
    min_entries = config.get("min_entries", 1)
    label = f"{path} (maps to {service_path} in the target app)" if service_path else path
    start = time.perf_counter()

    if not path:
        return CheckOutcome(STATUS_FAIL, "No 'Path in HealthChecker container' configured", 0)

    if not os.path.exists(path):
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"Path does not exist: {label}", elapsed)

    if not os.path.isdir(path):
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_WARN, f"Path exists but is not a directory: {label}", elapsed)

    try:
        entries = os.listdir(path)
    except OSError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return CheckOutcome(STATUS_FAIL, f"Could not list directory {label}: {exc}", elapsed)

    elapsed = (time.perf_counter() - start) * 1000
    if len(entries) < min_entries:
        return CheckOutcome(
            STATUS_FAIL,
            f"{label} has only {len(entries)} entrie(s), expected at least {min_entries} "
            "- possible unmounted/failed drive",
            elapsed,
        )
    return CheckOutcome(STATUS_OK, f"{label} accessible with {len(entries)} entrie(s)", elapsed)
