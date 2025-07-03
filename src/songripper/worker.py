# src/songripper/worker.py
"""Public API exposing worker functionality via a service instance."""

from __future__ import annotations

import subprocess
import shutil
import threading
from pathlib import Path
from typing import Optional

from .services.ripper_service import RipperService, TrackUpdateError
from .models import Track

# Default service used by module-level wrappers
_service = RipperService()

# Re-export constants for backward compatibility
YT_BASE = RipperService.YT_BASE
TAG_LOCK = _service.tag_lock
ALBUM_ART_CACHE = _service.album_art_cache
ALBUM_LOCK = _service.album_lock
DATA_DIR = _service.data_dir
NAS_PATH = _service.nas_path
AUDIO_FORMAT = RipperService.AUDIO_FORMAT
AUDIO_EXT = RipperService.AUDIO_EXT


def _sync_service() -> None:
    """Synchronize global path settings with the service instance."""
    _service.data_dir = DATA_DIR
    _service.nas_path = NAS_PATH


def clean(text: str) -> str:
    _sync_service()
    return _service.clean(text)


def fetch_cover(
    artist: str, title: str, requests_mod: Optional[object] = None
) -> Optional[bytes]:
    _sync_service()
    return _service.fetch_cover(artist, title, requests_mod)


def fetch_thumbnail(
    url: str, requests_mod: Optional[object] = None
) -> Optional[bytes]:
    _sync_service()
    return _service.fetch_thumbnail(url, requests_mod)


def mp3_from_url(
    url: str, staging_dir: Path, lock: Optional[threading.Lock] = None
):
    _sync_service()
    return _service.mp3_from_url(
        url,
        staging_dir,
        lock,
        subprocess_mod=subprocess,
        fetch_cover=fetch_cover,
        fetch_thumbnail=fetch_thumbnail,
    )


def rip_playlist(pl_url: str) -> str:
    _sync_service()
    return _service.rip_playlist(
        pl_url,
        subprocess_mod=subprocess,
        shutil_mod=shutil,
        fetch_cover=fetch_cover,
        fetch_thumbnail=fetch_thumbnail,
        mp3_func=mp3_from_url,
    )


def staging_has_files() -> bool:
    _sync_service()
    return _service.staging_has_files()


def approve_all() -> None:
    _sync_service()
    _service.approve_all(shutil_mod=shutil)


def approve_selected(paths: list[str]) -> None:
    _sync_service()
    _service.approve_selected(paths, shutil_mod=shutil)


def approve_with_checks(input_func=input) -> None:
    """Approve all staged tracks with duplicate checks."""
    _sync_service()
    _service.approve_with_checks(shutil_mod=shutil, input_func=input_func)


def delete_staging() -> bool:
    _sync_service()
    return _service.delete_staging(shutil_mod=shutil)


def list_staged_tracks() -> list[Track]:
    _sync_service()
    return _service.list_staged_tracks()


def read_tags(filepath: str) -> dict[str, str]:
    _sync_service()
    return _service.read_tags(filepath)


def update_track(filepath: str, field: str, value: str) -> Path:
    _sync_service()
    return _service.update_track(filepath, field, value)


def update_album_art(filepath: str, data: bytes, mime: str = "image/jpeg") -> None:
    _sync_service()
    _service.update_album_art(filepath, data, mime)


def find_matching_tracks(filepath: str) -> list[str]:
    """Return library tracks with names similar to ``filepath``."""
    _sync_service()
    return [str(p) for p in _service.find_matching_tracks(filepath)]
