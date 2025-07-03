# src/songripper/api.py
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from pathlib import Path
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from .worker import (
    rip_playlist,
    approve_all,
    approve_selected as worker_approve_selected,
    delete_staging,
    staging_has_files,
    list_staged_tracks,
    TrackUpdateError,
)
from .settings import CACHE_BUSTER
from . import PACKAGE_TIME
from . import worker
app = FastAPI()

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

app.mount("/static", StaticFiles(directory="src/songripper/static"), name="static")
templates = Jinja2Templates(directory="src/songripper/templates")

@app.get("/", response_class=HTMLResponse)
def home(req: Request, msg: str | None = None):
    context = {
        "request": req,
        "message": msg,
        "v": CACHE_BUSTER,
        "updated": PACKAGE_TIME,
        "has_staged_files": staging_has_files(),
    }
    return templates.TemplateResponse("index.html", context)

@app.post("/rip")
def rip(request: Request, youtube_url: str = Form(...)):
    rip_playlist(youtube_url)
    if request.headers.get("Hx-Request"):
        return HTMLResponse("", status_code=204, headers={"HX-Trigger": "refreshStaging"})
    return RedirectResponse("/", status_code=303)

@app.post("/approve")
def approve(request: Request):
    try:
        approve_all()
    except Exception as exc:
        if request.headers.get("Hx-Request"):
            context = {"request": request, "message": str(exc)}
            return templates.TemplateResponse("message.html", context, status_code=500)
        raise HTTPException(status_code=500, detail=str(exc))
    if request.headers.get("Hx-Request"):
        return HTMLResponse("", status_code=204, headers={"HX-Trigger": "refreshStaging"})
    return RedirectResponse("/", status_code=303)


@app.post("/approve-selected")
def approve_selected(request: Request, track: list[str] = Form([])):
    try:
        worker_approve_selected(track)
    except Exception as exc:
        if request.headers.get("Hx-Request"):
            context = {"request": request, "message": str(exc)}
            return templates.TemplateResponse("message.html", context, status_code=500)
        raise HTTPException(status_code=500, detail=str(exc))
    if request.headers.get("Hx-Request"):
        return HTMLResponse("", status_code=204, headers={"HX-Trigger": "refreshStaging"})
    return RedirectResponse("/", status_code=303)

@app.post("/delete")
def delete(request: Request):
    deleted = delete_staging()
    if deleted:
        msg = "Files deleted"
    else:
        msg = "No files in staging"
    if request.headers.get("Hx-Request"):
        context = {"request": request, "message": msg}
        response = templates.TemplateResponse("message.html", context)
        if deleted:
            response.headers["HX-Trigger-After-Swap"] = "refreshStaging"
        return response
    return RedirectResponse(f"/?msg={msg.replace(' ', '+')}", status_code=303)


@app.get("/staging", response_class=HTMLResponse)
def staging(req: Request):
    tracks = list_staged_tracks()
    context = {"request": req, "tracks": tracks}
    return templates.TemplateResponse("staging.html", context)

@app.get("/edit", response_class=HTMLResponse)
def edit_form(filepath: str, field: str):
    tags = worker.read_tags(filepath)
    value = tags.get(field, "")
    html = (
        "<td><form hx-put=\"/edit\" hx-target=\"closest td\" hx-swap=\"outerHTML\">"
        f"<input type=\"text\" name=\"value\" value=\"{value}\" autofocus>"
        f"<input type=\"hidden\" name=\"filepath\" value=\"{filepath}\">"
        f"<input type=\"hidden\" name=\"field\" value=\"{field}\">"
        "</form></td>"
    )
    return HTMLResponse(html)


@app.put("/edit")
def edit(filepath: str = Form(...), field: str = Form(...), value: str = Form(...)):
    try:
        new_path = worker.update_track(filepath, field, value)
    except TrackUpdateError as exc:
        html = f"<td>{exc}</td>"
        return HTMLResponse(html, status_code=400)
    headers = {"HX-Trigger": "refreshStaging"}
    html = (
        f'<td hx-get="/edit?filepath={new_path}&field={field}" '
        'hx-trigger="click" hx-target="this" hx-swap="outerHTML">'
        f'{value}</td>'
    )
    return HTMLResponse(html, headers=headers)


@app.post("/edit-multiple")
def edit_multiple(
    request: Request,
    track: list[str] = Form([]),
    artist_value: str = Form(""),
    artist_enable: str | None = Form(None),
    album_value: str = Form(""),
    album_enable: str | None = Form(None),
    title_value: str = Form(""),
    title_enable: str | None = Form(None),
    art_file: UploadFile | None = File(None),
    art_enable: str | None = Form(None),
):
    art_bytes = None
    art_mime = "image/jpeg"
    if art_enable and art_file is not None and art_file.filename:
        art_bytes = art_file.file.read()
        art_mime = art_file.content_type or "image/jpeg"
    for path in track:
        p = path
        if artist_enable:
            try:
                p = str(worker.update_track(p, "artist", artist_value))
            except TrackUpdateError as exc:
                return HTMLResponse(str(exc), status_code=400)
        if album_enable:
            try:
                p = str(worker.update_track(p, "album", album_value))
            except TrackUpdateError as exc:
                return HTMLResponse(str(exc), status_code=400)
        if title_enable:
            try:
                p = str(worker.update_track(p, "title", title_value))
            except TrackUpdateError as exc:
                return HTMLResponse(str(exc), status_code=400)
        if art_enable and art_bytes is not None:
            try:
                worker.update_album_art(p, art_bytes, art_mime)
            except TrackUpdateError as exc:
                return HTMLResponse(str(exc), status_code=400)
    if request.headers.get("Hx-Request"):
        resp = HTMLResponse("", status_code=204)
        resp.headers["HX-Trigger"] = "refreshStaging"
        return resp
    return RedirectResponse("/", status_code=303)


@app.get("/check")
def check_duplicates(request: Request, filepath: str):
    matches = worker.find_matching_tracks(filepath)
    if matches:
        names = ", ".join(Path(m).name for m in matches)
        msg = f"Possible matches: {names}"
    else:
        msg = "No matches found"
    if request.headers.get("Hx-Request"):
        context = {"request": request, "message": msg}
        return templates.TemplateResponse("message.html", context)
    return RedirectResponse(f"/?msg={msg.replace(' ', '+')}", status_code=303)
