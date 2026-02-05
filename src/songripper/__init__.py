from __future__ import annotations
from pathlib import Path

_build_date_file = Path(__file__).parent / "build_date.txt"
if _build_date_file.exists():
    PACKAGE_TIME = _build_date_file.read_text().strip()
else:
    PACKAGE_TIME = "Unknown"

__all__ = ["PACKAGE_TIME"]
