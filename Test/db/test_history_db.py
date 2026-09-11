import sqlite3

import pytest

import history_db
import main_db


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "t.db")
    monkeypatch.setattr(history_db, "DB_PATH", path)
    monkeypatch.setattr(history_db, "system_log", lambda *a, **k: None)
    monkeypatch.setattr(main_db, "DB_PATH", path)
    monkeypatch.setattr(main_db, "system_log", lambda *a, **k: None)
    return tmp_path / "t.db"


@pytest.fixture
def tables(db):
    main_db.create_table()  # FK target for history/web_log
    history_db.create_table()
    return db


def test_create_table_schema(tables):
    conn = sqlite3.connect(tables)
    hist = {r[1] for r in conn.execute("PRAGMA table_info(history)")}
    web = {r[1] for r in conn.execute("PRAGMA table_info(web_log)")}
    conn.close()
    assert hist == {"Session_id", "user_id", "summary", "created_on"}
    assert web == {"id", "user_id", "query", "provider", "depth", "urls", "created_on"}


def test_create_table_idempotent(tables):
    history_db.create_table()
    history_db.create_table()


def test_store_history_and_access(tables):
    uid = main_db.new_user("Hist", "p", "q")
    history_db.store_history("2026-01-01 10:00:00", uid, "first summary")
    history_db.store_history("2026-01-02 10:00:00", uid, "second summary")

    rows = history_db.access_history(uid)
    assert rows == [
        ("second summary", "2026-01-02 10:00:00"),
        ("first summary", "2026-01-01 10:00:00"),
    ]


def test_access_history_empty(tables):
    uid = main_db.new_user("Nobody", "p", "q")
    assert history_db.access_history(uid) == []


def test_access_history_limits_20(tables):
    uid = main_db.new_user("Spam", "p", "q")
    for i in range(25):
        history_db.store_history(f"2026-01-01 00:00:{i:02d}", uid, f"summary {i}")
    rows = history_db.access_history(uid)
    assert len(rows) == 20
    assert rows[0] == ("summary 24", "2026-01-01 00:00:24")


def test_store_web_log(tables):
    uid = main_db.new_user("Webby", "p", "q")
    history_db.store_web_log(uid, "solaris", "tavily", 3, "http://a,http://b")
    conn = sqlite3.connect(tables)
    row = conn.execute("SELECT * FROM web_log").fetchone()
    conn.close()
    assert row[1] == uid
    assert row[2] == "solaris"
    assert row[3] == "tavily"
    assert row[4] == 3
    assert row[5] == "http://a,http://b"