import sqlite3

import pytest

import main_db


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(main_db, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(main_db, "system_log", lambda *a, **k: None)
    return tmp_path / "t.db"


@pytest.fixture
def table(db):
    main_db.create_table()
    return db


def test_create_table_full_schema(table):
    conn = sqlite3.connect(table)
    cols = {r[1]: (r[3], r[4]) for r in conn.execute("PRAGMA table_info(user_data)")}  # (notnull, default)
    conn.close()

    assert list(cols) == [
        "user_id", "name", "prefers", "about_user",
        "is_private", "password", "is_active", "activation_code",
        "api_password_hash",
        # added by the profile-access migration
        "visibility", "state", "activation_code_hash", "profile_password_hash",
        "failed_attempts", "lockout_until", "created_at", "updated_at", "last_active",
    ]
    expected = {
        "user_id": (0, None),
        "is_private": (1, "0"),
        "is_active": (1, "1"),
        "visibility": (1, "'public'"),
        "state": (1, "'active'"),
        "failed_attempts": (1, "0"),
    }
    for name, (notnull, dflt) in expected.items():
        assert cols[name] == (notnull, dflt), name
    assert cols["password"] == (0, None)
    assert cols["activation_code"] == (0, None)
    assert cols["api_password_hash"] == (0, None)
    assert cols["profile_password_hash"] == (0, None)
    assert cols["activation_code_hash"] == (0, None)


def test_new_user_starts_public_active_with_an_activation_hash(table):
    uid = main_db.new_user("Ada", "calm", "maths")

    conn = sqlite3.connect(table)
    visibility, state, code_hash, plain_code = conn.execute(
        "SELECT visibility, state, activation_code_hash, activation_code FROM user_data WHERE user_id=?",
        (uid,),
    ).fetchone()
    conn.close()

    assert (visibility, state) == ("public", "active")
    assert code_hash and plain_code is None, "only the hash may be stored"
    assert main_db.verify_activation_code(uid, "not-the-code") is False


def test_create_table_idempotent(table):
    main_db.create_table()  # must not raise
    main_db.create_table()


def test_new_user_returns_lastrowid(table):
    uid = main_db.new_user("Alice", "calm", "likes hiking")
    assert isinstance(uid, int)
    next_uid = main_db.new_user("Bob", "fast", "likes chess")
    assert next_uid == uid + 1


def test_new_user_defaults(table):
    uid = main_db.new_user("Carol", "sassy", "none")
    conn = sqlite3.connect(table)
    row = conn.execute(
        "SELECT is_private, is_active, password, activation_code FROM user_data WHERE user_id=?",
        (uid,),
    ).fetchone()
    conn.close()
    assert row == (0, 1, None, None)


def test_get_data_existing(table):
    uid = main_db.new_user("Dave", "brief", "student")
    assert main_db.get_data(uid) == ("brief", "Dave", "student")


def test_get_data_missing(table):
    main_db.new_user("Eve", "x", "y")
    assert main_db.get_data(999_999) is None


def test_update_user_pref(table):
    uid = main_db.new_user("Frank", "old", "z")
    main_db.update_user_pref(uid, "new-pref")
    assert main_db.get_data(uid)[0] == "new-pref"


def test_update_about_user(table):
    uid = main_db.new_user("Gina", "w", "old bio")
    main_db.update_about_user("new bio", uid)
    assert main_db.get_data(uid)[2] == "new bio"


def test_check_existing(table):
    a = main_db.new_user("Zed", "1", "z")
    b = main_db.new_user("Amy", "2", "a")
    assert main_db.check_existing() == [(a, "Zed"), (b, "Amy")]


def test_fetch_user_id_found(table):
    uid = main_db.new_user("Mia", "p", "q")
    assert main_db.fetch_user_id("Mia") == (uid,)


def test_fetch_user_id_missing(table):
    main_db.new_user("Nia", "p", "q")
    assert main_db.fetch_user_id("Nobody") is None

def test_canonical_access_state_survives_a_second_migration(table):
    """visibility and state are canonical once written.

    The one-shot backfill from the legacy is_private/is_active mirrors must
    never run again — otherwise a deliberate change would be undone on the
    next start.
    """
    uid = main_db.new_user("Kay", "p", "q")
    main_db.set_visibility(uid, main_db.VISIBILITY_PRIVATE)
    main_db.set_state(uid, "inactive")

    # The legacy mirrors are deliberately left out of step with the canonical
    # values, exactly as they would be if the user changed them by hand.
    conn = main_db.get_conn()
    conn.execute("UPDATE user_data SET is_private = 0, is_active = 1 WHERE user_id = ?;", (uid,))
    conn.commit()
    conn.close()

    main_db.create_table()

    access = main_db.get_access(uid)
    assert access["visibility"] == main_db.VISIBILITY_PRIVATE
    assert access["state"] == "inactive"
