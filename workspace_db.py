"""Living Workspace session state: the current task and the session checkpoint.

Both are profile-scoped. The checkpoint is only ever written on an explicit
save, so a user's own wording is never overwritten by a model.
"""

import sqlite3

from _log import system_log, current_time

DB_PATH = "database.db"

MAX_TASK = 200


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_table():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workspace_task (
            user_id INTEGER PRIMARY KEY,
            task TEXT,
            updated_at TEXT,
            FOREIGN KEY (user_id) REFERENCES user_data (user_id)
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workspace_checkpoint (
            user_id INTEGER PRIMARY KEY,
            goal TEXT,
            decisions TEXT,
            questions TEXT,
            next_step TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY (user_id) REFERENCES user_data (user_id)
        );
    """)
    conn.commit()
    system_log("DATABASE", "INFO", "Workspace tables created or already exist.")
    cursor.close()
    conn.close()


# ---------------------------------------------------------------- task


def set_task(user_id, task):
    task = (task or "").strip()[:MAX_TASK]
    now = current_time()
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO workspace_task (user_id, task, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET task = excluded.task, updated_at = excluded.updated_at;
    """, (user_id, task, now))
    conn.commit()
    cursor.close()
    conn.close()
    return {"task": task, "updated_at": now}


def get_task(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT task, updated_at FROM workspace_task WHERE user_id = ?;", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return {"task": row[0], "updated_at": row[1]} if row else {"task": "", "updated_at": None}


# ---------------------------------------------------------------- checkpoint


def save_checkpoint(user_id, goal="", decisions="", questions="", next_step=""):
    """Save the session checkpoint. Only called from an explicit user action."""
    now = current_time()
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT created_at FROM workspace_checkpoint WHERE user_id = ?;", (user_id,))
    row = cursor.fetchone()
    created_at = row[0] if row else now
    cursor.execute("""
        INSERT INTO workspace_checkpoint (user_id, goal, decisions, questions, next_step, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            goal = excluded.goal,
            decisions = excluded.decisions,
            questions = excluded.questions,
            next_step = excluded.next_step,
            updated_at = excluded.updated_at;
    """, (user_id, (goal or "").strip(), (decisions or "").strip(),
          (questions or "").strip(), (next_step or "").strip(), created_at, now))
    conn.commit()
    cursor.close()
    conn.close()
    system_log("WORKSPACE", "INFO", f"Checkpoint saved for user_id={user_id}.")
    return get_checkpoint(user_id)


def get_checkpoint(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT goal, decisions, questions, next_step, created_at, updated_at
          FROM workspace_checkpoint WHERE user_id = ?;
    """, (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if row is None:
        return {"goal": "", "decisions": "", "questions": "", "next_step": "",
                "created_at": None, "updated_at": None}
    keys = ("goal", "decisions", "questions", "next_step", "created_at", "updated_at")
    return dict(zip(keys, row))


def clear_checkpoint(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM workspace_checkpoint WHERE user_id = ?;", (user_id,))
    conn.commit()
    removed = cursor.rowcount
    cursor.close()
    conn.close()
    return removed > 0


def clear_profile(user_id):
    """Remove all workspace state for a profile (used with profile cleanup)."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM workspace_task WHERE user_id = ?;", (user_id,))
    cursor.execute("DELETE FROM workspace_checkpoint WHERE user_id = ?;", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()
