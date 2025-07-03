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
        ("artist1", "album1", tmp_path / f"song1{worker.AUDIO_EXT}"),
        ("artist2", "album2", tmp_path / f"song2{worker.AUDIO_EXT}"),
    ])

    def fake_mp3_from_url(url, staging):
        return next(songs)

    monkeypatch.setattr(worker, "mp3_from_url", fake_mp3_from_url)

    moves = []

    def fake_move(src, dst):
        moves.append((src, dst))

    monkeypatch.setattr(worker.shutil, "move", fake_move)

    result = worker.rip_playlist("http://pl")

    dest1 = tmp_path / "staging" / "artist1" / "album1" / f"song1{worker.AUDIO_EXT}"
    dest2 = tmp_path / "staging" / "artist2" / "album2" / f"song2{worker.AUDIO_EXT}"

    assert set(moves) == {
        (str(tmp_path / f"song1{worker.AUDIO_EXT}"), dest1),
        (str(tmp_path / f"song2{worker.AUDIO_EXT}"), dest2),
    }
    assert result == "done"


def test_rip_playlist_accepts_video_url(monkeypatch, tmp_path):
    worker.DATA_DIR = tmp_path

    video_json = json.dumps({"id": "x"})

    monkeypatch.setattr(
        worker.subprocess, "check_output", lambda *a, **k: video_json
    )

    monkeypatch.setattr(
        worker,
        "mp3_from_url",
        lambda url, staging: ("a", "b", tmp_path / f"s{worker.AUDIO_EXT}"),
    )

    moves = []
    monkeypatch.setattr(worker.shutil, "move", lambda s, d: moves.append((s, d)))

    result = worker.rip_playlist("http://vid")

    dest = tmp_path / "staging" / "a" / "b" / f"s{worker.AUDIO_EXT}"
    assert moves == [(str(tmp_path / f"s{worker.AUDIO_EXT}"), dest)]
    assert result == "done"


def test_staging_has_files(tmp_path):
    worker.DATA_DIR = tmp_path
    # No staging dir -> False
    assert worker.staging_has_files() is False
    staging = tmp_path / "staging"
    staging.mkdir()
    # Empty dir -> False
    assert worker.staging_has_files() is False
    (staging / f"song{worker.AUDIO_EXT}").write_text("x")
    assert worker.staging_has_files() is True


def test_list_staged_tracks(tmp_path):
    worker.DATA_DIR = tmp_path
    staging = tmp_path / "staging"
    # Create files in reverse order to ensure sorting occurs
    (staging / "BArtist" / "BAlbum").mkdir(parents=True)
    f2 = staging / "BArtist" / "BAlbum" / f"Song2{worker.AUDIO_EXT}"
    f2.write_text("y")
    (staging / "AArtist" / "AAlbum").mkdir(parents=True)
    f1 = staging / "AArtist" / "AAlbum" / f"Song1{worker.AUDIO_EXT}"
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

    class DummyAPIC(bytes):
        FORMAT_JPEG = 0
        FORMAT_PNG = 1

        def __new__(cls, data, imageformat=None):
            obj = bytes.__new__(cls, data)
            obj.kw = {"data": data, "imageformat": imageformat}
            return obj

    monkeypatch.setitem(
        sys.modules,
        "mutagen.easymp4",
        types.SimpleNamespace(EasyMP4=DummyEasyID3),
    )
    monkeypatch.setitem(
        sys.modules,
        "mutagen.mp4",
        types.SimpleNamespace(MP4=DummyID3, MP4Cover=DummyAPIC),
    )

    artist, album, path = worker.mp3_from_url("http://x", tmp_path)

    artist_clean = worker.clean(meta["artist"])
    title_clean = worker.clean(meta["track"])

    assert thumb_calls == [meta["thumbnail"]]
    assert isinstance(id3_objects[0]["covr"], list)
    assert isinstance(id3_objects[0]["covr"][0], DummyAPIC)
    assert id3_objects[0]["covr"][0].kw["data"] == b"thumb"
    assert path == tmp_path / f"{title_clean}{worker.AUDIO_EXT}"


def test_update_track_sanitizes_new_value(tmp_path):
    worker.DATA_DIR = tmp_path
    staging = tmp_path / "staging" / "Artist" / "Album"
    staging.mkdir(parents=True)
    track = staging / f"Song{worker.AUDIO_EXT}"
    track.write_text("x")

    new_path = worker.update_track(str(track), "artist", "AC/DC")

    assert new_path.name == f"Song{worker.AUDIO_EXT}"
    assert new_path.exists()


