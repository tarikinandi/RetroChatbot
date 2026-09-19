from fastapi.testclient import TestClient

from app import gemini_client, storage
from app.main import app

client = TestClient(app)


def test_post_chat_returns_reply(monkeypatch):
    monkeypatch.setattr(storage, "get_era", lambda data_dir: "1996")
    monkeypatch.setattr(storage, "get_chat_history", lambda data_dir: [])
    monkeypatch.setattr(storage, "append_chat_message", lambda *a, **k: None)
    monkeypatch.setattr(
        gemini_client,
        "generate_reply",
        lambda history, msg, era: "1996'dan selamlar!",
    )

    response = client.post("/api/chat", json={"message": "merhaba"})

    assert response.status_code == 200
    assert response.json() == {"reply": "1996'dan selamlar!"}


def test_post_chat_saves_user_and_model_messages(monkeypatch):
    saved = []
    monkeypatch.setattr(storage, "get_era", lambda data_dir: "1996")
    monkeypatch.setattr(storage, "get_chat_history", lambda data_dir: [])
    monkeypatch.setattr(
        storage,
        "append_chat_message",
        lambda data_dir, role, text: saved.append((role, text)),
    )
    monkeypatch.setattr(
        gemini_client, "generate_reply", lambda history, msg, era: "cevap"
    )

    client.post("/api/chat", json={"message": "soru"})

    assert saved == [("user", "soru"), ("model", "cevap")]


def test_post_chat_passes_current_era_to_gemini_client(monkeypatch):
    received = {}
    monkeypatch.setattr(storage, "get_era", lambda data_dir: "2030")
    monkeypatch.setattr(storage, "get_chat_history", lambda data_dir: [])
    monkeypatch.setattr(storage, "append_chat_message", lambda *a, **k: None)

    def fake_generate_reply(history, msg, era):
        received["era"] = era
        return "cevap"

    monkeypatch.setattr(gemini_client, "generate_reply", fake_generate_reply)

    client.post("/api/chat", json={"message": "merhaba"})

    assert received["era"] == "2030"


def test_post_chat_returns_1996_fallback_message_on_gemini_error(monkeypatch):
    monkeypatch.setattr(storage, "get_era", lambda data_dir: "1996")
    monkeypatch.setattr(storage, "get_chat_history", lambda data_dir: [])
    monkeypatch.setattr(storage, "append_chat_message", lambda *a, **k: None)

    def raise_error(history, msg, era):
        raise gemini_client.GeminiRequestError("boom")

    monkeypatch.setattr(gemini_client, "generate_reply", raise_error)

    response = client.post("/api/chat", json={"message": "merhaba"})

    assert response.status_code == 200
    assert "BAGLANTI" in response.json()["reply"]


def test_post_chat_returns_2030_fallback_message_on_gemini_error(monkeypatch):
    monkeypatch.setattr(storage, "get_era", lambda data_dir: "2030")
    monkeypatch.setattr(storage, "get_chat_history", lambda data_dir: [])
    monkeypatch.setattr(storage, "append_chat_message", lambda *a, **k: None)

    def raise_error(history, msg, era):
        raise gemini_client.GeminiRequestError("boom")

    monkeypatch.setattr(gemini_client, "generate_reply", raise_error)

    response = client.post("/api/chat", json={"message": "merhaba"})

    assert response.status_code == 200
    assert "NÖRAL" in response.json()["reply"]
