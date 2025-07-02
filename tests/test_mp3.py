import os
import sys
import json
import types
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from songripper import worker
from songripper.worker import mp3_from_url


def test_mp3_from_url(tmp_path, monkeypatch):
    meta = {
        "artist": "Bad/Artist",
        "track": "Bad:Title?",
        "album": "Alb<>um",
        "uploader": "Uploader",
        "title": "Some Title",
        "playlist": "List"
    }

    check_calls = []

    def fake_check_output(cmd, text=True):
        check_calls.append((cmd, text))
        assert cmd == worker.YT_BASE + ["-J", "--no-playlist", "http://x"]
        assert text is True
        return json.dumps(meta)

    run_calls = []

    def fake_run(cmd, check=False):
        run_calls.append((cmd, check))

    fetch_calls = []

    def fake_fetch_cover(a, t):
        fetch_calls.append((a, t))
        return None

    easy_paths = []

    class DummyEasyID3(dict):
        def __init__(self, path):
            easy_paths.append(path)
            self.path = path
        def save(self):
            pass

    class DummyID3(dict):
        def __init__(self, path):
            self.path = path
        def save(self):
            pass

    class DummyAPIC:
        def __init__(self, **kw):
            self.kw = kw

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(worker, "fetch_cover", fake_fetch_cover)
    monkeypatch.setitem(
        sys.modules,
        "mutagen.easyid3",
        types.SimpleNamespace(EasyID3=DummyEasyID3),
    )
    monkeypatch.setitem(
        sys.modules,
        "mutagen.id3",
        types.SimpleNamespace(ID3=DummyID3, APIC=DummyAPIC),
    )

    artist, album, path = mp3_from_url("http://x", tmp_path)

    artist_clean = worker.clean(meta["artist"])
    title_clean = worker.clean(meta["track"])
    album_clean = worker.clean(meta["album"])

    assert artist == artist_clean
    assert album == album_clean
    assert path == tmp_path / f"{title_clean}.mp3"

    expected_out = worker.YT_BASE + [
        "-x",
        "--audio-format",
        "mp3",
        "-o",
        str(tmp_path / f"{title_clean}.%(ext)s"),
        "http://x",
    ]
    expected_trim = [
        "ffmpeg",
        "-y",
        "-i",
        str(tmp_path / f"{title_clean}.mp3"),
        "-af",
        (
            "silenceremove="
            "start_periods=1:start_duration=5:start_threshold=-50dB:" +
            "stop_periods=1:stop_duration=5:stop_threshold=-50dB"
        ),
        str(tmp_path / f"{title_clean}_trim.mp3"),
    ]
    assert run_calls == [(expected_out, True), (expected_trim, True)]
    assert fetch_calls == [(artist_clean, title_clean)]
    assert check_calls == [(
        worker.YT_BASE + ["-J", "--no-playlist", "http://x"],
        True,
    )]
    assert easy_paths == [tmp_path / f"{title_clean}.mp3"]


def test_mp3_from_url_uses_cached_cover(tmp_path, monkeypatch):
    meta = {
        "artist": "Artist",
        "track": "Title",
        "album": "Album",
        "uploader": "Uploader",
        "title": "Some Title",
        "playlist": "List",
    }

    def fake_check_output(cmd, text=True):
        return json.dumps(meta)

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)

    cover_calls = []

    def fake_fetch_cover(a, t):
        cover_calls.append((a, t))
        return b"img"

    monkeypatch.setattr(worker, "fetch_cover", fake_fetch_cover)

    class DummyEasyID3(dict):
        def __init__(self, path):
            self.path = path

        def save(self):
            pass

    class DummyID3(dict):
        def __init__(self, path):
            self.path = path

        def save(self):
            pass

    class DummyAPIC:
        def __init__(self, **kw):
            self.kw = kw

    monkeypatch.setitem(
        sys.modules,
        "mutagen.easyid3",
        types.SimpleNamespace(EasyID3=DummyEasyID3),
    )
    monkeypatch.setitem(
        sys.modules,
        "mutagen.id3",
        types.SimpleNamespace(ID3=DummyID3, APIC=DummyAPIC),
    )

    worker.ALBUM_ART_CACHE.clear()

    mp3_from_url("http://x", tmp_path)
    mp3_from_url("http://x", tmp_path)

    assert len(cover_calls) == 1


def test_mp3_from_url_fallback_values(tmp_path, monkeypatch):
    meta = {
        "artist": "\U0001F600",
        "track": "\U0001F3B5",
        "album": "\U0001F3B6",
        "uploader": "Uploader",
        "title": "T",
        "playlist": "List",
    }

    def fake_check_output(cmd, text=True):
        return json.dumps(meta)

    run_calls = []

    def fake_run(cmd, check=False):
        run_calls.append((cmd, check))

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(worker, "fetch_cover", lambda *a, **k: None)

    class DummyEasyID3(dict):
        def __init__(self, path):
            self.path = path

        def save(self):
            pass

    class DummyID3(dict):
        def __init__(self, path):
            self.path = path

        def save(self):
            pass

    class DummyAPIC:
        def __init__(self, **kw):
            self.kw = kw

    monkeypatch.setitem(
        sys.modules,
        "mutagen.easyid3",
        types.SimpleNamespace(EasyID3=DummyEasyID3),
    )
    monkeypatch.setitem(
        sys.modules,
        "mutagen.id3",
        types.SimpleNamespace(ID3=DummyID3, APIC=DummyAPIC),
    )

    artist, album, path = mp3_from_url("http://x", tmp_path)

    assert artist == "Unknown Artist"
    assert album == "Unknown Album"
    assert path == tmp_path / "Unknown Title.mp3"

    expected_out = worker.YT_BASE + [
        "-x",
        "--audio-format",
        "mp3",
        "-o",
        str(tmp_path / "Unknown Title.%(ext)s"),
        "http://x",
    ]
    expected_trim = [
        "ffmpeg",
        "-y",
        "-i",
        str(tmp_path / "Unknown Title.mp3"),
        "-af",
        (
            "silenceremove="
            "start_periods=1:start_duration=5:start_threshold=-50dB:" +
            "stop_periods=1:stop_duration=5:stop_threshold=-50dB"
        ),
        str(tmp_path / "Unknown Title_trim.mp3"),
    ]
    assert run_calls == [(expected_out, True), (expected_trim, True)]
