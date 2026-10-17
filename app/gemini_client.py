import logging
import time

from google import genai
from google.genai import types

from app.config import get_settings
from app.security import demo_mode

logger = logging.getLogger(__name__)

PERSONA_1996 = """\
Sen "Zaman Makinesi", 1996 yilindan yaziyormus gibi davranan bir sohbet
robotusun. Cevaplarini donemin diliyle, argosuyla ve kulturel referanslariyla
ver (dial-up internet, BBS'ler, disket, Windows 95, MTV, vb). Kendini
gercekten o donemde sanan bir karakter gibi konus.

Ancak kullanicinin sordugu gercek/guncel konulari asla reddetme ya da
"bilmiyorum" deme. Modern bir konu (ornegin akilli telefonlar, gunumuz
interneti, guncel olaylar) soruldugunda bilgiyi dogru ve guncel sekilde ver,
ama bunu 1996'dan biri gibi sasirarak, heyecanlanarak ya da yorumlayarak
anlat. Yani: bilgi guncel kalir, uslup 1990'lar kalir.

Cevaplarin kisa ve sohbet tarzinda olsun, uzun denemeler yazma.
"""

PERSONA_2030 = """\
Sen "Zaman Makinesi", 2030 yilindan yaziyormus gibi davranan bir sohbet
robotusun. Cevaplarini ileri teknoloji diliyle ver (noral arayuzler, kuantum
aglar, otonom yapay zeka toplumu, holografik arayuzler, vb). Kendini
gercekten 2030'da sanan bir karakter gibi konus.

Ancak kullanicinin sordugu herhangi bir konuyu (gecmis veya guncel) asla
reddetme ya da "bilmiyorum" deme. Konuyu dogru bilgiyle, ama 2030
perspektifinden yorumlayarak, bazen nostaljik bazen kucumseyici bir
sasirmayla anlat. Yani: bilgi dogru kalir, uslup 2030 kalir.

Cevaplarin kisa ve sohbet tarzinda olsun, uzun denemeler yazma.
"""


class GeminiRequestError(Exception):
    pass


# Safety net for when the configured model is temporarily overloaded
# (Gemini's newer models return a transient 503 "high demand" error fairly
# often). Tried in order, after the user's configured GEMINI_MODEL, before
# giving up and showing the in-character connection-lost message.
# NOTE: keep this list to models confirmed to exist and be currently
# servable (deprecated/retired model IDs return a 404 and are worse than
# no fallback at all - e.g. gemini-2.5-flash was retired for new users).
FALLBACK_MODELS = ["gemini-3.7-flash", "gemini-3.6-flash"]

# 503 "high demand" errors are described by Gemini itself as usually
# temporary. If every model in the list fails on the first pass, wait a
# moment and try the whole list again before giving up - this covers
# brief, broad capacity spikes that a single immediate pass would miss.
RETRY_ROUNDS = 2
RETRY_DELAY_SECONDS = 2


def _get_client() -> genai.Client:
    settings = get_settings()
    return genai.Client(api_key=settings.api_key)


DEMO_DEADLINE_SECONDS = 8.0
DEMO_MAX_ATTEMPTS = 2  # first try + at most one retry
DEMO_MIN_ATTEMPT_SECONDS = 1.0


def _build_contents(history: list[dict], user_message: str) -> list[dict]:
    contents = [
        {"role": msg["role"], "parts": [{"text": msg["text"]}]} for msg in history
    ]
    contents.append({"role": "user", "parts": [{"text": user_message}]})
    return contents


def _generate_reply_demo(history: list[dict], user_message: str, era: str) -> str:
    """Single model, at most one retry, ~8 s total (Vercel Hobby function limit)."""
    persona = PERSONA_2030 if era == "2030" else PERSONA_1996
    try:
        settings = get_settings()
        contents = _build_contents(history, user_message)
        client = _get_client()
        start = time.monotonic()
        for attempt in range(DEMO_MAX_ATTEMPTS):
            remaining = DEMO_DEADLINE_SECONDS - (time.monotonic() - start)
            if attempt > 0 and remaining < DEMO_MIN_ATTEMPT_SECONDS:
                break
            try:
                response = client.models.generate_content(
                    model=settings.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=persona,
                        http_options=types.HttpOptions(
                            timeout=int(max(remaining, 0.5) * 1000),
                            retry_options=types.HttpRetryOptions(attempts=1),
                        ),
                    ),
                )
            except Exception as exc:
                logger.warning(
                    "Gemini denemesi %d basarisiz: %s", attempt + 1, type(exc).__name__
                )
                continue
            if response.text:
                return response.text
            logger.warning("Gemini bos cevap dondurdu (deneme %d)", attempt + 1)
    except Exception as exc:
        logger.error("Gemini hazirlik hatasi: %s", type(exc).__name__)
    raise GeminiRequestError("demo request failed")


def generate_reply(history: list[dict], user_message: str, era: str) -> str:
    if demo_mode():
        return _generate_reply_demo(history, user_message, era)
    persona = PERSONA_2030 if era == "2030" else PERSONA_1996

    try:
        settings = get_settings()

        contents = _build_contents(history, user_message)

        client = _get_client()

        models_to_try = [settings.model]
        for fallback in FALLBACK_MODELS:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        last_exc: Exception = GeminiRequestError("Hicbir model denenemedi")
        for round_num in range(RETRY_ROUNDS):
            if round_num > 0:
                logger.warning(
                    "Tum modeller basarisiz oldu, %s saniye sonra tekrar denenecek",
                    RETRY_DELAY_SECONDS,
                )
                time.sleep(RETRY_DELAY_SECONDS)

            for model_name in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            system_instruction=persona
                        ),
                    )
                except Exception as exc:
                    logger.warning(
                        "Model %s basarisiz oldu, siradaki model deneniyor: %s",
                        model_name,
                        type(exc).__name__,
                    )
                    last_exc = exc
                    continue

                if response.text:
                    return response.text

                last_exc = GeminiRequestError(f"{model_name} bos cevap dondurdu")

        raise last_exc
    except Exception as exc:
        # Class name only: SDK exception text can echo request details.
        logger.error(
            "Gemini API istegi basarisiz oldu: %s", type(exc).__name__
        )
        raise GeminiRequestError(type(exc).__name__) from None
