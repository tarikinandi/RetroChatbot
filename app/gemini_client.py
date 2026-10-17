import logging
import re
import time

from google import genai
from google.genai import types

from app.config import get_models, get_settings
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
    """code: model_unavailable | quota | key_problem | timeout."""

    def __init__(self, message: str = "", code: str = "model_unavailable"):
        super().__init__(message)
        self.code = code


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
DEMO_MIN_ATTEMPT_SECONDS = 1.0
COOLDOWN_UNUSABLE_SECONDS = 600.0  # 404 / "not found": model name not accepted
COOLDOWN_QUOTA_SECONDS = 60.0  # 429
DISCOVERY_CACHE_SECONDS = 600.0
DISCOVERY_MAX_MODELS = 2
_DISCOVERY_EXCLUDE = ("image", "tts", "live", "embedding", "thinking-exp")

# In-memory, per warm serverless instance. Lost on cold start, which is fine.
_cooldowns: dict[str, tuple[float, str]] = {}
_last_good: list[str] = []
_discovery: list = []  # [fetched_at, names]


def reset_last_good() -> None:
    _last_good.clear()


def reset_model_state() -> None:
    _cooldowns.clear()
    _last_good.clear()
    _discovery.clear()


def _build_contents(history: list[dict], user_message: str) -> list[dict]:
    """Strictly alternating user/model turns, first and last turn from the user.

    The browser owns the history in demo mode, so it can start with a model turn
    (after trimming) or hold two user turns in a row (a failed reply is never
    stored). Gemini can reject both shapes with 400, so normalise here.
    """
    turns: list[tuple[str, str]] = []
    for msg in history:
        role, text = msg.get("role"), (msg.get("text") or "").strip()
        if role not in ("user", "model") or not text:
            continue
        if not turns and role == "model":
            continue
        if turns and turns[-1][0] == role:
            turns[-1] = (role, turns[-1][1] + " " + text)
        else:
            turns.append((role, text))
    if turns and turns[-1][0] == "user":
        turns[-1] = ("user", turns[-1][1] + " " + user_message)
    else:
        turns.append(("user", user_message))
    return [{"role": r, "parts": [{"text": t}]} for r, t in turns]


_KEY_LIKE = re.compile(r"AIza[0-9A-Za-z_\-]{10,}|[A-Za-z0-9_\-]{32,}")


def redact(text: str, limit: int = 160) -> str:
    """Safe-to-log excerpt: key-like tokens and the live key value removed."""
    out = str(text or "")
    try:
        secret = get_settings().api_key
    except Exception:
        secret = ""
    if secret and len(secret) >= 8:
        out = out.replace(secret, "[REDACTED]")
    out = _KEY_LIKE.sub("[REDACTED]", out)
    out = " ".join(out.split())
    return out[:limit]


def _error_message(exc: Exception) -> str:
    msg = getattr(exc, "message", None)
    return str(msg if msg else exc)


def _classify(exc: Exception) -> str:
    """key | quota | request_invalid | unusable | timeout | transient."""
    code = getattr(exc, "code", None)
    status = str(getattr(exc, "status", "") or "").upper()
    text = (_error_message(exc) + " " + str(exc)).lower()
    if code in (401, 403) or status in ("UNAUTHENTICATED", "PERMISSION_DENIED"):
        return "key"
    if code == 400 or status in ("INVALID_ARGUMENT", "FAILED_PRECONDITION"):
        if "api key" in text or "api_key" in text:
            return "key"
        if "not found" in text or "not supported" in text:
            return "unusable"
        return "request_invalid"
    if code == 429 or status == "RESOURCE_EXHAUSTED":
        return "quota"
    if code == 404 or status == "NOT_FOUND":
        return "unusable"
    if isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower():
        return "timeout"
    return "transient"


def _discover_models(client, exclude: set[str]) -> list[str]:
    """Last resort: ask Google which flash models exist (cached 10 min)."""
    now = time.monotonic()
    if not _discovery or now - _discovery[0] > DISCOVERY_CACHE_SECONDS:
        names: list[str] = []
        try:
            for model in client.models.list():
                actions = getattr(model, "supported_actions", None) or []
                name = str(getattr(model, "name", "") or "").removeprefix("models/")
                low = name.lower()
                if "generateContent" not in actions or "flash" not in low:
                    continue
                if any(bad in low for bad in _DISCOVERY_EXCLUDE):
                    continue
                names.append(name)
        except Exception as exc:
            logger.warning("Gemini model listesi alinamadi: %s", type(exc).__name__)
        names.sort(key=lambda n: "lite" in n.lower())  # stable: lite last
        _discovery[:] = [now, names]
    return [n for n in _discovery[1] if n not in exclude][:DISCOVERY_MAX_MODELS]


