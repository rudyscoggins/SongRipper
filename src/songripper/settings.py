# src/songripper/settings.py
import os
from pathlib import Path
from . import PACKAGE_TIME

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
NAS_PATH  = Path(os.getenv("NAS_PATH",  "/music"))
# Query string added to static assets for cache busting
CACHE_BUSTER = os.getenv("CACHE_BUSTER", PACKAGE_TIME.replace(":", "").replace("-", "").replace("+", ""))
