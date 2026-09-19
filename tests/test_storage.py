from app import storage


def test_get_chat_history_empty_when_no_file(tmp_path):
    history = storage.get_chat_history(tmp_path)
    assert history == []


def test_append_chat_message_persists_entry(tmp_path):
    storage.append_chat_message(tmp_path, "user", "internet nedir?")

    history = storage.get_chat_history(tmp_path)

    assert len(history) == 1
    assert history[0]["role"] == "user"
    assert history[0]["text"] == "internet nedir?"
    assert "timestamp" in history[0]


def test_append_chat_message_appends_in_order(tmp_path):
    storage.append_chat_message(tmp_path, "user", "merhaba")
    storage.append_chat_message(tmp_path, "model", "selam, 1996'dan yaziyorum")

    history = storage.get_chat_history(tmp_path)

    assert [m["role"] for m in history] == ["user", "model"]


def test_get_chat_history_handles_corrupt_file(tmp_path):
    data_file = tmp_path / "chat_history.json"
    data_file.write_text("{not valid json", encoding="utf-8")

    history = storage.get_chat_history(tmp_path)

    assert history == []


def test_get_guestbook_entries_empty_when_no_file(tmp_path):
    entries = storage.get_guestbook_entries(tmp_path)
    assert entries == []


def test_add_guestbook_entry_persists_entry(tmp_path):
    storage.add_guestbook_entry(tmp_path, "Ayse", "Harika bir site!")

    entries = storage.get_guestbook_entries(tmp_path)

    assert len(entries) == 1
    assert entries[0]["name"] == "Ayse"
    assert entries[0]["message"] == "Harika bir site!"
    assert "timestamp" in entries[0]


def test_add_guestbook_entry_appends_in_order(tmp_path):
    storage.add_guestbook_entry(tmp_path, "Ayse", "ilk mesaj")
    storage.add_guestbook_entry(tmp_path, "Mehmet", "ikinci mesaj")

    entries = storage.get_guestbook_entries(tmp_path)

    assert [e["name"] for e in entries] == ["Ayse", "Mehmet"]


def test_increment_counter_starts_at_one(tmp_path):
    count = storage.increment_counter(tmp_path)
    assert count == 1


def test_increment_counter_increases_each_call(tmp_path):
    storage.increment_counter(tmp_path)
    storage.increment_counter(tmp_path)
    count = storage.increment_counter(tmp_path)
    assert count == 3


def test_increment_counter_handles_corrupt_file(tmp_path):
    data_file = tmp_path / "counter.json"
    data_file.write_text("not json", encoding="utf-8")

    count = storage.increment_counter(tmp_path)

    assert count == 1


def test_get_era_defaults_to_1996_when_no_file(tmp_path):
    assert storage.get_era(tmp_path) == "1996"


def test_get_era_defaults_to_1996_when_corrupt(tmp_path):
    data_file = tmp_path / "era.json"
    data_file.write_text("not json", encoding="utf-8")

    assert storage.get_era(tmp_path) == "1996"


def test_toggle_era_switches_1996_to_2030(tmp_path):
    new_era = storage.toggle_era(tmp_path)
    assert new_era == "2030"
    assert storage.get_era(tmp_path) == "2030"


def test_toggle_era_switches_2030_back_to_1996(tmp_path):
    storage.toggle_era(tmp_path)
    new_era = storage.toggle_era(tmp_path)
    assert new_era == "1996"
    assert storage.get_era(tmp_path) == "1996"
