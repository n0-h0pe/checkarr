from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _read(path: Path, default: str) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return default


VERSION = _read(_REPO_ROOT / "VERSION", "dev")
BUILD_DATE = _read(_REPO_ROOT / "BUILD_DATE", "unknown")
