"""Demo-mode guards: input cleaning, origin check, best-effort rate limits.

Everything here is in-memory. On serverless each warm instance has its own
counters, so these limits are a second line of defence only; the real rate
limit is the hosting platform's firewall rule.
"""
import hashlib
import os
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urlsplit

DEFAULT_ALLOWED_ORIGIN = "https://portfolio-mtinandi.vercel.app"
DEV_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:8000")

IP_LIMIT = 5
IP_WINDOW_SECONDS = 60
DEFAULT_DAILY_CAP = 300

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def demo_mode() -> bool:
    return os.environ.get("DEMO_MODE", "").strip().lower() in ("1", "true", "yes", "on")


def clean_text(value: str) -> str:
    return _CONTROL_CHARS.sub("", value).strip()


def allowed_origins() -> list[str]:
    main = os.environ.get("ALLOWED_ORIGIN", "").strip().rstrip("/") or DEFAULT_ALLOWED_ORIGIN
    return [main, *DEV_ORIGINS]


def origin_allowed(origin: str | None, host: str | None) -> bool:
    """No Origin header means not a cross-site browser request: allow.

    A same-origin request (Origin host equals the Host header) is allowed so
    the demo works on its own deployment URL too.
    """
    if not origin:
        return True
    if origin.rstrip("/") in allowed_origins():
        return True
    return bool(host) and urlsplit(origin).netloc == host


def frame_ancestors() -> str:
    return " ".join(["'self'", *allowed_origins()])


def csp_header() -> str:
    cdn = "https://cdn.jsdelivr.net"
    return "; ".join(
        [
            "default-src 'self'",
            f"script-src 'self' {cdn}",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            f"connect-src 'self' {cdn}",
            "base-uri 'self'",
            "form-action 'self'",
            f"frame-ancestors {frame_ancestors()}",
        ]
    )


def client_key(forwarded_for: str | None, peer: str | None) -> str:
    """Hash of the first x-forwarded-for hop (or the peer); raw IPs are never kept."""
    first = (forwarded_for or "").split(",")[0].strip() or (peer or "unknown")
    return hashlib.sha256(first.encode()).hexdigest()[:16]


def daily_cap() -> int:
    try:
        return int(os.environ.get("DAILY_CAP", DEFAULT_DAILY_CAP))
    except ValueError:
        return DEFAULT_DAILY_CAP


class RateLimiter:
    """Per-key sliding window plus a global per-UTC-day soft cap."""

    def __init__(self, clock=time.monotonic, today=None):
        self._clock = clock
        self._today = today or (lambda: datetime.now(timezone.utc).date())
        self._lock = threading.Lock()
        self._hits: dict[str, deque] = {}
        self._day = None
        self._day_count = 0

    def check(self, key: str) -> str | None:
        """Return None if allowed (and count it), else 'ip' or 'daily'."""
        with self._lock:
            now = self._clock()
            today = self._today()
            if today != self._day:
                self._day, self._day_count = today, 0
            if self._day_count >= daily_cap():
                return "daily"
            if len(self._hits) > 5000:
                self._prune(now)
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= IP_WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= IP_LIMIT:
                return "ip"
            hits.append(now)
            self._day_count += 1
            return None

    def _prune(self, now: float) -> None:
        for k in [k for k, h in self._hits.items() if not h or now - h[-1] >= IP_WINDOW_SECONDS]:
            del self._hits[k]


limiter = RateLimiter()
