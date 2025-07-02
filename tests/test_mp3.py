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
    monkeypatch.setattr(worker, "fetch_track_info", lambda *a, **k: None)
    monkeypatch.setattr(worker, "fetch_track_number", lambda *a, **k: None)
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
        "-x", "--audio-format", "mp3",
        "-o", str(tmp_path / f"{title_clean}.%(ext)s"),
        "http://x",
    ]
    assert run_calls == [(expected_out, True)]
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
    monkeypatch.setattr(worker, "fetch_track_info", lambda *a, **k: None)
    monkeypatch.setattr(worker, "fetch_track_number", lambda *a, **k: None)

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
    monkeypatch.setattr(worker, "fetch_track_info", lambda *a, **k: None)
    monkeypatch.setattr(worker, "fetch_track_number", lambda *a, **k: None)

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
    assert run_calls == [(expected_out, True)]


def test_fetch_track_info(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None, headers=None):
        calls.append((url, params))

        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                if params and "query" in params:
                    return {
                        "releases": [
                            {
                                "id": "r1",
                                "title": "Album",
                                "artist-credit": [{"name": "Artist"}],
                            }
                        ]
                    }
                return {
                    "media": [
                        {
                            "tracks": [
                                {
                                    "title": "Title",
                                    "number": "5",
                                    "artist-credit": [{"name": "Artist"}],
                                }
                            ]
                        }
                    ]
                }

        return Resp()

    fake_requests = types.SimpleNamespace(get=fake_get)
    info = worker.fetch_track_info("Artist", "Album", "Title", fake_requests)
    assert info == ("Artist", "Album", "Title", 5)
    assert calls[0][0].startswith("https://musicbrainz.org/ws/2/release/")


def test_mp3_from_url_uses_musicbrainz_when_missing_track(tmp_path, monkeypatch):
    meta = {
        "artist": "Artist",
        "track": "Title",
        "album": "Album",
        "uploader": "Uploader",
        "title": "Title",
        "playlist": "List",
    }

    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: json.dumps(meta))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(worker, "fetch_cover", lambda *a, **k: None)
    monkeypatch.setattr(worker, "fetch_track_info", lambda a, b, c: ("MB Artist", "MB Album", "MB Title", 3))
    monkeypatch.setattr(worker, "fetch_track_number", lambda *a, **k: None)

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

    assert artist == "MB Artist"
    assert album == "MB Album"
    assert path == tmp_path / "03 MB Title.mp3"

