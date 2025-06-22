# src/songripper/api.py
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from .worker import (
    rip_playlist,
    approve_all,
    delete_staging,
    staging_has_files,
    list_staged_tracks,
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
def rip(request: Request, playlist_url: str = Form(...)):
    rip_playlist(playlist_url)
    if request.headers.get("Hx-Request"):
        return HTMLResponse("", status_code=204, headers={"HX-Trigger": "refreshStaging"})
    return RedirectResponse("/", status_code=303)

@app.post("/approve")
def approve():
    approve_all()
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
    new_path = worker.update_track(filepath, field, value)
    headers = {"HX-Trigger": "refreshStaging"}
    html = (
        f'<td hx-get="/edit?filepath={new_path}&field={field}" '
        'hx-trigger="click" hx-target="this" hx-swap="outerHTML">'
        f'{value}</td>'
    )
    return HTMLResponse(html, headers=headers)
