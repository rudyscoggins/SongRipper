import types
import os
import sys
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from songripper import worker
from songripper.worker import clean, fetch_cover, delete_staging
import pytest


def test_clean_removes_forbidden_chars():
    text = 'A/B:C*D?E"F<G>H|I'
    assert clean(text) == 'A_B_C_D_E_F_G_H_I'


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

    assert moves == [
        (str(tmp_path / "song1.mp3"), dest1),
        (str(tmp_path / "song2.mp3"), dest2),
    ]
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
    (staging / "Artist1" / "Album1").mkdir(parents=True)
    f1 = staging / "Artist1" / "Album1" / "Artist1 - Song1.mp3"
    f1.write_text("x")
    (staging / "Artist2" / "Album2").mkdir(parents=True)
    f2 = staging / "Artist2" / "Album2" / "Artist2 - Song2.mp3"
    f2.write_text("y")

    tracks = sorted(worker.list_staged_tracks(), key=lambda t: t.title)

    assert [(t.artist, t.album, t.title, t.filepath) for t in tracks] == [
        ("Artist1", "Album1", "Song1", str(f1)),
        ("Artist2", "Album2", "Song2", str(f2)),
    ]