def test_update_track_missing_file_raises(tmp_path):
    worker.DATA_DIR = tmp_path
    missing = tmp_path / "staging" / f"bad{worker.AUDIO_EXT}"
    with pytest.raises(worker.TrackUpdateError):
        worker.update_track(str(missing), "artist", "A")


def test_update_track_moves_file_and_listing_updates(tmp_path):
    worker.DATA_DIR = tmp_path

    staging = tmp_path / "staging" / "OldArtist" / "OldAlbum"
    staging.mkdir(parents=True)
    track = staging / f"OldTitle{worker.AUDIO_EXT}"
    track.write_text("x")

    # Update artist
    p1 = worker.update_track(str(track), "artist", "NewArtist")
    assert p1 == tmp_path / "staging" / "NewArtist" / "OldAlbum" / f"OldTitle{worker.AUDIO_EXT}"
    assert p1.exists()
    assert not track.exists()
    tr = worker.list_staged_tracks()
    assert [(t.artist, t.album, t.title) for t in tr] == [("NewArtist", "OldAlbum", "OldTitle")]

    # Update album
    p2 = worker.update_track(str(p1), "album", "NewAlbum")
    assert p2 == tmp_path / "staging" / "NewArtist" / "NewAlbum" / f"OldTitle{worker.AUDIO_EXT}"
    assert p2.exists()
    assert not p1.exists()
    tr = worker.list_staged_tracks()
    assert [(t.artist, t.album, t.title) for t in tr] == [("NewArtist", "NewAlbum", "OldTitle")]

    # Update title
    p3 = worker.update_track(str(p2), "title", "NewTitle")
    assert p3 == tmp_path / "staging" / "NewArtist" / "NewAlbum" / f"NewTitle{worker.AUDIO_EXT}"
    assert p3.exists()
    tr = worker.list_staged_tracks()
    assert [(t.artist, t.album, t.title) for t in tr] == [
        ("NewArtist", "NewAlbum", "NewTitle")
    ]


def test_update_album_art_writes_image(monkeypatch, tmp_path):
    mp3 = tmp_path / f"song{worker.AUDIO_EXT}"
    mp3.write_text("x")

    id3_objects = []

    class DummyMP4(dict):
        def __init__(self, path=None):
            self.path = path
            id3_objects.append(self)

        def save(self, path=None):
            self.saved = path

    class DummyCover:
        FORMAT_JPEG = 0
        FORMAT_PNG = 1

        def __init__(self, data, imageformat=None):
            self.kw = {"data": data, "imageformat": imageformat}

    monkeypatch.setitem(
        sys.modules,
        "mutagen.mp4",
        types.SimpleNamespace(MP4=DummyMP4, MP4Cover=DummyCover),
    )

    worker.update_album_art(str(mp3), b"img", "image/png")

    assert isinstance(id3_objects[0]["covr"], list)
    assert isinstance(id3_objects[0]["covr"][0], DummyCover)
    assert id3_objects[0]["covr"][0].kw["data"] == b"img"
    assert id3_objects[0]["covr"][0].kw["imageformat"] == DummyCover.FORMAT_PNG
    assert id3_objects[0].saved == mp3


def test_update_album_art_replaces_existing(monkeypatch, tmp_path):
    mp3 = tmp_path / f"song{worker.AUDIO_EXT}"
    mp3.write_text("x")

    class DummyMP4(dict):
        def __init__(self, path=None):
            self.deleted = False
            self.saved = None

        def delall(self, key):
            if key == "covr":
                self.deleted = True

        def save(self, path=None):
            self.saved = path

    class DummyCover:
        FORMAT_JPEG = 0
        FORMAT_PNG = 1

        def __init__(self, data, imageformat=None):
            self.kw = {"data": data, "imageformat": imageformat}

    id3_instance = DummyMP4()
    monkeypatch.setitem(
        sys.modules,
        "mutagen.mp4",
        types.SimpleNamespace(MP4=lambda p=None: id3_instance, MP4Cover=DummyCover),
    )

    worker.update_album_art(str(mp3), b"img", "image/png")

    assert id3_instance.deleted
    assert isinstance(id3_instance["covr"], list)
    assert isinstance(id3_instance["covr"][0], DummyCover)
    assert id3_instance.saved == mp3


