import os
import sys
import types
from pathlib import Path

# Provide a minimal fastapi stub so the module under test can be imported
fastapi = types.ModuleType("fastapi")

class FastAPI:
    def __init__(self):
        pass

    def middleware(self, *args, **kwargs):
        def deco(fn):
            return fn
        return deco

    def mount(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        def deco(fn):
            return fn
        return deco

    def post(self, *args, **kwargs):
        def deco(fn):
            return fn
        return deco

    def put(self, *args, **kwargs):
        def deco(fn):
            return fn
        return deco

fastapi.FastAPI = FastAPI
fastapi.Form = lambda *a, **kw: None
fastapi.File = lambda *a, **kw: None
fastapi.UploadFile = object
class Request:
    def __init__(self, headers=None):
        self.headers = headers or {}
fastapi.Request = Request
class BackgroundTasks:
    pass
fastapi.BackgroundTasks = BackgroundTasks

responses = types.ModuleType("fastapi.responses")
class HTMLResponse:
    def __init__(self, content="", status_code=200, headers=None):
        self.text = content
        self.status_code = status_code
        self.headers = headers or {}
class RedirectResponse(HTMLResponse):
    def __init__(self, url, status_code=307):
        super().__init__("", status_code)
        self.headers["location"] = url
responses.HTMLResponse = HTMLResponse
responses.RedirectResponse = RedirectResponse
fastapi.responses = responses

templating = types.ModuleType("fastapi.templating")
class Jinja2Templates:
    def __init__(self, directory):
        self.directory = directory
    def TemplateResponse(self, name, context):
        return HTMLResponse(context.get("message", ""))
templating.Jinja2Templates = Jinja2Templates
fastapi.templating = templating

staticfiles = types.ModuleType("fastapi.staticfiles")
class StaticFiles:
    def __init__(self, directory, name=None):
        pass
staticfiles.StaticFiles = StaticFiles
fastapi.staticfiles = staticfiles

sys.modules.setdefault("fastapi", fastapi)
sys.modules.setdefault("fastapi.responses", responses)
sys.modules.setdefault("fastapi.templating", templating)
sys.modules.setdefault("fastapi.staticfiles", staticfiles)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import songripper.api as api
import songripper.worker as worker


def test_delete_hx_success(monkeypatch):
    monkeypatch.setattr(worker, "delete_staging", lambda: True)
    monkeypatch.setattr(api, "delete_staging", lambda: True)
    req = types.SimpleNamespace(headers={"Hx-Request": "true"})
    resp = api.delete(req)
    assert resp.headers.get("HX-Trigger-After-Swap") == "refreshStaging"
    assert resp.text == "Files deleted"


def test_delete_hx_failure_no_trigger(monkeypatch):
    monkeypatch.setattr(worker, "delete_staging", lambda: False)
    monkeypatch.setattr(api, "delete_staging", lambda: False)
    req = types.SimpleNamespace(headers={"Hx-Request": "1"})
    resp = api.delete(req)
    assert "HX-Trigger-After-Swap" not in resp.headers
    assert resp.text == "No files in staging"


def test_delete_non_hx_redirect(monkeypatch):
    monkeypatch.setattr(worker, "delete_staging", lambda: True)
    monkeypatch.setattr(api, "delete_staging", lambda: True)
    req = types.SimpleNamespace(headers={})
    resp = api.delete(req)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/?msg=Files+deleted"


def test_approve_hx_triggers_refresh(monkeypatch):
    monkeypatch.setattr(worker, "approve_all", lambda: None)
    req = types.SimpleNamespace(headers={"Hx-Request": "1"})
    resp = api.approve(req)
    assert resp.status_code == 204
    assert resp.headers["HX-Trigger"] == "refreshStaging"


def test_approve_non_hx_redirect(monkeypatch):
    monkeypatch.setattr(worker, "approve_all", lambda: None)
    req = types.SimpleNamespace(headers={})
    resp = api.approve(req)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


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

    req = types.SimpleNamespace(headers={"Hx-Request": "1"})
    resp = api.edit_multiple(
        req,
        track=["file.mp3"],
        artist_value="A",
        artist_enable="on",
        album_value="B",
        album_enable="on",
        title_value="",
        title_enable=None,
        art_file=DummyUpload(),
        art_enable="on",
    )
    assert resp.status_code == 204
    assert resp.headers["HX-Trigger"] == "refreshStaging"
    assert calls == [
        ("file.mp3", "artist", "A"),
        ("file.mp3:artist", "album", "B"),
    ]
    assert art_calls == [("file.mp3:artist:album", b"img", "image/png")]


def test_edit_handles_missing_file(monkeypatch):
    def fake_update(fp, field, val):
        raise worker.TrackUpdateError("not found")

    monkeypatch.setattr(api.worker, "update_track", fake_update)
    resp = api.edit(filepath="x.mp3", field="artist", value="A")
    assert resp.status_code == 400
    assert "not found" in resp.text


def test_edit_returns_new_path_and_trigger(monkeypatch):
    def fake_update(fp, field, val):
        return Path("/new/location.mp3")

    monkeypatch.setattr(api.worker, "update_track", fake_update)
    resp = api.edit(filepath="x.mp3", field="artist", value="A")
    assert resp.headers["HX-Trigger"] == "refreshStaging"
    assert "hx-get=\"/edit?filepath=/new/location.mp3&field=artist\"" in resp.text


def test_edit_multiple_handles_missing_file(monkeypatch):
    def fake_update(fp, field, val):
        raise worker.TrackUpdateError("bad")

    monkeypatch.setattr(api.worker, "update_track", fake_update)
    req = types.SimpleNamespace(headers={"Hx-Request": "1"})
    resp = api.edit_multiple(
        req,
        track=["song.mp3"],
        artist_value="A",
        artist_enable="on",
        album_value="",
        album_enable=None,
        title_value="",
        title_enable=None,
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
