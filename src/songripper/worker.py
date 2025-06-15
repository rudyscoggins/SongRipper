# src/songripper/worker.py
import subprocess, json, shutil, re, requests
from pathlib import Path
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC
from .settings import DATA_DIR, NAS_PATH

YT_BASE = ["yt-dlp", "--quiet", "--no-warnings"]

def clean(text: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", text).strip()

def fetch_cover(artist: str, title: str) -> bytes | None:
    q = requests.get("https://itunes.apple.com/search",
                     params={"term": f"{artist} {title}", "entity": "song", "limit": 1},
                     timeout=10).json()
    try:
        url = q["results"][0]["artworkUrl100"].replace("100x100bb", "600x600bb")
        return requests.get(url, timeout=10).content
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
    # 3. tag file
    audio = EasyID3(mp3_path)
    audio["artist"], audio["title"], audio["album"] = [artist], [title], [album]
    audio.save()
    cover = fetch_cover(artist, title)
    if cover:
        tags = ID3(mp3_path)
        tags["APIC"] = APIC(encoding=3, mime="image/jpeg",
                            type=3, desc=u"Cover", data=cover)
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
    return "done"

def approve_all():
    for p in (DATA_DIR / "staging").iterdir():
        shutil.move(str(p), NAS_PATH / p.name)
