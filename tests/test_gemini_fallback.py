"""Demo-mode model fallback, cooldowns, discovery and error codes (no network)."""
import pytest

from app import gemini_client


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, models):
        self.models = models


class ApiErr(Exception):
    """Mimics google.genai.errors.APIError (code/status); the message is secret-ish."""

    def __init__(self, code, status="", message="SECRET-API-TEXT"):
        super().__init__(message)
        self.code = code
        self.status = status


class RoutedModels:
    """Per-model outcomes: str = reply text, Exception = raise."""

    def __init__(self, outcomes, listing=None, clock=None, cost=0.0):
        self.outcomes = outcomes
        self.listing = listing
        self.calls = []
        self.timeouts = []
        self.list_calls = 0
        self.clock = clock
        self.cost = cost

    def generate_content(self, **kwargs):
        self.calls.append(kwargs["model"])
        self.timeouts.append(kwargs["config"].http_options.timeout)
        if self.clock is not None:
            self.clock[0] += self.cost
        out = self.outcomes.get(kwargs["model"], ApiErr(404, "NOT_FOUND"))
        if isinstance(out, Exception):
            raise out
        return FakeResponse(out)

    def list(self):
        self.list_calls += 1
        return list(self.listing or [])


class Listed:
    def __init__(self, name, actions=("generateContent",)):
        self.name = name
        self.supported_actions = list(actions)


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("GEMINI_MODELS", "m1,m2,m3")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    gemini_client.reset_model_state()
    clock = [1000.0]
    monkeypatch.setattr(gemini_client.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(gemini_client.time, "sleep", lambda s: None)

    def install(models):
        monkeypatch.setattr(gemini_client, "_get_client", lambda: FakeClient(models))
        return models

    install.clock = clock
    yield install
    gemini_client.reset_model_state()


def reply():
    return gemini_client.generate_reply([], "hi", "1996")


def test_first_model_400_falls_to_second(demo):
    m = demo(RoutedModels({"m1": ApiErr(404, "NOT_FOUND"), "m2": "ok"}))
    assert reply() == "ok"
    assert m.calls == ["m1", "m2"]


def test_quota_429_moves_to_next_model(demo):
    m = demo(RoutedModels({"m1": ApiErr(429, "RESOURCE_EXHAUSTED"), "m2": "ok"}))
    assert reply() == "ok"
    assert m.calls == ["m1", "m2"]


def test_5xx_and_timeout_move_to_next_model(demo):
    m = demo(RoutedModels({"m1": ApiErr(503, "UNAVAILABLE"), "m2": TimeoutError(), "m3": "ok"}))
    assert reply() == "ok"
    assert m.calls == ["m1", "m2", "m3"]


@pytest.mark.parametrize("code,status", [(401, "UNAUTHENTICATED"), (403, "PERMISSION_DENIED")])
def test_auth_errors_stop_immediately(demo, code, status):
    m = demo(RoutedModels({"m1": ApiErr(code, status), "m2": "ok"}))
    with pytest.raises(gemini_client.GeminiRequestError) as info:
        reply()
    assert info.value.code == "key_problem"
    assert m.calls == ["m1"]


def test_invalid_key_reported_as_400_is_key_problem(demo):
    msg = "API key not valid. Please pass a valid API key."
    m = demo(RoutedModels({"m1": ApiErr(400, "INVALID_ARGUMENT", msg), "m2": "ok"}))
    with pytest.raises(gemini_client.GeminiRequestError) as info:
        reply()
    assert info.value.code == "key_problem" and m.calls == ["m1"]


def test_last_good_model_tried_first_next_time(demo):
    m = demo(RoutedModels({"m1": ApiErr(503, "UNAVAILABLE"), "m2": "ok", "m3": "ok"}))
    reply()
    m.calls.clear()
    reply()
    assert m.calls == ["m2"]


def test_400_cooldown_skips_bad_model_then_expires(demo):
    m = demo(RoutedModels({"m1": ApiErr(404, "NOT_FOUND"), "m2": ApiErr(503), "m3": "ok"}))
    reply()  # m1 -> cooldown, m2 transient, m3 ok (last good)
    m.calls.clear()
    m.outcomes["m3"] = ApiErr(503)
    m.outcomes["m2"] = "ok"
    reply()
    assert "m1" not in m.calls  # still cooled down
    demo.clock[0] += gemini_client.COOLDOWN_UNUSABLE_SECONDS + 1
    gemini_client.reset_last_good()
    m.calls.clear()
    m.outcomes["m1"] = "ok"
    reply()
    assert m.calls[0] == "m1"


def test_429_cooldown_is_short_and_expires(demo):
    m = demo(RoutedModels({"m1": ApiErr(429, "RESOURCE_EXHAUSTED"), "m2": "ok"}))
    reply()
    gemini_client.reset_last_good()
    m.calls.clear()
    reply()
    assert "m1" not in m.calls
    demo.clock[0] += gemini_client.COOLDOWN_QUOTA_SECONDS + 1
    gemini_client.reset_last_good()
    m.calls.clear()
    reply()
    assert m.calls[0] == "m1"
    assert gemini_client.COOLDOWN_QUOTA_SECONDS < gemini_client.COOLDOWN_UNUSABLE_SECONDS


def test_all_quota_gives_quota_code(demo):
    demo(RoutedModels({k: ApiErr(429, "RESOURCE_EXHAUSTED") for k in ("m1", "m2", "m3")}))
    with pytest.raises(gemini_client.GeminiRequestError) as info:
        reply()
    assert info.value.code == "quota"


def test_all_400_triggers_discovery_and_listing_is_cached(demo):
    listing = [
        Listed("models/gemini-9-pro"),
        Listed("models/gemini-9-flash-lite"),
        Listed("models/gemini-9-flash-image"),
        Listed("models/gemini-9-flash-tts"),
        Listed("models/gemini-9-flash", ("generateContent", "countTokens")),
        Listed("models/gemini-9-flash-embedding", ("embedContent",)),
        Listed("models/gemini-8-flash", ("embedContent",)),
    ]
    outcomes = {k: ApiErr(404, "NOT_FOUND") for k in ("m1", "m2", "m3")}
    outcomes["gemini-9-flash"] = "found"
    m = demo(RoutedModels(outcomes, listing=listing))
    assert reply() == "found"
    assert m.calls == ["m1", "m2", "m3", "gemini-9-flash"]
    assert m.list_calls == 1
    gemini_client.reset_last_good()
    reply()
    assert m.list_calls == 1  # cached


def test_discovery_prefers_flash_over_lite_and_caps_at_two(demo):
    listing = [Listed("models/g-flash-lite"), Listed("models/g-flash-a"), Listed("models/g-flash-b")]
    outcomes = {k: ApiErr(404, "NOT_FOUND") for k in ("m1", "m2", "m3")}
    outcomes.update({"g-flash-lite": "never"})
    m = demo(RoutedModels(outcomes, listing=listing))
    with pytest.raises(gemini_client.GeminiRequestError) as info:
        reply()
    assert m.calls[3:] == ["g-flash-a", "g-flash-b"]
    assert info.value.code == "model_unavailable"


def test_discovery_not_used_when_a_failure_was_quota(demo):
    m = demo(RoutedModels(
        {"m1": ApiErr(404), "m2": ApiErr(429, "RESOURCE_EXHAUSTED"), "m3": ApiErr(404)},
        listing=[Listed("models/x-flash")],
    ))
    with pytest.raises(gemini_client.GeminiRequestError):
        reply()
    assert m.list_calls == 0


def test_discovery_failure_is_swallowed(demo):
    class Broken(RoutedModels):
        def list(self):
            raise RuntimeError("SECRET-LIST")

    demo(Broken({k: ApiErr(404) for k in ("m1", "m2", "m3")}))
    with pytest.raises(gemini_client.GeminiRequestError) as info:
        reply()
    assert info.value.code == "model_unavailable"


def test_deadline_respected_with_fake_clock(demo):
    m = demo(RoutedModels({k: TimeoutError() for k in ("m1", "m2", "m3")},
                          clock=demo.clock, cost=5.0))
    start = demo.clock[0]
    with pytest.raises(gemini_client.GeminiRequestError) as info:
        reply()
    assert info.value.code == "timeout"
    # each attempt burns 5 s of fake time: after the 2nd the deadline is gone
    assert len(m.calls) == 2
    assert demo.clock[0] - start == 10.0


def test_attempt_timeout_is_a_share_of_remaining(demo):
    m = demo(RoutedModels({"m1": ApiErr(503), "m2": ApiErr(503), "m3": "ok"}))
    reply()
    limit = gemini_client.DEMO_DEADLINE_SECONDS * 1000
    assert all(0 < t <= limit for t in m.timeouts)
    assert m.timeouts[0] < limit


def test_logs_have_class_and_code_only(demo, caplog):
    demo(RoutedModels({"m1": ApiErr(403, "PERMISSION_DENIED", "FAKE" + "-KEY-TEXT")}))
    with pytest.raises(gemini_client.GeminiRequestError):
        gemini_client.generate_reply([], "private-user-text", "1996")
    assert "private-user-text" not in caplog.text
    assert "ApiErr" in caplog.text and "403" in caplog.text


# ---- request shape, classification and redaction (no network) ----

HISTORIES = [
    [],
    [{"role": "user", "text": "a"}, {"role": "model", "text": "b"}],
    [{"role": "model", "text": "b"}, {"role": "user", "text": "a"}],  # trimmed start
    [{"role": "user", "text": "a"}, {"role": "user", "text": "c"}],  # failed reply
    [{"role": "user", "text": "a"}, {"role": "model", "text": " "}],  # empty turn
    [{"role": "user", "text": "a"}, {"role": "model", "text": "b"}, {"role": "user", "text": "c"}],
]


@pytest.mark.parametrize("history", HISTORIES)
@pytest.mark.parametrize("era", ["1996", "2030"])
def test_demo_request_shape_is_valid(demo, history, era):
    from google.genai import types

    m = demo(RoutedModels({"m1": "ok"}))
    seen = {}
    real = m.generate_content

    def spy(**kw):
        seen.update(kw)
        return real(**kw)

    m.generate_content = spy
    gemini_client.generate_reply(history, "Merhaba", era)
    contents = seen["contents"]
    roles = [c["role"] for c in contents]
    assert roles[0] == "user" and roles[-1] == "user"
    assert all(a != b for a, b in zip(roles, roles[1:]))
    for c in contents:
        assert c["parts"] and all(p["text"].strip() for p in c["parts"])
        types.Content.model_validate(c)
    cfg = seen["config"]
    assert isinstance(cfg, types.GenerateContentConfig)
    assert cfg.system_instruction and "Zaman Makinesi" in cfg.system_instruction
    assert cfg.tools is None and cfg.max_output_tokens is None
    assert "Merhaba" in contents[-1]["parts"][0]["text"]


def test_400_other_is_request_invalid_without_fallback(demo, caplog):
    m = demo(RoutedModels({"m1": ApiErr(400, "INVALID_ARGUMENT", "bad contents"), "m2": "ok"}))
    with pytest.raises(gemini_client.GeminiRequestError) as info:
        reply()
    assert info.value.code == "request_invalid"
    assert m.calls == ["m1"]
    assert "request_invalid" in caplog.text and "INVALID_ARGUMENT" in caplog.text


def test_400_api_key_is_key_problem(demo):
    m = demo(RoutedModels({"m1": ApiErr(400, "INVALID_ARGUMENT", "API key not valid"), "m2": "ok"}))
    with pytest.raises(gemini_client.GeminiRequestError) as info:
        reply()
    assert info.value.code == "key_problem" and m.calls == ["m1"]


def test_404_still_falls_back(demo):
    demo(RoutedModels({"m1": ApiErr(404, "NOT_FOUND", "model not found"), "m2": "ok"}))
    assert reply() == "ok"


def test_redact_removes_key_like_values_and_truncates(monkeypatch):
    fake_key = "AI" + "za" + "Sy" + "x" * 33
    other = "tok" + "A1" * 20
    monkeypatch.setenv("GEMINI_API_KEY", "shortsecret-" + "z" * 4)
    text = f"bad {fake_key} and {other} and shortsecret-zzzz " + "w " * 200
    out = gemini_client.redact(text)
    assert fake_key not in out and other not in out and "shortsecret-zzzz" not in out
    assert "[REDACTED]" in out and len(out) <= 160
