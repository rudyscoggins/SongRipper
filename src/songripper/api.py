# src/songripper/api.py
from fastapi import FastAPI, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from .worker import rip_playlist, approve_all, delete_staging
app = FastAPI()
templates = Jinja2Templates(directory="src/songripper/templates")

@app.get("/", response_class=HTMLResponse)
def home(req: Request, msg: str | None = None):
    context = {"request": req, "message": msg}
    return templates.TemplateResponse("index.html", context)

@app.post("/rip")
def rip(playlist_url: str = Form(...), bg: BackgroundTasks = None):
    bg.add_task(rip_playlist, playlist_url)
    return RedirectResponse("/", status_code=303)

@app.post("/approve")
def approve():
    approve_all()
    return RedirectResponse("/", status_code=303)

@app.post("/delete")
def delete():
    delete_staging()
    return RedirectResponse("/?msg=Files+successfully+deleted", status_code=303)
