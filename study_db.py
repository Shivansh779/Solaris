"""Study Trails: profile-scoped learning continuity.

A trail is one topic someone is learning. Concepts inside a trail carry a
mastery state; notes keep saved answers next to the topic they belong to.
No points, streaks or badges — the point is remembering where you left off.
"""

import sqlite3

from _log import system_log, current_time

DB_PATH = "database.db"

STAGES = ("starting", "learning", "practicing", "reviewing", "done")
MASTERY = ("new", "practicing", "confident", "revisit")

STAGE_LABELS = {
    "starting": "Starting",
    "learning": "Learning",
    "practicing": "Practicing",
    "reviewing": "Reviewing",
    "done": "Wrapped up",
}

MAX_TITLE = 160


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_table():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS study_trail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            stage TEXT NOT NULL DEFAULT 'starting',
            quizzes_completed INTEGER NOT NULL DEFAULT 0,
            next_review TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES user_data (user_id)
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS study_concept (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trail_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            mastery TEXT NOT NULL DEFAULT 'new',
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (trail_id) REFERENCES study_trail (id) ON DELETE CASCADE
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS study_note (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trail_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            title TEXT,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (trail_id) REFERENCES study_trail (id) ON DELETE CASCADE
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trail_user ON study_trail (user_id, stage);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_concept_trail ON study_concept (trail_id, mastery);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_note_trail ON study_note (trail_id);")
    conn.commit()
    system_log("DATABASE", "INFO", "Study trail tables created or already exist.")
    cursor.close()
    conn.close()


# ---------------------------------------------------------------- trails


def create_trail(user_id, title, description=""):
    title = (title or "").strip()
    if not title:
        raise ValueError("A study trail needs a topic.")
    now = current_time()
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO study_trail (user_id, title, description, stage, created_at, updated_at)
        VALUES (?, ?, ?, 'starting', ?, ?);
    """, (user_id, title[:MAX_TITLE], (description or "").strip(), now, now))
    conn.commit()
    trail_id = cursor.lastrowid
    cursor.close()
    conn.close()
    system_log("STUDY", "INFO", f"Study trail {trail_id} created for user_id={user_id}.")
    return trail_id


def update_trail(user_id, trail_id, title=None, description=None, stage=None, next_review=None):
    fields, values = [], []
    if title is not None:
        if not title.strip():
            raise ValueError("A study trail needs a topic.")
        fields.append("title = ?")
        values.append(title.strip()[:MAX_TITLE])
    if description is not None:
        fields.append("description = ?")
        values.append((description or "").strip())
    if stage is not None:
        if stage not in STAGES:
            raise ValueError("Unknown trail stage.")
        fields.append("stage = ?")
        values.append(stage)
    if next_review is not None:
        fields.append("next_review = ?")
        values.append((next_review or "").strip())
    if not fields:
        return True
    fields.append("updated_at = ?")
    values.append(current_time())
    values.extend([trail_id, user_id])
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE study_trail SET {', '.join(fields)} WHERE id = ? AND user_id = ?;", values)
    conn.commit()
    changed = cursor.rowcount > 0
    cursor.close()
    conn.close()
    return changed


def delete_trail(user_id, trail_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM study_concept WHERE trail_id = ? AND user_id = ?;", (trail_id, user_id))
    cursor.execute("DELETE FROM study_note WHERE trail_id = ? AND user_id = ?;", (trail_id, user_id))
    cursor.execute("DELETE FROM study_trail WHERE id = ? AND user_id = ?;", (trail_id, user_id))
    conn.commit()
    changed = cursor.rowcount > 0
    cursor.close()
    conn.close()
    return changed


def register_quiz(user_id, trail_id):
    """One quiz completed — bumps the counter and marks the trail as practicing."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE study_trail
           SET quizzes_completed = quizzes_completed + 1,
               stage = CASE WHEN stage IN ('starting', 'learning') THEN 'practicing' ELSE stage END,
               updated_at = ?
         WHERE id = ? AND user_id = ?;
    """, (current_time(), trail_id, user_id))
    conn.commit()
    changed = cursor.rowcount > 0
    cursor.close()
    conn.close()
    return changed


def list_trails(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, title, description, stage, quizzes_completed, next_review, created_at, updated_at
          FROM study_trail WHERE user_id = ? ORDER BY updated_at DESC, id DESC;
    """, (user_id,))
    trails = [_trail_dict(row) for row in cursor.fetchall()]
    for trail in trails:
        cursor.execute("""
            SELECT mastery, COUNT(*) FROM study_concept WHERE trail_id = ? GROUP BY mastery;
        """, (trail["id"],))
        trail["mastery"] = {state: count for state, count in cursor.fetchall()}
        cursor.execute("SELECT COUNT(*) FROM study_note WHERE trail_id = ?;", (trail["id"],))
        trail["notes"] = cursor.fetchone()[0]
        cursor.execute("""
            SELECT name, mastery FROM study_concept
             WHERE trail_id = ? AND mastery IN ('revisit', 'practicing')
             ORDER BY updated_at DESC LIMIT 5;
        """, (trail["id"],))
        trail["weak_spots"] = [{"name": name, "mastery": state} for name, state in cursor.fetchall()]
    cursor.close()
    conn.close()
    return trails


def get_trail(user_id, trail_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, title, description, stage, quizzes_completed, next_review, created_at, updated_at
          FROM study_trail WHERE id = ? AND user_id = ?;
    """, (trail_id, user_id))
    row = cursor.fetchone()
    if row is None:
        cursor.close()
        conn.close()
        return None
    trail = _trail_dict(row)
    cursor.execute("""
        SELECT id, trail_id, name, mastery, note, created_at, updated_at
          FROM study_concept WHERE trail_id = ? ORDER BY updated_at DESC, id DESC;
    """, (trail_id,))
    trail["concepts"] = [_concept_dict(r) for r in cursor.fetchall()]
    cursor.execute("""
        SELECT id, title, content, created_at FROM study_note
         WHERE trail_id = ? ORDER BY created_at DESC, id DESC;
    """, (trail_id,))
    trail["saved_notes"] = [
        {"id": rid, "title": title, "content": content, "created_at": created}
        for rid, title, content, created in cursor.fetchall()
    ]
    cursor.close()
    conn.close()
    return trail


# ---------------------------------------------------------------- concepts


def add_concept(user_id, trail_id, name, mastery="new", note=""):
    name = (name or "").strip()
    if not name:
        raise ValueError("A concept needs a name.")
    if mastery not in MASTERY:
        mastery = "new"
    if get_trail(user_id, trail_id) is None:
        raise ValueError("Unknown study trail.")
    now = current_time()
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO study_concept (trail_id, user_id, name, mastery, note, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?);
    """, (trail_id, user_id, name[:MAX_TITLE], mastery, (note or "").strip(), now, now))
    conn.commit()
    concept_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return concept_id


def set_mastery(user_id, concept_id, mastery):
    if mastery not in MASTERY:
        raise ValueError("Unknown mastery state.")
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE study_concept SET mastery = ?, updated_at = ?
         WHERE id = ? AND user_id = ?;
    """, (mastery, current_time(), concept_id, user_id))
    conn.commit()
    changed = cursor.rowcount > 0
    cursor.close()
    conn.close()
    return changed


def delete_concept(user_id, concept_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM study_concept WHERE id = ? AND user_id = ?;", (concept_id, user_id))
    conn.commit()
    changed = cursor.rowcount > 0
    cursor.close()
    conn.close()
    return changed


# ---------------------------------------------------------------- notes


def add_note(user_id, trail_id, title, content):
    content = (content or "").strip()
    if not content:
        raise ValueError("Nothing to save.")
    if get_trail(user_id, trail_id) is None:
        raise ValueError("Unknown study trail.")
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO study_note (trail_id, user_id, title, content, created_at)
        VALUES (?, ?, ?, ?, ?);
    """, (trail_id, user_id, (title or "").strip()[:MAX_TITLE], content, current_time()))
    conn.commit()
    note_id = cursor.lastrowid
    cursor.close()
    conn.close()
    system_log("STUDY", "INFO", f"Note {note_id} saved to trail {trail_id}.")
    return note_id


def delete_note(user_id, note_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM study_note WHERE id = ? AND user_id = ?;", (note_id, user_id))
    conn.commit()
    changed = cursor.rowcount > 0
    cursor.close()
    conn.close()
    return changed


def summary(user_id):
    """Compact study summary for the workspace shelf."""
    trails = list_trails(user_id)
    weak = []
    for trail in trails:
        for spot in trail["weak_spots"]:
            weak.append({"trail": trail["title"], "concept": spot["name"], "mastery": spot["mastery"]})
    upcoming = [t for t in trails if t["next_review"]]
    return {
        "trails": len(trails),
        "active": trails[0] if trails else None,
        "weak_spots": weak[:5],
        "next_review": upcoming[0]["next_review"] if upcoming else None,
    }


def _trail_dict(row):
    keys = ("id", "user_id", "title", "description", "stage", "quizzes_completed",
            "next_review", "created_at", "updated_at")
    return dict(zip(keys, row))


def _concept_dict(row):
    keys = ("id", "trail_id", "name", "mastery", "note", "created_at", "updated_at")
    return dict(zip(keys, row))
