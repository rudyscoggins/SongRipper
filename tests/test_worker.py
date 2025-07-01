import types
import os
import sys
import json
import threading
import time
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from songripper import worker
from songripper.worker import clean, fetch_cover, delete_staging
import pytest


def test_clean_replaces_forbidden_chars_with_space():
    text = 'A/B:C*D?E"F<G>H|I'
    assert clean(text) == 'A B C D E F G H I'


def test_clean_removes_emojis_and_collapses_space():
    text = 'Hello\U0001F600 World \U0001F3B5'
    assert clean(text) == 'Hello World'


def test_fetch_cover_uses_requests_module():
    calls = []
    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        class Resp:
            def __init__(self):
                self.content = b"img"
            def json(self):
                return {"results": [{"artworkUrl100": "http://x/100x100bb"}]}
            def raise_for_status(self):
                pass
        return Resp()
    fake_requests = types.SimpleNamespace(get=fake_get)
    result = fetch_cover("a", "b", fake_requests)
    assert result == b"img"
    assert calls[0][0] == "https://itunes.apple.com/search"
    assert calls[1][0] == "http://x/600x600bb"


@pytest.mark.parametrize("fail", ["get", "raise"])
def test_fetch_cover_returns_none_on_error(fail):
    def fake_get(url, params=None, timeout=None):
        if fail == "get":
            raise RuntimeError("boom")
        class Resp:
            def __init__(self):
                self.content = b"img"
            def json(self):
                return {"results": [{"artworkUrl100": "http://x/100x100bb"}]}
            def raise_for_status(self):
                if fail == "raise":
                    raise RuntimeError("boom")
        return Resp()

    fake_requests = types.SimpleNamespace(get=fake_get)
    assert fetch_cover("a", "b", fake_requests) is None


def test_delete_staging_returns_false_when_no_files(tmp_path):
    worker.DATA_DIR = tmp_path
    assert delete_staging() is False


def test_delete_staging_removes_dir_and_returns_true(tmp_path):
    worker.DATA_DIR = tmp_path
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "a").write_text("x")
    assert delete_staging() is True
    assert not staging.exists()


def test_rip_playlist_moves_files(monkeypatch, tmp_path):
    worker.DATA_DIR = tmp_path

    playlist_json = json.dumps({"entries": [{"id": "1"}, {"id": "2"}]})

    def fake_check_output(args, text=None):
        return playlist_json

    monkeypatch.setattr(worker.subprocess, "check_output", fake_check_output)

    songs = iter([
        ("artist1", "album1", tmp_path / "song1.mp3"),
        ("artist2", "album2", tmp_path / "song2.mp3"),
    ])

    def fake_mp3_from_url(url, staging):
        return next(songs)

    monkeypatch.setattr(worker, "mp3_from_url", fake_mp3_from_url)

    moves = []

    def fake_move(src, dst):
        moves.append((src, dst))

    monkeypatch.setattr(worker.shutil, "move", fake_move)

    result = worker.rip_playlist("http://pl")

    dest1 = tmp_path / "staging" / "artist1" / "album1" / "song1.mp3"
    dest2 = tmp_path / "staging" / "artist2" / "album2" / "song2.mp3"

    assert set(moves) == {
        (str(tmp_path / "song1.mp3"), dest1),
        (str(tmp_path / "song2.mp3"), dest2),
    }
    assert result == "done"


def test_staging_has_files(tmp_path):
    worker.DATA_DIR = tmp_path
    # No staging dir -> False
    assert worker.staging_has_files() is False
    staging = tmp_path / "staging"
    staging.mkdir()
    # Empty dir -> False
    assert worker.staging_has_files() is False
    (staging / "song.mp3").write_text("x")
    assert worker.staging_has_files() is True


def test_list_staged_tracks(tmp_path):
    worker.DATA_DIR = tmp_path
    staging = tmp_path / "staging"
    # Create files in reverse order to ensure sorting occurs
    (staging / "BArtist" / "BAlbum").mkdir(parents=True)
    f2 = staging / "BArtist" / "BAlbum" / "Song2.mp3"
    f2.write_text("y")
    (staging / "AArtist" / "AAlbum").mkdir(parents=True)
    f1 = staging / "AArtist" / "AAlbum" / "Song1.mp3"
    f1.write_text("x")

    tracks = worker.list_staged_tracks()

    assert [(t.artist, t.album, t.title, t.filepath) for t in tracks] == [
        ("AArtist", "AAlbum", "Song1", str(f1)),
        ("BArtist", "BAlbum", "Song2", str(f2)),
    ]


