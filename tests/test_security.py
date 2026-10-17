from datetime import date

from app import security


def test_clean_text_strips_control_chars_but_keeps_newline():
    assert security.clean_text("  a\x00b\x07c\nd\x7f ") == "abc\nd"


def test_origin_rules(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGIN", raising=False)
    assert security.origin_allowed(None, "x.vercel.app")
    assert security.origin_allowed("https://portfolio-mtinandi.vercel.app", "x")
    assert security.origin_allowed("http://localhost:3000", "x")
    assert security.origin_allowed("https://x.vercel.app", "x.vercel.app")
    assert not security.origin_allowed("https://evil.example", "x.vercel.app")


def test_allowed_origin_env_override(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGIN", "https://site.example/")
    assert "https://site.example" in security.allowed_origins()


def test_client_key_uses_first_hop_and_hides_ip():
    k = security.client_key("1.2.3.4, 5.6.7.8", "9.9.9.9")
    assert k == security.client_key("1.2.3.4", None)
    assert "1.2.3.4" not in k


def test_ip_limit_five_per_minute():
    now = [0.0]
    rl = security.RateLimiter(clock=lambda: now[0])
    assert [rl.check("a") for _ in range(5)] == [None] * 5
    assert rl.check("a") == "ip"
    assert rl.check("b") is None
    now[0] = 61
    assert rl.check("a") is None


def test_daily_cap(monkeypatch):
    monkeypatch.setenv("DAILY_CAP", "2")
    day = [date(2030, 1, 1)]
    rl = security.RateLimiter(clock=lambda: 0.0, today=lambda: day[0])
    assert rl.check("a") is None
    assert rl.check("b") is None
    assert rl.check("c") == "daily"
    day[0] = date(2030, 1, 2)
    assert rl.check("c") is None
