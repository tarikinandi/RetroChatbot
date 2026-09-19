from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import storage
from app.config import BASE_DIR, DATA_DIR

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/", response_class=HTMLResponse)
def get_index(request: Request):
    counter = storage.increment_counter(DATA_DIR)
    history = storage.get_chat_history(DATA_DIR)
    era = storage.get_era(DATA_DIR)
    return templates.TemplateResponse(
        request,
        "index.html",
        {"history": history, "counter": counter, "era": era},
    )


@router.get("/guestbook", response_class=HTMLResponse)
def get_guestbook(request: Request):
    entries = storage.get_guestbook_entries(DATA_DIR)
    era = storage.get_era(DATA_DIR)
    return templates.TemplateResponse(
        request, "guestbook.html", {"entries": entries, "era": era}
    )


@router.post("/guestbook")
def post_guestbook(name: str = Form(...), message: str = Form(...)):
    storage.add_guestbook_entry(DATA_DIR, name, message)
    return RedirectResponse(url="/guestbook", status_code=303)


@router.post("/toggle-era")
def post_toggle_era(request: Request):
    storage.toggle_era(DATA_DIR)
    referer = request.headers.get("referer")
    return RedirectResponse(url=referer or "/", status_code=303)


@router.get("/about", response_class=HTMLResponse)
def get_about(request: Request):
    era = storage.get_era(DATA_DIR)
    return templates.TemplateResponse(request, "about.html", {"era": era})