def test_update_album_art_updates_all_album_tracks(monkeypatch, tmp_path):
    album_dir = tmp_path / "Artist" / "Album"
    album_dir.mkdir(parents=True)
    t1 = album_dir / f"t1{worker.AUDIO_EXT}"
    t2 = album_dir / f"t2{worker.AUDIO_EXT}"
    t1.write_text("x")
    t2.write_text("y")

    id3_objects = []

    class DummyMP4(dict):
        def __init__(self, path=None):
            self.path = path

        def save(self, path=None):
            self.saved = path

        def delall(self, key):
            pass

    class DummyCover:
        FORMAT_JPEG = 0
        FORMAT_PNG = 1

        def __init__(self, data, imageformat=None):
            self.kw = {"data": data, "imageformat": imageformat}
            id3_objects.append((data, self))

    def id3_factory(p=None):
        obj = DummyMP4(p)
        return obj

    monkeypatch.setitem(
        sys.modules,
        "mutagen.mp4",
        types.SimpleNamespace(MP4=id3_factory, MP4Cover=DummyCover),
    )

    worker.ALBUM_ART_CACHE.clear()
    worker.update_album_art(str(t1), b"img", "image/png")

    assert len(id3_objects) == 2
    assert all(obj[0] == b"img" for obj in id3_objects)
    with worker.ALBUM_LOCK:
        assert worker.ALBUM_ART_CACHE[("Artist", "Album")] == b"img"


def test_update_album_art_missing_file_raises(tmp_path):
    missing = tmp_path / f"x{worker.AUDIO_EXT}"
    with pytest.raises(worker.TrackUpdateError):
        worker.update_album_art(str(missing), b"img")


def test_approve_all_merges_existing_artist(tmp_path):
    worker.DATA_DIR = tmp_path
    worker.NAS_PATH = tmp_path / "nas"

    staging = tmp_path / "staging" / "Artist" / "NewAlbum"
    staging.mkdir(parents=True)
    (staging / f"track{worker.AUDIO_EXT}").write_text("x")

    existing = worker.NAS_PATH / "Artist" / "OldAlbum"
    existing.mkdir(parents=True, exist_ok=True)
    (existing / f"old{worker.AUDIO_EXT}").write_text("y")

    worker.approve_all()

    assert (existing / f"old{worker.AUDIO_EXT}").exists()
    assert (worker.NAS_PATH / "Artist" / "NewAlbum" / f"track{worker.AUDIO_EXT}").exists()
    assert not (worker.NAS_PATH / "Artist" / "Artist").exists()
    assert worker.staging_has_files() is False


def test_approve_selected_moves_only_specified(tmp_path):
    worker.DATA_DIR = tmp_path
    worker.NAS_PATH = tmp_path / "nas"

    staging_album = tmp_path / "staging" / "Artist" / "Album"
    staging_album.mkdir(parents=True)
    t1 = staging_album / f"t1{worker.AUDIO_EXT}"
    t2 = staging_album / f"t2{worker.AUDIO_EXT}"
    t1.write_text("x")
    t2.write_text("y")

    worker.approve_selected([str(t1)])

    assert (worker.NAS_PATH / "Artist" / "Album" / f"t1{worker.AUDIO_EXT}").exists()
    assert t2.exists()
    assert (worker.NAS_PATH / "Artist" / "Album" / f"t2{worker.AUDIO_EXT}").exists() is False
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
        return ("a", "b", tmp_path / f"{url.split('/')[-1]}{worker.AUDIO_EXT}")

    monkeypatch.setattr(worker, "mp3_from_url", fake_mp3_from_url)
    monkeypatch.setattr(worker.shutil, "move", lambda *a, **k: None)

    worker.rip_playlist("http://pl")

    assert len(set(thread_ids)) >= 2


def test_approve_with_checks_overwrites_when_confirmed(tmp_path):
    worker.DATA_DIR = tmp_path
    worker.NAS_PATH = tmp_path / "nas"

    staging = tmp_path / "staging" / "Artist" / "Album"
    staging.mkdir(parents=True)
    new_file = staging / f"t{worker.AUDIO_EXT}"
    new_file.write_text("new")

    dest_dir = worker.NAS_PATH / "Artist" / "Album"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / f"t{worker.AUDIO_EXT}"
    dest_file.write_text("old")

    worker.approve_with_checks(lambda prompt: "y")

    assert dest_file.read_text() == "new"
    assert not new_file.exists()
    assert worker.staging_has_files() is False


def test_approve_with_checks_skips_when_declined(tmp_path):
    worker.DATA_DIR = tmp_path
    worker.NAS_PATH = tmp_path / "nas"

    staging = tmp_path / "staging" / "Artist" / "Album"
    staging.mkdir(parents=True)
    new_file = staging / f"t{worker.AUDIO_EXT}"
    new_file.write_text("new")

    dest_dir = worker.NAS_PATH / "Artist" / "Album"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / f"t{worker.AUDIO_EXT}"
    dest_file.write_text("old")

    worker.approve_with_checks(lambda prompt: "n")

    assert dest_file.read_text() == "old"
    assert new_file.exists()
    assert worker.staging_has_files() is True

