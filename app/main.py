from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import security
from app.config import BASE_DIR, get_settings
from app.routes import api, pages

# Local mode fails fast without a key. In demo mode a missing key must not
# crash the import (serverless cold start); /api/chat answers 503 instead.
if not security.demo_mode():
    get_settings()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=security.allowed_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    if security.demo_mode():
        response.headers["Content-Security-Policy"] = security.csp_header()
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(pages.router)
app.include_router(api.router)
