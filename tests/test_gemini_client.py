import pytest

from app import gemini_client


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    """Never actually sleep in tests, even though generate_reply retries with a delay."""
    monkeypatch.setattr(gemini_client.time, "sleep", lambda seconds: None)


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, response=None, exception=None):
        self._response = response
        self._exception = exception
        self.last_call = None

    def generate_content(self, **kwargs):
        self.last_call = kwargs
        if self._exception:
            raise self._exception
        return self._response


class FakeClient:
    def __init__(self, models):
        self.models = models


def test_generate_reply_returns_text(monkeypatch):
    fake_models = FakeModels(response=FakeResponse("Selam, 1996'dayiz!"))
    monkeypatch.setattr(
        gemini_client, "_get_client", lambda: FakeClient(fake_models)
    )

    reply = gemini_client.generate_reply([], "merhaba", "1996")

    assert reply == "Selam, 1996'dayiz!"


def test_generate_reply_sends_history_and_message(monkeypatch):
    fake_models = FakeModels(response=FakeResponse("cevap"))
    monkeypatch.setattr(
        gemini_client, "_get_client", lambda: FakeClient(fake_models)
    )
    history = [{"role": "user", "text": "ilk mesaj"}]

    gemini_client.generate_reply(history, "ikinci mesaj", "1996")

    sent_contents = fake_models.last_call["contents"]
    assert sent_contents[0] == {"role": "user", "parts": [{"text": "ilk mesaj"}]}
    assert sent_contents[1] == {"role": "user", "parts": [{"text": "ikinci mesaj"}]}


def test_generate_reply_raises_gemini_error_on_failure(monkeypatch):
    fake_models = FakeModels(exception=RuntimeError("network down"))
    monkeypatch.setattr(
        gemini_client, "_get_client", lambda: FakeClient(fake_models)
    )

    with pytest.raises(gemini_client.GeminiRequestError):
        gemini_client.generate_reply([], "merhaba", "1996")


def test_generate_reply_raises_on_empty_response(monkeypatch):
    fake_models = FakeModels(response=FakeResponse(""))
    monkeypatch.setattr(
        gemini_client, "_get_client", lambda: FakeClient(fake_models)
    )

    with pytest.raises(gemini_client.GeminiRequestError):
        gemini_client.generate_reply([], "merhaba", "1996")


def test_generate_reply_sends_1996_persona_for_1996_era(monkeypatch):
    fake_models = FakeModels(response=FakeResponse("cevap"))
    monkeypatch.setattr(
        gemini_client, "_get_client", lambda: FakeClient(fake_models)
    )

    gemini_client.generate_reply([], "merhaba", "1996")

    sent_config = fake_models.last_call["config"]
    assert sent_config.system_instruction == gemini_client.PERSONA_1996


def test_generate_reply_sends_2030_persona_for_2030_era(monkeypatch):
    fake_models = FakeModels(response=FakeResponse("cevap"))
    monkeypatch.setattr(
        gemini_client, "_get_client", lambda: FakeClient(fake_models)
    )

    gemini_client.generate_reply([], "merhaba", "2030")

    sent_config = fake_models.last_call["config"]
    assert sent_config.system_instruction == gemini_client.PERSONA_2030


class FlakyModels:
    """Fails on the first N calls (simulating an overloaded model), then succeeds."""

    def __init__(self, fail_times, response_text):
        self.fail_times = fail_times
        self.response_text = response_text
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs["model"])
        if len(self.calls) <= self.fail_times:
            raise RuntimeError("503 UNAVAILABLE: model overloaded")
        return FakeResponse(self.response_text)


def test_generate_reply_falls_back_to_next_model_when_primary_fails(monkeypatch):
    fake_models = FlakyModels(fail_times=1, response_text="ikinci modelden cevap")
    monkeypatch.setattr(
        gemini_client, "_get_client", lambda: FakeClient(fake_models)
    )

    reply = gemini_client.generate_reply([], "merhaba", "1996")

    assert reply == "ikinci modelden cevap"
    assert len(fake_models.calls) == 2
    assert fake_models.calls[1] == gemini_client.FALLBACK_MODELS[0]


def test_generate_reply_raises_only_after_all_retry_rounds_fail(monkeypatch):
    models_per_round = 1 + len(gemini_client.FALLBACK_MODELS)
    total_attempts = models_per_round * gemini_client.RETRY_ROUNDS
    fake_models = FlakyModels(fail_times=total_attempts, response_text="never used")
    monkeypatch.setattr(
        gemini_client, "_get_client", lambda: FakeClient(fake_models)
    )

    with pytest.raises(gemini_client.GeminiRequestError):
        gemini_client.generate_reply([], "merhaba", "1996")

    assert len(fake_models.calls) == total_attempts


def test_generate_reply_succeeds_on_second_retry_round(monkeypatch):
    models_per_round = 1 + len(gemini_client.FALLBACK_MODELS)
    fake_models = FlakyModels(
        fail_times=models_per_round, response_text="ikinci turdan cevap"
    )
    monkeypatch.setattr(
        gemini_client, "_get_client", lambda: FakeClient(fake_models)
    )

    reply = gemini_client.generate_reply([], "merhaba", "1996")

    assert reply == "ikinci turdan cevap"
    assert len(fake_models.calls) == models_per_round + 1
