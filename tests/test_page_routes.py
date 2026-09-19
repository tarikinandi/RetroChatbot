from fastapi.testclient import TestClient

from app import storage
from app.main import app

client = TestClient(app)


def test_get_index_returns_200(monkeypatch):
    monkeypatch.setattr(storage, "increment_counter", lambda data_dir: 1)
    monkeypatch.setattr(storage, "get_chat_history", lambda data_dir: [])
    monkeypatch.setattr(storage, "get_era", lambda data_dir: "1996")

    response = client.get("/")

    assert response.status_code == 200


def test_get_index_calls_increment_counter(monkeypatch):
    calls = []
    monkeypatch.setattr(
        storage, "increment_counter", lambda data_dir: calls.append(1) or 5
    )
    monkeypatch.setattr(storage, "get_chat_history", lambda data_dir: [])
    monkeypatch.setattr(storage, "get_era", lambda data_dir: "1996")

    client.get("/")

    assert len(calls) == 1


def test_get_guestbook_returns_200(monkeypatch):
    monkeypatch.setattr(storage, "get_guestbook_entries", lambda data_dir: [])
    monkeypatch.setattr(storage, "get_era", lambda data_dir: "1996")

    response = client.get("/guestbook")

    assert response.status_code == 200


def test_post_guestbook_saves_entry_and_redirects(monkeypatch):
    saved = []
    monkeypatch.setattr(
        storage,
        "add_guestbook_entry",
        lambda data_dir, name, message: saved.append((name, message)),
    )

    response = client.post(
        "/guestbook",
        data={"name": "Ayse", "message": "Selam!"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/guestbook"
    assert saved == [("Ayse", "Selam!")]


def test_post_toggle_era_calls_toggle_era(monkeypatch):
    calls = []
    monkeypatch.setattr(
        storage, "toggle_era", lambda data_dir: calls.append(1) or "2030"
    )

    client.post("/toggle-era", follow_redirects=False)

    assert len(calls) == 1


def test_post_toggle_era_redirects_to_referer(monkeypatch):
    monkeypatch.setattr(storage, "toggle_era", lambda data_dir: "2030")

    response = client.post(
        "/toggle-era",
        headers={"referer": "http://testserver/guestbook"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "http://testserver/guestbook"


def test_post_toggle_era_redirects_to_home_without_referer(monkeypatch):
    monkeypatch.setattr(storage, "toggle_era", lambda data_dir: "2030")

    response = client.post("/toggle-era", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_get_about_returns_200(monkeypatch):
    monkeypatch.setattr(storage, "get_era", lambda data_dir: "1996")

    response = client.get("/about")

    assert response.status_code == 200