def _cooled(model: str, now: float) -> str | None:
    until, kind = _cooldowns.get(model, (0.0, ""))
    return kind if until > now else None


def _candidates(configured: list[str]) -> list[str]:
    """Models to try now: skip cooled-down ones, last good model first."""
    now = time.monotonic()
    live = [m for m in configured if _cooled(m, now) is None]
    if not live and not all(_cooled(m, now) == "unusable" for m in configured):
        live = list(configured)  # everything is cooling on quota: try anyway
    if _last_good and _last_good[0] in live:
        live.remove(_last_good[0])
        live.insert(0, _last_good[0])
    return live


def _all_unusable(configured: list[str], kinds: list[str]) -> bool:
    """Every configured model is known to be rejected (400/404) and nothing else went wrong."""
    now = time.monotonic()
    return all(k == "unusable" for k in kinds) and all(
        _cooled(m, now) == "unusable" for m in configured
    )


def _mark_failed(model: str, kind: str) -> None:
    if kind == "unusable":
        _cooldowns[model] = (time.monotonic() + COOLDOWN_UNUSABLE_SECONDS, "unusable")
    elif kind == "quota":
        _cooldowns[model] = (time.monotonic() + COOLDOWN_QUOTA_SECONDS, "quota")
    if _last_good and _last_good[0] == model:
        _last_good.clear()


def _final_code(kinds: list[str]) -> str:
    if kinds and all(k == "quota" for k in kinds):
        return "quota"
    if "timeout" in kinds and "unusable" not in kinds:
        return "timeout"
    if not kinds:
        return "timeout"
    return "model_unavailable"


def _generate_reply_demo(history: list[dict], user_message: str, era: str) -> str:
    """Ordered model fallback inside one ~8 s deadline (Vercel Hobby limit)."""
    persona = PERSONA_2030 if era == "2030" else PERSONA_1996
    kinds: list[str] = []
    try:
        contents = _build_contents(history, user_message)
        configured = get_models()
        client = _get_client()
        start = time.monotonic()
        queue = _candidates(configured)
        discovered = False
        tried = 0
        while True:
            remaining = DEMO_DEADLINE_SECONDS - (time.monotonic() - start)
            if not queue:
                if discovered or not _all_unusable(configured, kinds):
                    break
                discovered = True
                if remaining < DEMO_MIN_ATTEMPT_SECONDS:
                    break
                queue = _discover_models(client, set(configured))
                continue
            if tried and remaining < DEMO_MIN_ATTEMPT_SECONDS:
                break
            model = queue.pop(0)
            share = remaining / min(len(queue) + 1, 2)
            tried += 1
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=persona,
                        http_options=types.HttpOptions(
                            timeout=int(max(share, 0.5) * 1000),
                            retry_options=types.HttpRetryOptions(attempts=1),
                        ),
                    ),
                )
            except Exception as exc:
                kind = _classify(exc)
                logger.warning(
                    "Gemini denemesi basarisiz: model=%s %s kod=%s status=%s tur=%s mesaj=%s",
                    model, type(exc).__name__, getattr(exc, "code", None),
                    getattr(exc, "status", None), kind, redact(_error_message(exc)),
                )
                if kind == "key":
                    raise GeminiRequestError("key", code="key_problem") from None
                if kind == "request_invalid":
                    raise GeminiRequestError("invalid", code="request_invalid") from None
                kinds.append(kind)
                _mark_failed(model, kind)
                continue
            if response.text:
                _last_good[:] = [model]
                return response.text
            logger.warning("Gemini bos cevap dondurdu")
            kinds.append("transient")
    except GeminiRequestError:
        raise
    except Exception as exc:
        logger.error("Gemini hazirlik hatasi: %s", type(exc).__name__)
    raise GeminiRequestError("demo request failed", code=_final_code(kinds))


def generate_reply(history: list[dict], user_message: str, era: str) -> str:
    if demo_mode():
        return _generate_reply_demo(history, user_message, era)
    persona = PERSONA_2030 if era == "2030" else PERSONA_1996

    try:
        settings = get_settings()

        contents = _build_contents(history, user_message)

        client = _get_client()

        models_to_try = list(settings.models) or [settings.model]

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
