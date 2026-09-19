import json
from datetime import datetime, timezone
from pathlib import Path


def _load_list(path: Path) -> list:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_list(path: Path, data: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_chat_history(data_dir: Path) -> list[dict]:
    return _load_list(Path(data_dir) / "chat_history.json")


def append_chat_message(data_dir: Path, role: str, text: str) -> None:
    history = get_chat_history(data_dir)
    history.append({"role": role, "text": text, "timestamp": _now_iso()})
    _save_list(Path(data_dir) / "chat_history.json", history)


def get_guestbook_entries(data_dir: Path) -> list[dict]:
    return _load_list(Path(data_dir) / "guestbook.json")


def add_guestbook_entry(data_dir: Path, name: str, message: str) -> None:
    entries = get_guestbook_entries(data_dir)
    entries.append({"name": name, "message": message, "timestamp": _now_iso()})
    _save_list(Path(data_dir) / "guestbook.json", entries)


def increment_counter(data_dir: Path) -> int:
    path = Path(data_dir) / "counter.json"
    count = 0
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                count = json.load(f).get("count", 0)
        except (json.JSONDecodeError, OSError):
            count = 0

    count += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump({"count": count}, f)

    return count


def get_era(data_dir: Path) -> str:
    path = Path(data_dir) / "era.json"
    if not path.exists():
        return "1996"
    try:
        with path.open("r", encoding="utf-8") as f:
            era = json.load(f).get("era", "1996")
    except (json.JSONDecodeError, OSError):
        return "1996"
    return era if era in ("1996", "2030") else "1996"


def toggle_era(data_dir: Path) -> str:
    current = get_era(data_dir)
    new_era = "2030" if current == "1996" else "1996"
    path = Path(data_dir) / "era.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump({"era": new_era}, f)
    return new_era
