from __future__ import annotations

from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

PACKAGE_TIME = datetime.fromtimestamp(
    Path(__file__).stat().st_mtime,
    tz=ZoneInfo("America/Chicago"),
).isoformat(timespec="seconds")

__all__ = ["PACKAGE_TIME"]