def test_mp3_from_url_embeds_thumbnail_when_no_itunes(monkeypatch, tmp_path):
    meta = {
        "artist": "Bad/Artist",
        "track": "Bad:Title?",
        "album": "Alb<>um",
        "uploader": "Uploader",
        "title": "Some Title",
        "playlist": "List",
        "thumbnail": "http://thumb/img.jpg",
    }

    def fake_check_output(cmd, text=True):
        return json.dumps(meta)

    monkeypatch.setattr(worker.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(worker.subprocess, "run", lambda *a, **kw: None)
    monkeypatch.setattr(worker, "fetch_cover", lambda a, t: None)

    thumb_calls = []

    def fake_fetch_thumb(url):
        thumb_calls.append(url)
        return b"thumb"

    monkeypatch.setattr(worker, "fetch_thumbnail", fake_fetch_thumb)

    class DummyEasyID3(dict):
        def __init__(self, path):
            self.path = path
        def save(self):
            pass

    id3_objects = []

    class DummyID3(dict):
        def __init__(self, path):
            self.path = path
            id3_objects.append(self)
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

    artist, album, path = worker.mp3_from_url("http://x", tmp_path)

    artist_clean = worker.clean(meta["artist"])
    title_clean = worker.clean(meta["track"])

    assert thumb_calls == [meta["thumbnail"]]
    assert isinstance(id3_objects[0]["APIC"], DummyAPIC)
    assert id3_objects[0]["APIC"].kw["data"] == b"thumb"
    assert path == tmp_path / f"{title_clean}.mp3"


def test_update_track_sanitizes_new_value(tmp_path):
    worker.DATA_DIR = tmp_path
    staging = tmp_path / "staging" / "Artist" / "Album"
    staging.mkdir(parents=True)
    track = staging / "Song.mp3"
    track.write_text("x")

    new_path = worker.update_track(str(track), "artist", "AC/DC")

    assert new_path.name == "Song.mp3"
    assert new_path.exists()


def test_update_track_missing_file_raises(tmp_path):
    worker.DATA_DIR = tmp_path
    missing = tmp_path / "staging" / "bad.mp3"
    with pytest.raises(worker.TrackUpdateError):
        worker.update_track(str(missing), "artist", "A")


def test_update_track_moves_file_and_listing_updates(tmp_path):
    worker.DATA_DIR = tmp_path

    staging = tmp_path / "staging" / "OldArtist" / "OldAlbum"
    staging.mkdir(parents=True)
    track = staging / "OldTitle.mp3"
    track.write_text("x")

    # Update artist
    p1 = worker.update_track(str(track), "artist", "NewArtist")
    assert p1 == tmp_path / "staging" / "NewArtist" / "OldAlbum" / "OldTitle.mp3"
    assert p1.exists()
    assert not track.exists()
    tr = worker.list_staged_tracks()
    assert [(t.artist, t.album, t.title) for t in tr] == [("NewArtist", "OldAlbum", "OldTitle")]

    # Update album
    p2 = worker.update_track(str(p1), "album", "NewAlbum")
    assert p2 == tmp_path / "staging" / "NewArtist" / "NewAlbum" / "OldTitle.mp3"
    assert p2.exists()
    assert not p1.exists()
    tr = worker.list_staged_tracks()
    assert [(t.artist, t.album, t.title) for t in tr] == [("NewArtist", "NewAlbum", "OldTitle")]

    # Update title
    p3 = worker.update_track(str(p2), "title", "NewTitle")
    assert p3 == tmp_path / "staging" / "NewArtist" / "NewAlbum" / "NewTitle.mp3"
    assert p3.exists()
    tr = worker.list_staged_tracks()
    assert [(t.artist, t.album, t.title) for t in tr] == [
        ("NewArtist", "NewAlbum", "NewTitle")
    ]


def test_update_album_art_writes_image(monkeypatch, tmp_path):
    mp3 = tmp_path / "song.mp3"
    mp3.write_text("x")

    id3_objects = []

    class DummyID3(dict):
        def __init__(self, path=None):
            self.path = path
            id3_objects.append(self)

        def save(self, path=None):
            self.saved = path

    class DummyAPIC:
        def __init__(self, **kw):
            self.kw = kw

    monkeypatch.setitem(
        sys.modules,
        "mutagen.id3",
        types.SimpleNamespace(ID3=DummyID3, APIC=DummyAPIC),
    )

    worker.update_album_art(str(mp3), b"img", "image/png")

    assert isinstance(id3_objects[0]["APIC"], DummyAPIC)
    assert id3_objects[0]["APIC"].kw["data"] == b"img"
    assert id3_objects[0]["APIC"].kw["mime"] == "image/png"
    assert id3_objects[0].saved == mp3


def test_update_album_art_replaces_existing(monkeypatch, tmp_path):
    mp3 = tmp_path / "song.mp3"
    mp3.write_text("x")

    class DummyID3(dict):
        def __init__(self, path=None):
            self.deleted = False
            self.saved = None

        def delall(self, key):
            if key == "APIC":
                self.deleted = True

        def save(self, path=None):
            self.saved = path

    class DummyAPIC:
        def __init__(self, **kw):
            self.kw = kw

    id3_instance = DummyID3()
    monkeypatch.setitem(
        sys.modules,
        "mutagen.id3",
        types.SimpleNamespace(ID3=lambda p=None: id3_instance, APIC=DummyAPIC),
    )

    worker.update_album_art(str(mp3), b"img", "image/png")

    assert id3_instance.deleted
    assert isinstance(id3_instance["APIC"], DummyAPIC)
    assert id3_instance.saved == mp3


def test_update_album_art_updates_all_album_tracks(monkeypatch, tmp_path):
    album_dir = tmp_path / "Artist" / "Album"
    album_dir.mkdir(parents=True)
    t1 = album_dir / "t1.mp3"
    t2 = album_dir / "t2.mp3"
    t1.write_text("x")
    t2.write_text("y")

    id3_objects = []

    class DummyID3(dict):
        def __init__(self, path=None):
            self.path = path

        def save(self, path=None):
            self.saved = path

        def delall(self, key):
            pass

    class DummyAPIC:
        def __init__(self, **kw):
            self.kw = kw
            id3_objects.append((kw.get("data"), self))

    def id3_factory(p=None):
        obj = DummyID3(p)
        return obj

    monkeypatch.setitem(
        sys.modules,
        "mutagen.id3",
        types.SimpleNamespace(ID3=id3_factory, APIC=DummyAPIC),
    )

    worker.ALBUM_ART_CACHE.clear()
    worker.update_album_art(str(t1), b"img", "image/png")

    assert len(id3_objects) == 2
    assert all(obj[0] == b"img" for obj in id3_objects)
    with worker.ALBUM_LOCK:
        assert worker.ALBUM_ART_CACHE[("Artist", "Album")] == b"img"


def test_update_album_art_missing_file_raises(tmp_path):
    missing = tmp_path / "x.mp3"
    with pytest.raises(worker.TrackUpdateError):
        worker.update_album_art(str(missing), b"img")


def test_approve_all_merges_existing_artist(tmp_path):
    worker.DATA_DIR = tmp_path
    worker.NAS_PATH = tmp_path / "nas"

    staging = tmp_path / "staging" / "Artist" / "NewAlbum"
    staging.mkdir(parents=True)
    (staging / "track.mp3").write_text("x")

    existing = worker.NAS_PATH / "Artist" / "OldAlbum"
    existing.mkdir(parents=True, exist_ok=True)
    (existing / "old.mp3").write_text("y")

    worker.approve_all()

    assert (existing / "old.mp3").exists()
    assert (worker.NAS_PATH / "Artist" / "NewAlbum" / "track.mp3").exists()
    assert not (worker.NAS_PATH / "Artist" / "Artist").exists()
    assert worker.staging_has_files() is False


def test_approve_selected_moves_only_specified(tmp_path):
    worker.DATA_DIR = tmp_path
    worker.NAS_PATH = tmp_path / "nas"

    staging_album = tmp_path / "staging" / "Artist" / "Album"
    staging_album.mkdir(parents=True)
    t1 = staging_album / "t1.mp3"
    t2 = staging_album / "t2.mp3"
    t1.write_text("x")
    t2.write_text("y")

    worker.approve_selected([str(t1)])

    assert (worker.NAS_PATH / "Artist" / "Album" / "t1.mp3").exists()
    assert t2.exists()
    assert (worker.NAS_PATH / "Artist" / "Album" / "t2.mp3").exists() is False
    assert worker.staging_has_files() is True

    worker.approve_selected([str(t2)])
    assert not (tmp_path / "staging").exists()


def test_rip_playlist_runs_in_parallel(monkeypatch, tmp_path):
    worker.DATA_DIR = tmp_path

    playlist_json = json.dumps({"entries": [{"id": "1"}, {"id": "2"}]})
    monkeypatch.setattr(worker.subprocess, "check_output", lambda *a, **k: playlist_json)

    thread_ids = []

    def fake_mp3_from_url(url, staging):
        thread_ids.append(threading.get_ident())
        time.sleep(0.01)
        return ("a", "b", tmp_path / f"{url.split('/')[-1]}.mp3")

    monkeypatch.setattr(worker, "mp3_from_url", fake_mp3_from_url)
    monkeypatch.setattr(worker.shutil, "move", lambda *a, **k: None)

    worker.rip_playlist("http://pl")

    assert len(set(thread_ids)) >= 2

