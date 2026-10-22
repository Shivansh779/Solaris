import sqlite3
from datetime import datetime

from _log import system_log, current_time

import embeddings
import vec_db

DB_PATH = "database.db"

def get_conn ():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def _ensure_vector_meta ():
    """Make sure the vector bookkeeping table lives in this database.

    `vec_db` keeps its own path constant, so the call is pointed at this
    module's database for as long as it runs. The table only has to be
    created once: after that the index is there and the rows own it.
    """
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'vec_meta';"
        ).fetchone()
    except Exception as error:
        system_log("VECTOR", "WARNING", f"Vector bookkeeping check failed: {error}")
        row = None
    finally:
        conn.close()
    if row:
        return
    try:
        vec_db.create_table(path=DB_PATH)
    except Exception as error:
        system_log("VECTOR", "WARNING", f"Vector bookkeeping table unavailable: {error}")

def create_table():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            Session_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            summary TEXT,
            created_on TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES user_data (user_id)
        );
    """)
    conn.commit()
    system_log("DATABASE", "INFO", "History table created or already exists.")
    cursor.close()
    conn.close()
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS web_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            query TEXT,
            provider TEXT,
            depth INTEGER,
            urls TEXT,
            created_on TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES user_data (user_id)
        );
    """)
    conn.commit()
    system_log("DATABASE", "INFO", "Web log table created or already exists.")
    cursor.close()
    conn.close()
    _ensure_vector_meta()

def store_web_log (user_id, query, provider, depth, urls):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO web_log (user_id, query, provider, depth, urls, created_on) VALUES (?, ?, ?, ?, ?, ?);
    """, (user_id, query, provider, depth, urls, current_time())
    )
    conn.commit()
    system_log("DATABASE", "INFO", f"Inserted web log entry for user_id={user_id}, provider={provider}.")
    cursor.close()
    conn.close()

def store_history (time, user_id, summary):
    """Save a session summary and index it for semantic search.

    The chunks are embedded before the write connection is opened, so the
    database is never locked across a call to the local model. A model that
    is down costs the index, not the summary: the row is written either way.
    """
    chunks = vec_db.split_bullets(summary)
    vectors = None
    if chunks:
        try:
            vectors = embeddings.embed(chunks)
        except Exception as error:
            system_log("VECTOR", "WARNING", f"Summary embedding skipped: {error}")
            vectors = None
        if vectors and len(vectors) != len(chunks):
            system_log("VECTOR", "WARNING", "Summary embedding returned the wrong number of vectors.")
            vectors = None
    if chunks and vectors:
        _ensure_vector_meta()
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO history (user_id, summary, created_on) VALUES (?, ?, ?);
    """, (user_id, summary, time)
    )
    session_id = cursor.lastrowid
    if chunks and vectors:
        try:
            vec_db.insert_chunks(conn, user_id, vec_db.KIND_HISTORY, session_id, chunks, vectors)
        except Exception as error:
            system_log("VECTOR", "WARNING", f"Summary chunks not indexed: {error}")
    conn.commit()
    system_log("DATABASE", "INFO", f"Inserted history summary for user_id={user_id}.")
    cursor.close()
    conn.close()
    return session_id

def access_history (user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            SELECT summary, created_on
            FROM history 
            WHERE user_id = ? 
            ORDER BY Session_id DESC 
            LIMIT 20;
        """, (user_id,)
    )
    response = cursor.fetchall()
    system_log("DATABASE", "INFO", f"Retrieved history summaries for user_id={user_id}.")
    cursor.close()
    conn.close()
    return response

def access_history_similar (user_id, query, limit=20):
    """History summaries ranked by how well they match `query`.

    Same shape as `access_history`: a list of (summary, created_on) tuples.
    The vector index is a bonus, so whenever it cannot answer - no index, no
    hits, or rows that are gone - the plain last-20 view is returned instead.
    """
    hits = []
    try:
        hits = vec_db.search(user_id, query, kind=vec_db.KIND_HISTORY, limit=limit,
                             path=DB_PATH) or []
    except Exception as error:
        system_log("VECTOR", "WARNING", f"Vector history search failed: {error}")
        hits = []
    order = []
    for hit in hits:
        ref_id = hit.get("ref_id")
        if ref_id is None or ref_id in order:
            continue
        order.append(ref_id)
    if not order:
        return access_history(user_id)
    conn = get_conn()
    cursor = conn.cursor()
    placeholders = ",".join("?" * len(order))
    cursor.execute(
        f"""
            SELECT Session_id, summary, created_on
            FROM history
            WHERE user_id = ? AND Session_id IN ({placeholders});
        """, [user_id] + order
    )
    rows = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
    cursor.close()
    conn.close()
    response = [rows[ref_id] for ref_id in order if ref_id in rows]
    if not response:
        return access_history(user_id)
    system_log("DATABASE", "INFO", f"Retrieved {len(response)} similar history summaries for user_id={user_id}.")
    return response
