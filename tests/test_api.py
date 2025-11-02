import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fastapi.testclient import TestClient

import songripper.api as api
import songripper.worker as worker

client = TestClient(api.app)


def test_delete_hx_success(monkeypatch):
    monkeypatch.setattr(worker, "delete_staging", lambda: True)
    monkeypatch.setattr(api, "delete_staging", lambda: True)
    resp = client.post("/delete", headers={"Hx-Request": "true"})
    assert resp.headers.get("HX-Trigger-After-Swap") == "refreshStaging"
    assert "Files deleted" in resp.text


def test_delete_hx_failure_no_trigger(monkeypatch):
    monkeypatch.setattr(worker, "delete_staging", lambda: False)
    monkeypatch.setattr(api, "delete_staging", lambda: False)
    resp = client.post("/delete", headers={"Hx-Request": "1"})
    assert "HX-Trigger-After-Swap" not in resp.headers
    assert "No files in staging" in resp.text


def test_delete_non_hx_redirect(monkeypatch):
    monkeypatch.setattr(worker, "delete_staging", lambda: True)
    monkeypatch.setattr(api, "delete_staging", lambda: True)
    resp = client.post("/delete")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/?msg=Files+deleted"


def test_approve_hx_triggers_refresh(monkeypatch):
    monkeypatch.setattr(worker, "approve_all", lambda: None)
    monkeypatch.setattr(api, "approve_all", worker.approve_all)
    resp = client.post("/approve", headers={"Hx-Request": "1"})
    assert resp.status_code == 204
    assert resp.headers["HX-Trigger"] == "refreshStaging"


def test_approve_hx_error_returns_message(monkeypatch, tmp_path):
    log_path = tmp_path / "errors.log"
    monkeypatch.setattr(api, "ERROR_LOG_PATH", log_path, raising=False)

    def boom():
        raise RuntimeError("oops")

    monkeypatch.setattr(worker, "approve_all", boom)
    monkeypatch.setattr(api, "approve_all", boom)
    resp = client.post("/approve", headers={"Hx-Request": "1"})
    assert resp.status_code == 500
    assert "oops" in resp.text
    assert "oops" in log_path.read_text()


def test_approve_non_hx_redirect(monkeypatch):
    monkeypatch.setattr(worker, "approve_all", lambda: None)
    resp = client.post("/approve")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_approve_selected_hx_triggers_refresh(monkeypatch):
    monkeypatch.setattr(worker, "approve_selected", lambda tracks: None)
    monkeypatch.setattr(api, "worker_approve_selected", worker.approve_selected)
    resp = client.post(
        "/approve-selected",
        data=[("track", f"a{worker.AUDIO_EXT}"), ("track", f"b{worker.AUDIO_EXT}")],
        headers={"Hx-Request": "1"},
    )
    assert resp.status_code == 204
    assert resp.headers["HX-Trigger"] == "refreshStaging"


def test_approve_selected_hx_error_returns_message(monkeypatch, tmp_path):
    log_path = tmp_path / "errors.log"
    monkeypatch.setattr(api, "ERROR_LOG_PATH", log_path, raising=False)

    def boom(tracks=None):
        raise RuntimeError("oops")

    monkeypatch.setattr(worker, "approve_selected", boom)
    monkeypatch.setattr(api, "worker_approve_selected", boom)
    resp = client.post(
        "/approve-selected",
        data=[("track", f"a{worker.AUDIO_EXT}")],
        headers={"Hx-Request": "1"},
    )
    assert resp.status_code == 500
    assert "oops" in resp.text
    assert "Tracks: ['a" in log_path.read_text()


