import types
import os
import sys
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


@pytest.mark.parametrize(
    "fail_point",
    ["search_get", "search_raise", "cover_get", "cover_raise"],
)
def test_fetch_cover_returns_none_on_error(fail_point):
    calls = []

    def fake_get(url, params=None, timeout=None):
        idx = len(calls)
        calls.append(url)
        if fail_point == "search_get" and idx == 0:
            raise RuntimeError("boom")
        if fail_point == "cover_get" and idx == 1:
            raise RuntimeError("boom")

        class Resp:
            def __init__(self):
                self.content = b"img"

            def json(self):
                return {"results": [{"artworkUrl100": "http://x/100x100bb"}]}

            def raise_for_status(self):
                if fail_point == "search_raise" and idx == 0:
                    raise RuntimeError("boom")
                if fail_point == "cover_raise" and idx == 1:
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
