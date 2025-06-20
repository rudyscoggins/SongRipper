from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

PACKAGE_TIME = datetime.fromtimestamp(
    Path(__file__).stat().st_mtime,
    timezone.utc,
).isoformat(timespec="seconds")

__all__ = ["PACKAGE_TIME"]