def test_approve_selected_non_hx_redirect(monkeypatch):
    monkeypatch.setattr(worker, "approve_selected", lambda tracks: None)
    resp = client.post(
        "/approve-selected",
        data=[("track", f"a{worker.AUDIO_EXT}")],
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_rip_non_hx_error_returns_stack(monkeypatch, tmp_path):
    log_path = tmp_path / "errors.log"
    monkeypatch.setattr(api, "ERROR_LOG_PATH", log_path, raising=False)

    def boom(url):
        raise RuntimeError("boom")

    monkeypatch.setattr(worker, "rip_playlist", boom)
    monkeypatch.setattr(api, "rip_playlist", boom)
    with pytest.raises(api.HTTPException) as excinfo:
        client.post("/rip", data={"youtube_url": "http://x"})
    assert "RuntimeError: boom" in excinfo.value.detail
    assert "RuntimeError: boom" in log_path.read_text()


def test_rip_hx_error_returns_stack(monkeypatch, tmp_path):
    log_path = tmp_path / "errors.log"
    monkeypatch.setattr(api, "ERROR_LOG_PATH", log_path, raising=False)

    def boom(url):
        raise RuntimeError("boom")

    monkeypatch.setattr(worker, "rip_playlist", boom)
    monkeypatch.setattr(api, "rip_playlist", boom)
    resp = client.post(
        "/rip",
        data={"youtube_url": "http://x"},
        headers={"Hx-Request": "1"},
    )
    assert resp.status_code == 500
    assert "RuntimeError: boom" in resp.text
    assert "RuntimeError: boom" in log_path.read_text()


def test_error_log_endpoint_serves_file(monkeypatch, tmp_path):
    log_path = tmp_path / "errors.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("log contents")
    monkeypatch.setattr(api, "ERROR_LOG_PATH", log_path, raising=False)
    resp = client.get("/logs/error")
    assert resp.status_code == 200
    assert resp.text == "log contents"


def test_error_log_endpoint_returns_404_when_missing(monkeypatch, tmp_path):
    log_path = tmp_path / "errors.log"
    if log_path.exists():
        log_path.unlink()
    monkeypatch.setattr(api, "ERROR_LOG_PATH", log_path, raising=False)
    with pytest.raises(api.HTTPException) as excinfo:
        client.get("/logs/error")
    assert excinfo.value.status_code == 404


def test_index_template_has_error_log_link():
    template_path = os.path.join(os.path.dirname(__file__), "..", "src", "songripper", "templates", "index.html")
    with open(template_path) as fh:
        html = fh.read()
    assert "View error log" in html
    assert "No errors logged yet." in html


def test_rip_form_has_afterrequest_handler():
    template_path = os.path.join(os.path.dirname(__file__), "..", "src", "songripper", "templates", "index.html")
    with open(template_path) as fh:
        html = fh.read()
    assert "hx-on:afterRequest" in html


def test_edit_multiple_updates_fields(monkeypatch):
    calls = []

    def fake_update(fp, field, val):
        calls.append((fp, field, val))
        return f"{fp}:{field}"

    monkeypatch.setattr(api.worker, "update_track", fake_update)

    art_calls = []

    def fake_update_art(fp, data, mime):
        art_calls.append((fp, data, mime))

    monkeypatch.setattr(api.worker, "update_album_art", fake_update_art)

    class DummyUpload:
        def __init__(self, data=b"img"):
            self.file = types.SimpleNamespace(read=lambda: data)
            self.filename = "cover.png"
            self.content_type = "image/png"

    data = [
        ("track", f"file{worker.AUDIO_EXT}"),
        ("artist_value", "A"),
        ("artist_enable", "on"),
        ("album_value", "B"),
        ("album_enable", "on"),
        ("title_value", ""),
        ("title_enable", ""),
        ("art_enable", "on"),
    ]
    files = {"art_file": ("cover.png", b"img", "image/png")}
    resp = client.post(
        "/edit-multiple",
        data=data,
        files=files,
        headers={"Hx-Request": "1"},
    )
    assert resp.status_code == 204
    assert resp.headers["HX-Trigger"] == "refreshStaging"
    assert calls == [
        (f"file{worker.AUDIO_EXT}", "artist", "A"),
        (f"file{worker.AUDIO_EXT}:artist", "album", "B"),
    ]
    assert art_calls == [(f"file{worker.AUDIO_EXT}:artist:album", b"img", "image/png")]


def test_edit_handles_missing_file(monkeypatch):
    def fake_update(fp, field, val):
        raise worker.TrackUpdateError("not found")

    monkeypatch.setattr(api.worker, "update_track", fake_update)
    resp = client.put(
        "/edit",
        data={"filepath": f"x{worker.AUDIO_EXT}", "field": "artist", "value": "A"},
    )
    assert resp.status_code == 400
    assert "not found" in resp.text


def test_edit_returns_new_path_and_trigger(monkeypatch):
    def fake_update(fp, field, val):
        return Path(f"/new/location{worker.AUDIO_EXT}")

    monkeypatch.setattr(api.worker, "update_track", fake_update)
    resp = client.put(
        "/edit",
        data={"filepath": f"x{worker.AUDIO_EXT}", "field": "artist", "value": "A"},
    )
    assert resp.headers["HX-Trigger"] == "refreshStaging"
    assert f"hx-get=\"/edit?filepath=/new/location{worker.AUDIO_EXT}&field=artist\"" in resp.text


def test_edit_multiple_handles_missing_file(monkeypatch):
    def fake_update(fp, field, val):
        raise worker.TrackUpdateError("bad")

    monkeypatch.setattr(api.worker, "update_track", fake_update)
    data = [
        ("track", f"song{worker.AUDIO_EXT}"),
        ("artist_value", "A"),
        ("artist_enable", "on"),
        ("album_value", ""),
        ("album_enable", ""),
        ("title_value", ""),
        ("title_enable", ""),
    ]
    resp = client.post(
        "/edit-multiple",
        data=data,
        headers={"Hx-Request": "1"},
    )
    assert resp.status_code == 400
    assert "bad" in resp.text


def test_staging_template_has_multi_edit_form():
    path = os.path.join(
        os.path.dirname(__file__), "..", "src", "songripper", "templates", "staging.html"
    )
    with open(path) as fh:
        html = fh.read()
    assert "Edit Track(s)" in html
    assert "hx-post=\"/edit-multiple\"" in html
    assert 'id="edit-btn"' in html


def test_staging_template_has_album_art_field():
    path = os.path.join(
        os.path.dirname(__file__), "..", "src", "songripper", "templates", "staging.html"
    )
    with open(path) as fh:
        html = fh.read()
    assert 'name="art_file"' in html
    assert 'name="art_enable"' in html


def test_staging_template_uses_multipart_encoding():
    path = os.path.join(
        os.path.dirname(__file__), "..", "src", "songripper", "templates", "staging.html"
    )
    with open(path) as fh:
        html = fh.read()
    assert 'hx-encoding="multipart/form-data"' in html


def test_staging_template_approve_form_targets_alerts():
    path = os.path.join(
        os.path.dirname(__file__), "..", "src", "songripper", "templates", "staging.html"
    )
    with open(path) as fh:
        html = fh.read()
    assert 'hx-post="/approve"' in html
    assert 'hx-post="/approve-selected"' in html
    assert 'hx-target="#alerts"' in html


def test_staging_template_has_select_all_checkbox():
    path = os.path.join(
        os.path.dirname(__file__), "..", "src", "songripper", "templates", "staging.html"
    )
    with open(path) as fh:
        html = fh.read()
    assert 'id="select-all"' in html
    assert "Select All" in html


def test_staging_template_shows_no_tracks_message():
    path = os.path.join(
        os.path.dirname(__file__), "..", "src", "songripper", "templates", "staging.html"
    )
    with open(path) as fh:
        html = fh.read()
    assert "No tracks found" in html
    assert 'id="no-tracks"' in html


def test_check_endpoint_hx(monkeypatch):
    monkeypatch.setattr(worker, "find_matching_tracks", lambda fp: [f"/a{worker.AUDIO_EXT}"])
    resp = client.get("/check", params={"filepath": f"file{worker.AUDIO_EXT}"}, headers={"Hx-Request": "1"})
    assert resp.status_code == 200
    assert "Possible matches" in resp.text


def test_check_endpoint_redirect(monkeypatch):
    monkeypatch.setattr(worker, "find_matching_tracks", lambda fp: [])
    resp = client.get("/check", params={"filepath": f"file{worker.AUDIO_EXT}"})
    assert resp.status_code == 303
    assert "msg=No+matches+found" in resp.headers["location"]


def test_staging_template_has_check_button():
    path = os.path.join(
        os.path.dirname(__file__), "..", "src", "songripper", "templates", "staging.html"
    )
    with open(path) as fh:
        html = fh.read()
    assert "hx-get=\"/check" in html
    assert "hx-target=\"#alerts\"" in html
