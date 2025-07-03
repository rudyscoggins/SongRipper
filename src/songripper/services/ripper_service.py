# src/songripper/services/ripper_service.py
"""Core service operations for ripping and managing tracks."""

from __future__ import annotations

import concurrent.futures
import json
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

from ..models import Track
from ..settings import DATA_DIR, NAS_PATH


class TrackUpdateError(Exception):
    """Raised when an update operation cannot be completed."""


class RipperService:
    """Service encapsulating all ripping and file management operations."""

    YT_BASE = ["yt-dlp", "--quiet", "--no-warnings"]
    AUDIO_FORMAT = "m4a"
    AUDIO_EXT = ".m4a"

    def __init__(self, data_dir: Path = DATA_DIR, nas_path: Path = NAS_PATH) -> None:
        self.data_dir = data_dir
        self.nas_path = nas_path
        self.tag_lock = threading.Lock()
        self.album_lock = threading.Lock()
        self.album_art_cache: dict[tuple[str, str], bytes | None] = {}

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    @staticmethod
    def clean(text: str) -> str:
        """Return ``text`` safe for use in file paths."""
        text = re.sub(r'[\\/*?:"<>|]', " ", text)
        emoji_re = re.compile(
            "["
            "\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF"
            "\U00002700-\U000027BF"
            "\U0001F900-\U0001F9FF"
            "\U0001FA70-\U0001FAFF"
            "\U00002600-\U000026FF"
            "\U000024C2-\U0001F251"
            "]",
            flags=re.UNICODE,
        )
        text = emoji_re.sub(" ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def fetch_cover(
        self, artist: str, title: str, requests_mod: Optional[object] = None
    ) -> Optional[bytes]:
        """Return album art from iTunes if available."""
        try:
            if requests_mod is None:
                try:
                    import requests as requests_mod  # type: ignore
                except Exception:
                    return None
            res = requests_mod.get(
                "https://itunes.apple.com/search",
                params={"term": f"{artist} {title}", "entity": "song", "limit": 1},
                timeout=10,
            )
            res.raise_for_status()
            q = res.json()
            url = q["results"][0]["artworkUrl100"].replace("100x100bb", "600x600bb")
            cover = requests_mod.get(url, timeout=10)
            cover.raise_for_status()
            return cover.content
        except Exception:
            return None

    def fetch_thumbnail(
        self, url: str, requests_mod: Optional[object] = None
    ) -> Optional[bytes]:
        """Return thumbnail image bytes from ``url`` if possible."""
        try:
            if requests_mod is None:
                try:
                    import requests as requests_mod  # type: ignore
                except Exception:
                    return None
            res = requests_mod.get(url, timeout=10)
            res.raise_for_status()
            return res.content
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Core ripping and file management methods
    # ------------------------------------------------------------------
    def mp3_from_url(
        self,
        url: str,
        staging_dir: Path,
        lock: threading.Lock | None = None,
        *,
        subprocess_mod=subprocess,
        fetch_cover=None,
        fetch_thumbnail=None,
    ) -> tuple[str, str, Path]:
        """Download ``url`` to ``staging_dir`` and tag the resulting audio."""

        lock = lock or self.tag_lock
        fetch_cover = fetch_cover or self.fetch_cover
        fetch_thumbnail = fetch_thumbnail or self.fetch_thumbnail

        meta = json.loads(
            subprocess_mod.check_output(self.YT_BASE + ["-J", "--no-playlist", url], text=True)
        )
        artist = self.clean(meta.get("artist") or meta["uploader"])
        title = self.clean(meta.get("track") or meta["title"])
        album = self.clean(meta.get("album") or meta.get("playlist") or "Singles")

        if not artist:
            artist = "Unknown Artist"
        if not album:
            album = "Unknown Album"
        if not title:
            title = "Unknown Title"
        track_no = meta.get("track_number")
        prefix = ""
        if track_no:
            try:
                num = int(str(track_no).split("/", 1)[0])
                prefix = f"{num:02d} "
            except ValueError:
                prefix = ""

        outtmpl = str(staging_dir / f"{prefix}{title}.%(ext)s")
        subprocess_mod.run(
            self.YT_BASE
            + ["-x", "--audio-format", self.AUDIO_FORMAT, "-o", outtmpl, url],
            check=True,
        )
        mp3_path = staging_dir / f"{prefix}{title}{self.AUDIO_EXT}"

        # Trim any long silence (>5s) at the start or end of the track.
        tmp_trim = mp3_path.with_name(mp3_path.stem + "_trim" + self.AUDIO_EXT)
        trim_cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(mp3_path),
            "-af",
            (
                "silenceremove="
                "start_periods=1:start_duration=5:start_threshold=-50dB:"\
                "stop_periods=1:stop_duration=5:stop_threshold=-50dB"
            ),
            str(tmp_trim),
        ]
        try:
            subprocess_mod.run(trim_cmd, check=True)
            mp3_path.unlink()
            tmp_trim.rename(mp3_path)
        except Exception:
            if tmp_trim.exists():
                tmp_trim.unlink()

        try:
            from mutagen.easymp4 import EasyMP4
            from mutagen.mp4 import MP4, MP4Cover
        except Exception:
            EasyMP4 = MP4 = MP4Cover = None  # type: ignore

        cover = None
        if EasyMP4 is not None:
            with lock:
                audio = EasyMP4(mp3_path)
                audio["artist"], audio["title"], audio["album"] = [artist], [title], [album]
                if prefix:
                    audio["tracknumber"] = [prefix.strip()]
                audio.save()
            key = (artist, album)
            with self.album_lock:
                cover = self.album_art_cache.get(key)
            if cover is None:
                cover = fetch_cover(artist, title)
                if cover is None:
                    thumb_url = meta.get("thumbnail")
                    if thumb_url is None:
                        thumbs = meta.get("thumbnails")
                        if isinstance(thumbs, list) and thumbs:
                            first = thumbs[0]
                            if isinstance(first, dict):
                                thumb_url = first.get("url")
                            else:
                                thumb_url = first
                    if thumb_url:
                        cover = fetch_thumbnail(thumb_url)
                with self.album_lock:
                    self.album_art_cache[key] = cover
            if cover and MP4 is not None:
                with lock:
                    tags = MP4(mp3_path)
                    tags["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_JPEG)]
                    tags.save()
        return artist, album, mp3_path

    def rip_playlist(
        self,
        pl_url: str,
        *,
        subprocess_mod=subprocess,
        shutil_mod=shutil,
        fetch_cover=None,
        fetch_thumbnail=None,
        mp3_func=None,
    ) -> str:
        """Rip a playlist or single video URL into the staging directory."""
        staging = self.data_dir / "staging"
        staging.mkdir(parents=True, exist_ok=True)
        with self.album_lock:
            self.album_art_cache.clear()

        info = json.loads(
            subprocess_mod.check_output(
                self.YT_BASE + ["--flat-playlist", "-J", pl_url], text=True
            )
        )
        items = info.get("entries")

        fetch_cover = fetch_cover or self.fetch_cover
        fetch_thumbnail = fetch_thumbnail or self.fetch_thumbnail
        mp3_func = mp3_func or self.mp3_from_url

        def rip_item(url: str) -> None:
            artist, album, path = mp3_func(url, staging)
            dest = staging / artist / album
            dest.mkdir(parents=True, exist_ok=True)
            shutil_mod.move(str(path), dest / path.name)

        if items:
            def to_url(it: object) -> str:
                vid = it.get("id") if isinstance(it, dict) else str(it)
                return f"https://youtu.be/{vid}"

            with concurrent.futures.ThreadPoolExecutor() as ex:
                list(ex.map(lambda it: rip_item(to_url(it)), items))
        else:
            rip_item(pl_url)

        print("Songs successfully transferred to staging directory")
        return "done"

    def staging_has_files(self) -> bool:
        staging = self.data_dir / "staging"
        return staging.exists() and any(staging.iterdir())

    def approve_all(self, *, shutil_mod=shutil) -> None:
        staging = self.data_dir / "staging"
        if not self.staging_has_files():
            return
        for p in list(staging.iterdir()):
            dest_artist = self.nas_path / p.name
            if dest_artist.exists():
                for album in p.iterdir():
                    shutil_mod.move(str(album), dest_artist / album.name)
                try:
                    p.rmdir()
                except OSError:
                    pass
            else:
                shutil_mod.move(str(p), dest_artist)
        try:
            staging.rmdir()
        except OSError:
            pass

    def approve_selected(self, paths: list[str], *, shutil_mod=shutil) -> None:
        staging_root = self.data_dir / "staging"
        if not paths:
            return
        for track in paths:
            src = Path(track)
            if not src.exists():
                continue
            dest_dir = self.nas_path / src.parents[1].name / src.parent.name
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil_mod.move(str(src), dest_dir / src.name)
            parent = src.parent
            while parent != staging_root:
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
        try:
            staging_root.rmdir()
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Duplicate-aware approval helpers
    # ------------------------------------------------------------------
    def _find_matches(
        self, dest_dir: Path, stem: str, *, threshold: float = 0.6
    ) -> list[Path]:
        """Return existing files in ``dest_dir`` with similar names."""
        from difflib import SequenceMatcher

        matches: list[Path] = []
        if dest_dir.exists():
            for existing in dest_dir.glob(f"*{self.AUDIO_EXT}"):
                ratio = SequenceMatcher(None, existing.stem.lower(), stem.lower()).ratio()
                if ratio >= threshold:
                    matches.append(existing)
        return matches

    def approve_with_checks(
        self,
        *,
        shutil_mod=shutil,
        input_func=input,
    ) -> None:
        """Approve staged tracks with duplicate checks and optional overwrite."""

        staging_root = self.data_dir / "staging"
        if not self.staging_has_files():
            return
        for artist_dir in list(staging_root.iterdir()):
            if not artist_dir.is_dir():
                continue
            for album_dir in list(artist_dir.iterdir()):
                if not album_dir.is_dir():
                    continue
                dest_dir = self.nas_path / artist_dir.name / album_dir.name
                dest_dir.mkdir(parents=True, exist_ok=True)
                for track_path in list(album_dir.glob(f"*{self.AUDIO_EXT}")):
                    dest_path = dest_dir / track_path.name
                    matches = self._find_matches(dest_dir, track_path.stem)
                    if matches:
                        print(f"Possible duplicates for {track_path.name}:")
                        for m in matches:
                            print(f" - {m.name}")
                        resp = input_func("Overwrite with new file? [y/N] ").strip().lower()
                        if not resp.startswith("y"):
                            continue
                        if dest_path.exists():
                            try:
                                dest_path.unlink()
                            except OSError:
                                pass
                    shutil_mod.move(str(track_path), dest_path)
                try:
                    album_dir.rmdir()
                except OSError:
                    pass
            try:
                artist_dir.rmdir()
            except OSError:
                pass
        try:
            staging_root.rmdir()
        except OSError:
            pass

    def delete_staging(self, *, shutil_mod=shutil) -> bool:
        staging = self.data_dir / "staging"
        if not self.staging_has_files():
            return False
        shutil_mod.rmtree(staging)
        return True

    def list_staged_tracks(self) -> list[Track]:
        staging = self.data_dir / "staging"
        if not staging.exists():
            return []

        tracks: list[Track] = []
        for artist_dir in staging.iterdir():
            if not artist_dir.is_dir():
                continue
            for album_dir in artist_dir.iterdir():
                if not album_dir.is_dir():
                    continue
                for mp3 in album_dir.glob(f"*{self.AUDIO_EXT}"):
                    name = mp3.stem
                    if re.match(r"\d{2} ", name):
                        title = name[3:]
                    else:
                        title = name
                    cover_b64 = None
                    try:
                        from mutagen.mp4 import MP4, MP4Cover
                        import base64

                        tags = MP4(mp3)
                        pics = tags.tags.get("covr") if tags.tags else []
                        if pics:
                            pic = pics[0]
                            mime = (
                                "image/png"
                                if getattr(pic, "imageformat", MP4Cover.FORMAT_JPEG)
                                == MP4Cover.FORMAT_PNG
                                else "image/jpeg"
                            )
                            cover_b64 = "data:%s;base64,%s" % (
                                mime,
                                base64.b64encode(bytes(pic)).decode("ascii"),
                            )
                    except Exception:
                        cover_b64 = None
                    tracks.append(
                        Track(
                            job_id=0,
                            artist=artist_dir.name,
                            album=album_dir.name,
                            title=title,
                            filepath=str(mp3),
                            cover=cover_b64,
                        )
                    )
        tracks.sort(key=lambda t: (t.artist.lower(), t.album.lower()))
        return tracks

    def read_tags(self, filepath: str) -> dict[str, str]:
        path = Path(filepath)
        try:
            from mutagen.easymp4 import EasyMP4
        except Exception:
            EasyMP4 = None
        if EasyMP4 is not None:
            try:
                audio = EasyMP4(path)
                name = path.stem
                title_from_file = name[3:] if re.match(r"\d{2} ", name) else name
                return {
                    "artist": audio.get("artist", [path.parents[1].name])[0],
                    "album": audio.get("album", [path.parent.name])[0],
                    "title": audio.get("title", [title_from_file])[0],
                }
            except Exception:
                pass
        name = path.stem
        title = name[3:] if re.match(r"\d{2} ", name) else name
        return {
            "artist": path.parents[1].name,
            "album": path.parent.name,
            "title": title,
        }

    def update_track(self, filepath: str, field: str, value: str) -> Path:
        value = self.clean(value)
        tags = self.read_tags(filepath)
        tags[field] = value
        try:
            from mutagen.easymp4 import EasyMP4
        except Exception:
            EasyMP4 = None
        if EasyMP4 is not None:
            try:
                audio = EasyMP4(filepath)
                audio["artist"] = [tags["artist"]]
                audio["album"] = [tags["album"]]
                audio["title"] = [tags["title"]]
                audio.save()
            except Exception:
                pass
        path = Path(filepath)
        if not path.exists():
            raise TrackUpdateError(f"File not found: {filepath}")
        staging_root = self.data_dir / "staging"
        dest_dir = staging_root / tags["artist"] / tags["album"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        prefix = ""
        if re.match(r"\d{2} ", path.stem):
            prefix = path.stem[:3]
        new_path = dest_dir / f"{prefix}{tags['title']}{self.AUDIO_EXT}"
        if path.resolve() != new_path.resolve():
            try:
                path.rename(new_path)
            except OSError as e:
                raise TrackUpdateError(str(e))
            parent = path.parent
            while parent != staging_root:
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
        return new_path

    def update_album_art(self, filepath: str, data: bytes, mime: str = "image/jpeg") -> None:
        path = Path(filepath)
        if not path.exists():
            raise TrackUpdateError(f"File not found: {filepath}")
        try:
            from mutagen.mp4 import MP4, MP4Cover
        except Exception:
            return

        tags_info = self.read_tags(filepath)
        key = (tags_info["artist"], tags_info["album"])

        def write_art(mp3: Path) -> None:
            try:
                tags = MP4(mp3)
            except Exception:
                tags = MP4()
            if hasattr(tags, "delall"):
                try:
                    tags.delall("covr")  # type: ignore[attr-defined]
                except Exception:
                    pass
            tags["covr"] = [
                MP4Cover(
                    data,
                    imageformat=
                    MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG,
                )
            ]
            try:
                tags.save(mp3)
            except Exception as e:
                raise TrackUpdateError(str(e))

        for mp3 in path.parent.glob(f"*{self.AUDIO_EXT}"):
            write_art(mp3)

        with self.album_lock:
            self.album_art_cache[key] = data

    def find_matching_tracks(self, filepath: str) -> list[Path]:
        """Return existing library tracks similar to ``filepath``."""
        tags = self.read_tags(filepath)
        dest_dir = self.nas_path / tags["artist"] / tags["album"]
        return self._find_matches(dest_dir, Path(filepath).stem)

