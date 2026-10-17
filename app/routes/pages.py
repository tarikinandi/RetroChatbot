from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import security, storage
from app.config import BASE_DIR, DATA_DIR

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

ERAS = ("1996", "2030")


def _page_context(request: Request) -> dict:
    """Demo: era comes from ?era= or a cookie, never from shared state."""
    demo = security.demo_mode()
    if demo:
        era = request.query_params.get("era") or request.cookies.get("era")
        era = era if era in ERAS else "1996"
    else:
        era = storage.get_era(DATA_DIR)
    return {"era": era, "demo": demo}


def _render(request: Request, name: str, extra: dict | None = None):
    context = _page_context(request) | (extra or {})
    response = templates.TemplateResponse(request, name, context)
    if context["demo"] and request.query_params.get("era") in ERAS:
        response.set_cookie(
            "era", context["era"], max_age=86400, samesite="lax", httponly=True,
            secure=request.url.scheme == "https",
        )
    return response


def _require_local() -> None:
    if security.demo_mode():
        raise HTTPException(status_code=404)


@router.get("/", response_class=HTMLResponse)
def get_index(request: Request):
    if security.demo_mode():
        return _render(request, "index.html", {"history": [], "counter": None})
    counter = storage.increment_counter(DATA_DIR)
    history = storage.get_chat_history(DATA_DIR)
    return _render(request, "index.html", {"history": history, "counter": counter})


@router.get("/guestbook", response_class=HTMLResponse)
def get_guestbook(request: Request):
    _require_local()
    entries = storage.get_guestbook_entries(DATA_DIR)
    return _render(request, "guestbook.html", {"entries": entries})


@router.post("/guestbook")
def post_guestbook(name: str = Form(...), message: str = Form(...)):
    _require_local()
    storage.add_guestbook_entry(DATA_DIR, name, message)
    return RedirectResponse(url="/guestbook", status_code=303)


@router.post("/toggle-era")
def post_toggle_era():
    _require_local()
    storage.toggle_era(DATA_DIR)
    # Fixed target: never redirect to a client-supplied Referer.
    return RedirectResponse(url="/", status_code=303)


@router.get("/about", response_class=HTMLResponse)
def get_about(request: Request):
    return _render(request, "about.html")
