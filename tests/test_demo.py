import pytest
from fastapi.testclient import TestClient

from app import gemini_client, security, storage
from app.main import app

client = TestClient(app)
PORTFOLIO = "https://portfolio-mtinandi.vercel.app"


@pytest.fixture(autouse=True)
def demo_env(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(security, "limiter", security.RateLimiter())
    calls = []

    def fake_reply(history, msg, era):
        calls.append((history, msg, era))
        return "cevap"

    monkeypatch.setattr(gemini_client, "generate_reply", fake_reply)

    def boom(*a, **k):
        raise AssertionError("demo mode must not touch server storage")

    for name in ("get_era", "get_chat_history", "append_chat_message",
                 "increment_counter", "toggle_era", "add_guestbook_entry",
                 "get_guestbook_entries"):
        monkeypatch.setattr(storage, name, boom)
    return calls


def test_chat_uses_client_history_and_era(demo_env):
    body = {"message": "selam", "era": "2030",
            "history": [{"role": "user", "text": "a"}, {"role": "model", "text": "b"}]}
    r = client.post("/api/chat", json=body)
    assert r.status_code == 200 and r.json() == {"reply": "cevap"}
    history, msg, era = demo_env[0]
    assert msg == "selam" and era == "2030" and len(history) == 2


@pytest.mark.parametrize("body", [
    {"message": ""},
    {"message": "x" * 501},
    {"message": "ok", "history": [{"role": "user", "text": "a"}] * 11},
    {"message": "ok", "history": [{"role": "system", "text": "a"}]},
    {"message": "ok", "history": [{"role": "user", "text": "x" * 501}]},
    {"message": "ok", "era": "1850"},
    {"message": "\x00\x07  "},
])
def test_chat_validation_422(body):
    assert client.post("/api/chat", json=body).status_code == 422


def test_control_chars_stripped(demo_env):
    client.post("/api/chat", json={"message": "a\x00b\x1bc"})
    assert demo_env[0][1] == "abc"


def test_disallowed_origin_403(demo_env):
    r = client.post("/api/chat", json={"message": "x"}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403 and not demo_env


def test_allowed_origin_and_cors_headers():
    r = client.post("/api/chat", json={"message": "x"}, headers={"origin": PORTFOLIO})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == PORTFOLIO


def test_cors_not_granted_to_other_origin():
    r = client.options("/api/chat", headers={
        "origin": "https://evil.example", "access-control-request-method": "POST"})
    assert "access-control-allow-origin" not in r.headers


def test_missing_key_gives_503_not_crash(monkeypatch, demo_env):
    monkeypatch.delenv("GEMINI_API_KEY")
    r = client.post("/api/chat", json={"message": "x", "era": "2030"})
    assert r.status_code == 503 and "reply" in r.json() and not demo_env


def test_per_ip_limit_429_in_era_voice():
    h = {"x-forwarded-for": "7.7.7.7, 10.0.0.1"}
    codes = [client.post("/api/chat", json={"message": "x"}, headers=h).status_code
             for _ in range(6)]
    assert codes == [200] * 5 + [429]
    r = client.post("/api/chat", json={"message": "x", "era": "2030"}, headers=h)
    assert r.status_code == 429 and "NÖRAL" in r.json()["reply"]


def test_daily_cap_429(monkeypatch):
    monkeypatch.setenv("DAILY_CAP", "1")
    assert client.post("/api/chat", json={"message": "x"},
                       headers={"x-forwarded-for": "1.1.1.1"}).status_code == 200
    r = client.post("/api/chat", json={"message": "x"}, headers={"x-forwarded-for": "2.2.2.2"})
    assert r.status_code == 429


def test_gemini_error_is_generic(monkeypatch):
    def fail(*a):
        raise gemini_client.GeminiRequestError("SECRET")
    monkeypatch.setattr(gemini_client, "generate_reply", fail)
    r = client.post("/api/chat", json={"message": "x"})
    assert r.status_code == 502 and "SECRET" not in r.text


def test_guestbook_and_toggle_disabled():
    assert client.get("/guestbook").status_code == 404
    assert client.post("/guestbook", data={"name": "a", "message": "b"}).status_code == 404
    assert client.post("/toggle-era").status_code == 404


def test_index_era_from_query_sets_cookie_and_hides_extras():
    r = client.get("/?era=2030")
    assert r.status_code == 200 and 'data-era="2030"' in r.text
    assert "era=2030" in r.headers["set-cookie"]
    assert "Misafir Defteri" not in r.text and "toggle-era" not in r.text
    assert "Ziyaretci sayisi" not in r.text


def test_security_headers_present():
    r = client.get("/")
    csp = r.headers["content-security-policy"]
    assert "frame-ancestors 'self' " + PORTFOLIO in csp
    assert "https://cdn.jsdelivr.net" in csp


def test_app_imports_without_key_in_demo(monkeypatch):
    import importlib
    import app.main as m
    import dotenv
    # never let a real local .env leak a key into the test process
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    monkeypatch.delenv("GEMINI_API_KEY")
    importlib.reload(m)
