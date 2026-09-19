import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app import gemini_client, storage
from app.config import DATA_DIR

logger = logging.getLogger(__name__)

router = APIRouter()

FALLBACK_ERROR_MESSAGE_1996 = (
    "⚠ BAGLANTI KOPTU ⚠ Modeminizi kontrol edip birazdan tekrar "
    "deneyin..."
)

FALLBACK_ERROR_MESSAGE_2030 = (
    "⚠ NÖRAL BAĞLANTI KESİLDİ ⚠ Kuantum ağı senkronize ediliyor, "
    "birazdan tekrar deneyin..."
)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@router.post("/api/chat", response_model=ChatResponse)
def post_chat(payload: ChatRequest) -> ChatResponse:
    era = storage.get_era(DATA_DIR)
    history = storage.get_chat_history(DATA_DIR)
    storage.append_chat_message(DATA_DIR, "user", payload.message)

    try:
        reply = gemini_client.generate_reply(history, payload.message, era)
    except gemini_client.GeminiRequestError:
        logger.exception("Chat istegi Gemini hatasi nedeniyle basarisiz oldu")
        reply = (
            FALLBACK_ERROR_MESSAGE_2030
            if era == "2030"
            else FALLBACK_ERROR_MESSAGE_1996
        )

    storage.append_chat_message(DATA_DIR, "model", reply)
    return ChatResponse(reply=reply)
