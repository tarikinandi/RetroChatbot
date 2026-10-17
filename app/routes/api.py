import logging
import os
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, BaseModel, Field

from app import gemini_client, security, storage
from app.config import DATA_DIR, get_models

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_TEXT = 500
MAX_HISTORY = 10

FALLBACK_ERROR_MESSAGE_1996 = (
    "⚠ BAGLANTI KOPTU ⚠ Modeminizi kontrol edip birazdan tekrar "
    "deneyin..."
)

FALLBACK_ERROR_MESSAGE_2030 = (
    "⚠ NÖRAL BAĞLANTI KESİLDİ ⚠ Kuantum ağı senkronize ediliyor, "
    "birazdan tekrar deneyin..."
)

KEY_PROBLEM_MESSAGES = {
    "1996": "⚠ ANAHTAR SORUNU ⚠ Santralin sifresi gecersiz, demo sahibi hatti duzeltene kadar sus...",
    "2030": "⚠ ANAHTAR SORUNU ⚠ Hologram çekirdeğinin kimliği geçersiz, demo sahibi düzeltene kadar bekle...",
}
QUOTA_MESSAGES = {
    "1996": "⚠ KOTA DOLDU ⚠ Santral simdilik dolu, birazdan tekrar dene...",
    "2030": "⚠ KOTA DOLDU ⚠ Kuantum kanalı şimdilik tıkandı, birazdan tekrar dene...",
}
# error code -> (HTTP status, messages by era); anything else is the generic 502.
ERROR_CODES = {
    "key_problem": (503, KEY_PROBLEM_MESSAGES),
    "quota": (429, QUOTA_MESSAGES),
}

RATE_LIMIT_MESSAGES = {
    "1996": "⚠ HAT MESGUL ⚠ Cok hizli yazdin, modem soguyana kadar bir dakika bekle...",
    "2030": "⚠ NÖRAL YÜK AŞIMI ⚠ Çok hızlı aktardın, kanal soğuyana kadar bir dakika bekle...",
}
DAILY_CAP_MESSAGES = {
    "1996": "⚠ SANTRAL DOLU ⚠ Bugunluk gorusme kotasi doldu, yarin tekrar ara...",
    "2030": "⚠ KUANTUM KOTA DOLU ⚠ Bugünlük zaman yolculuğu kotası bitti, yarın tekrar dene...",
}
NOT_CONFIGURED_MESSAGES = {
    "1996": "⚠ DEMO HENUZ HAZIR DEGIL ⚠ Santral kurulumu suruyor, sonra tekrar ara...",
    "2030": "⚠ DEMO HENÜZ YAPILANDIRILMADI ⚠ Hologram çekirdeği hazırlanıyor, sonra tekrar dene...",
}


def _clean_and_check(value: str) -> str:
    cleaned = security.clean_text(value)
    if not 1 <= len(cleaned) <= MAX_TEXT:
        raise ValueError("text must be 1..500 characters")
    return cleaned


CleanText = Annotated[str, Field(max_length=MAX_TEXT), AfterValidator(_clean_and_check)]


class HistoryItem(BaseModel):
    role: Literal["user", "model"]
    text: CleanText


class ChatRequest(BaseModel):
    message: CleanText
    # Demo mode only: the browser owns the conversation and the era choice.
    history: list[HistoryItem] = Field(default_factory=list, max_length=MAX_HISTORY)
    era: Literal["1996", "2030"] | None = None


class ChatResponse(BaseModel):
    reply: str


def require_allowed_origin(request: Request) -> None:
    if not security.demo_mode():
        return
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if not security.origin_allowed(request.headers.get("origin"), host):
        raise HTTPException(status_code=403, detail="Origin not allowed")


def _error(status: int, messages: dict, era: str, code: str | None = None) -> JSONResponse:
    body = {"reply": messages[era]}
    if code:
        body["error"] = code
    return JSONResponse(body, status_code=status)


def _post_chat_demo(request: Request, payload: ChatRequest):
    era = payload.era or "1996"

    if not os.environ.get("GEMINI_API_KEY"):
        return _error(503, NOT_CONFIGURED_MESSAGES, era)

    peer = request.client.host if request.client else None
    key = security.client_key(request.headers.get("x-forwarded-for"), peer)
    verdict = security.limiter.check(key)
    if verdict == "ip":
        return _error(429, RATE_LIMIT_MESSAGES, era)
    if verdict == "daily":
        return _error(429, DAILY_CAP_MESSAGES, era)

    history = [item.model_dump() for item in payload.history]
    try:
        reply = gemini_client.generate_reply(history, payload.message, era)
    except gemini_client.GeminiRequestError as exc:
        code = getattr(exc, "code", "model_unavailable")
        logger.error("Demo chat istegi Gemini hatasi nedeniyle basarisiz oldu: %s", code)
        status, messages = ERROR_CODES.get(
            code,
            (502, {"1996": FALLBACK_ERROR_MESSAGE_1996, "2030": FALLBACK_ERROR_MESSAGE_2030}),
        )
        return _error(status, messages, era, code)
    return ChatResponse(reply=reply)


@router.post(
    "/api/chat",
    response_model=ChatResponse,
    dependencies=[Depends(require_allowed_origin)],
)
def post_chat(request: Request, payload: ChatRequest):
    if security.demo_mode():
        return _post_chat_demo(request, payload)

    era = storage.get_era(DATA_DIR)
    history = storage.get_chat_history(DATA_DIR)
    storage.append_chat_message(DATA_DIR, "user", payload.message)

    try:
        reply = gemini_client.generate_reply(history, payload.message, era)
    except gemini_client.GeminiRequestError:
        logger.error("Chat istegi Gemini hatasi nedeniyle basarisiz oldu")
        reply = (
            FALLBACK_ERROR_MESSAGE_2030
            if era == "2030"
            else FALLBACK_ERROR_MESSAGE_1996
        )

    storage.append_chat_message(DATA_DIR, "model", reply)
    return ChatResponse(reply=reply)


@router.get("/api/health")
def get_health():
    """Safe diagnostic: no secrets, no upstream error text, no Google calls."""
    return JSONResponse(
        {
            "ok": True,
            "demo": security.demo_mode(),
            "configured": bool(os.environ.get("GEMINI_API_KEY")),
            "models": get_models(),
        },
        headers={"Cache-Control": "no-store"},
    )
