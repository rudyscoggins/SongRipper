# src/songripper/settings.py
import os
from pathlib import Path
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
NAS_PATH  = Path(os.getenv("NAS_PATH",  "/music"))
