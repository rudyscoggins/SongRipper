# src/songripper/worker.py
import subprocess, json, shutil, re
from pathlib import Path


class TrackUpdateError(Exception):
    """Raised when an update operation cannot be completed."""
    pass
from .settings import DATA_DIR, NAS_PATH
from .models import Track

YT_BASE = ["yt-dlp", "--quiet", "--no-warnings"]

def clean(text: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", text).strip()

def fetch_cover(artist: str, title: str, requests_mod=None) -> bytes | None:
    """Return album art from iTunes if available.

    Any network or parsing error should simply result in ``None`` rather
    than raising an exception during ripping.

    The ``requests_mod`` parameter allows dependency injection for unit
    testing.  If omitted, the real ``requests`` library is imported.
    """
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


def fetch_thumbnail(url: str, requests_mod=None) -> bytes | None:
    """Return thumbnail image bytes from ``url`` if possible.

    Any network error results in ``None``. The ``requests_mod`` parameter
    allows dependency injection for unit tests.
    """
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

def mp3_from_url(url: str, staging_dir: Path):
    # 1. get metadata only
    meta = json.loads(subprocess.check_output(
        YT_BASE + ["-J", "--no-playlist", url], text=True))
    artist = clean(meta.get("artist") or meta["uploader"])
    title  = clean(meta.get("track")  or meta["title"])
    album  = clean(meta.get("album")  or meta.get("playlist") or "Singles")

    # 2. download + convert to MP3
    outtmpl = str(staging_dir / f"{artist} - {title}.%(ext)s")
    subprocess.run(YT_BASE + ["-x", "--audio-format", "mp3",
                              "-o", outtmpl, url], check=True)

    mp3_path = staging_dir / f"{artist} - {title}.mp3"
    # 3. tag file.  Import mutagen lazily so the module can be imported
    # even when the dependency is missing (e.g. in unit tests).
    try:
        from mutagen.easyid3 import EasyID3
        from mutagen.id3 import ID3, APIC
    except Exception:
        EasyID3 = ID3 = APIC = None  # type: ignore

    if EasyID3 is not None:
        audio = EasyID3(mp3_path)
        audio["artist"], audio["title"], audio["album"] = [artist], [title], [album]
        audio.save()
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
        if cover:
            tags = ID3(mp3_path)
            tags["APIC"] = APIC(
                encoding=3,
                mime="image/jpeg",
                type=3,
                desc=u"Cover",
                data=cover,
            )
            tags.save()
    return artist, album, mp3_path

def rip_playlist(pl_url: str):
    staging = DATA_DIR / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    # flatten playlist ? list of video URLs
    items = json.loads(subprocess.check_output(
        YT_BASE + ["--flat-playlist", "-J", pl_url], text=True))["entries"]
    for it in items:
        url = f"https://youtu.be/{it['id']}"
        artist, album, path = mp3_from_url(url, staging)
        dest = staging / artist / album
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), dest / path.name)
    print("Songs successfully transferred to staging directory")
    return "done"

def staging_has_files() -> bool:
    """Return True if staging directory exists and is non-empty."""
    staging = DATA_DIR / "staging"
    return staging.exists() and any(staging.iterdir())

def approve_all():
    staging = DATA_DIR / "staging"
    # Staging may be missing if no playlists were ripped yet
    if not staging_has_files():
        return
    for p in staging.iterdir():
        shutil.move(str(p), NAS_PATH / p.name)

def delete_staging() -> bool:
    """Delete the staging directory if it contains files.

    Returns ``True`` if any files were removed, otherwise ``False``.
    ``False`` is returned when the directory does not exist or is empty.
    """
    staging = DATA_DIR / "staging"
    if not staging_has_files():
        return False
    shutil.rmtree(staging)
    return True


def list_staged_tracks() -> list[Track]:
    """Return a list of ``Track`` objects for files in the staging directory."""
    staging = DATA_DIR / "staging"
    if not staging.exists():
        return []

    tracks: list[Track] = []
    for artist_dir in staging.iterdir():
        if not artist_dir.is_dir():
            continue
        for album_dir in artist_dir.iterdir():
            if not album_dir.is_dir():
                continue
            for mp3 in album_dir.glob("*.mp3"):
                name = mp3.stem
                if " - " in name:
                    _, title = name.split(" - ", 1)
                else:
                    title = name
                cover_b64 = None
                try:  # pragma: no cover - optional dependency
                    from mutagen.id3 import ID3
                    import base64
                    tags = ID3(mp3)
                    pics = tags.getall("APIC") if hasattr(tags, "getall") else []
                    if pics:
                        pic = pics[0]
                        mime = getattr(pic, "mime", "image/jpeg")
                        cover_b64 = "data:%s;base64,%s" % (
                            mime,
                            base64.b64encode(pic.data).decode("ascii"),
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

    return tracks

def read_tags(filepath: str) -> dict[str, str]:
    """Return artist, album and title tags from ``filepath``.

    Falls back to directory and filename heuristics when tag parsing
    dependencies are missing.
    """
    path = Path(filepath)
    try:
        from mutagen.easyid3 import EasyID3
    except Exception:  # pragma: no cover - optional dependency
        EasyID3 = None
    if EasyID3 is not None:
        try:
            audio = EasyID3(path)
            return {
                "artist": audio.get("artist", [path.parents[1].name])[0],
                "album": audio.get("album", [path.parent.name])[0],
                "title": audio.get("title", [path.stem])[0],
            }
        except Exception:
            pass
    name = path.stem
    title = name.split(" - ", 1)[1] if " - " in name else name
    return {
        "artist": path.parents[1].name,
        "album": path.parent.name,
        "title": title,
    }

def update_track(filepath: str, field: str, value: str) -> Path:
    """Update ``field`` tag of the MP3 at ``filepath``.

    The file is renamed and moved inside the staging directory to match
    the updated artist/album/title structure.  Returns the new path.
    """
    value = clean(value)
    tags = read_tags(filepath)
    tags[field] = value
    try:
        from mutagen.easyid3 import EasyID3
    except Exception:  # pragma: no cover - optional dependency
        EasyID3 = None
    if EasyID3 is not None:
        try:
            audio = EasyID3(filepath)
            audio["artist"] = [tags["artist"]]
            audio["album"] = [tags["album"]]
            audio["title"] = [tags["title"]]
            audio.save()
        except Exception:
            pass
    path = Path(filepath)
    if not path.exists():
        raise TrackUpdateError(f"File not found: {filepath}")
    staging_root = DATA_DIR / "staging"
    dest_dir = staging_root / tags["artist"] / tags["album"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    new_path = dest_dir / f"{tags['artist']} - {tags['title']}.mp3"
    if path.resolve() != new_path.resolve():
        try:
            path.rename(new_path)
        except OSError as e:
            raise TrackUpdateError(str(e))
        # remove empty directories
        parent = path.parent
        while parent != staging_root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    return new_path
