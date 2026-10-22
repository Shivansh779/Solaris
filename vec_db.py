"""Semantic index over Solaris' memory layers (sqlite-vec).

The index is a derived, rebuildable artefact: `profile_memory` and `history`
stay the source of truth. Everything here degrades to a no-op when the
sqlite-vec extension or the local embedding model is unavailable — the app
then falls back to plain keyword ranking and behaves exactly as it did before.

Vectors live in one `vec0` virtual table inside the existing `database.db`,
so a reader either sees a chunk and its source row together, or neither.
"""

import re
import sqlite3

from _log import current_time, system_log

import embeddings

try:
    import sqlite_vec
except ImportError:  # the extension is optional — the app must still boot
    sqlite_vec = None

DB_PATH = "database.db"

VEC_TABLE = "vec_chunks"
META_TABLE = "vec_meta"

KIND_MEMORY = "memory"
KIND_HISTORY = "history"

# Chunk ids are deterministic, so a chunk can be deleted by primary key:
#   kind * 1e9 + ref_id * 1000 + sequence
CHUNK_STRIDE = 1000
KIND_STRIDE = 1_000_000_000
KIND_CODES = {KIND_MEMORY: 1, KIND_HISTORY: 2}

# all-minilm is served with num_ctx 256, so a chunk must stay well inside
# that window or the tail is silently truncated.
MAX_CHUNK_CHARS = 400
MAX_CHUNKS_PER_REF = 64

# Bullet markers a model may emit: - * + • · – — and 1. 2)
_BULLET = re.compile(r"^\s*(?:[-*+•·–—]|\d+[.)])\s+")
_SENTENCE = re.compile(r"(?<=[.!?;])\s+")

# The query embedding of the current turn, so one turn costs one embed.
_vector_cache = {"query": None, "vector": None}


# ---------------------------------------------------------------- connections


def get_conn(path=None):
    """A plain connection to the database. Same shape as the other db modules.

    `path` overrides the module constant, so a caller can point the index at
    its own database without mutating shared state.
    """
    conn = sqlite3.connect(path or DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def load_extension(conn):
    """Load sqlite-vec onto a connection. False when it cannot be loaded."""
    if sqlite_vec is None:
        return False
    try:
        conn.enable_load_extension(True)
    except AttributeError:
        # The SQLite that ships with macOS cannot load extensions at all.
        return False
    try:
        sqlite_vec.load(conn)
        return True
    except Exception as error:
        system_log("VECTOR", "WARNING", f"sqlite-vec could not be loaded: {error}")
        return False
    finally:
        try:
            conn.enable_load_extension(False)
        except Exception:
            pass


def available():
    """True when sqlite-vec can be used on this machine."""
    if sqlite_vec is None:
        return False
    conn = get_conn()
    try:
        if not load_extension(conn):
            return False
        conn.execute("SELECT vec_version();").fetchone()
        return True
    except Exception:
        return False
    finally:
        conn.close()


# ---------------------------------------------------------------- bookkeeping


def read_meta(conn=None, path=None):
    """The single bookkeeping row: model, dimension, chunk count, state."""
    own = conn is None
    conn = conn or get_conn(path)
    try:
        row = conn.execute(
            f"SELECT model, dimension, chunk_count, built_at, state FROM {META_TABLE} WHERE id = 1;"
        ).fetchone()
    except Exception:
        if own:
            conn.close()
        return {}
    if own:
        conn.close()
    if not row:
        return {}
    return {
        "model": row[0],
        "dimension": row[1],
        "chunk_count": row[2] or 0,
        "built_at": row[3],
        "state": row[4],
    }


def _set_meta(conn, **fields):
    """Update the bookkeeping row."""
    if not fields:
        return
    assignments = ", ".join(f"{name} = ?" for name in fields)
    values = list(fields.values())
    placeholders = ", ".join("?" * len(fields))
    conn.execute(
        f"INSERT INTO {META_TABLE} (id, {', '.join(fields)}) VALUES (1, {placeholders}) "
        f"ON CONFLICT(id) DO UPDATE SET {assignments};",
        # SQLite binds the upsert twice: once for the INSERT, once for the SET.
        values + values,
    )


def create_table(path=None):
    """Create the bookkeeping table. Idempotent, and needs no extension.

    The vector table itself is created on first use, because its dimension
    depends on the embedding model.
    """
    conn = get_conn(path)
    cursor = conn.cursor()
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {META_TABLE} (
            id INTEGER PRIMARY KEY,
            model TEXT NULL,
            dimension INTEGER NULL,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            built_at TEXT NULL,
            state TEXT NOT NULL DEFAULT 'empty'
        );
    """)
    conn.commit()
    cursor.close()
    conn.close()
    # Seed the bookkeeping row only when it is missing — an existing row
    # carries the state of a built index and must not be reset.
    meta_conn = get_conn(path)
    try:
        if not read_meta(meta_conn):
            _set_meta(meta_conn, state="empty")
            meta_conn.commit()
    finally:
        meta_conn.close()
    system_log("DATABASE", "INFO", "Vector metadata table created or already exists.")


def _ensure_meta_table(conn):
    """Make sure the bookkeeping table exists on this connection."""
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {META_TABLE} (
            id INTEGER PRIMARY KEY,
            model TEXT NULL,
            dimension INTEGER NULL,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            built_at TEXT NULL,
            state TEXT NOT NULL DEFAULT 'empty'
        );
    """)


def ensure_table(conn, dimension):
    """Create the vector table for this dimension, recreating it if the model
    changed. The index is derived, so dropping it is always safe."""
    dimension = int(dimension)
    if not load_extension(conn):
        return False
    _ensure_meta_table(conn)
    cursor = conn.cursor()
    try:
        cursor.execute(f"PRAGMA table_info({VEC_TABLE});")
        exists = bool(cursor.fetchall())
    except Exception:
        exists = False
    if exists:
        meta = read_meta(conn)
        if meta.get("dimension") == dimension and meta.get("model") == embeddings.model_name():
            cursor.close()
            return True
        # A different model or dimension: the old vectors are meaningless.
        cursor.execute(f"DROP TABLE {VEC_TABLE};")
        conn.commit()
        system_log("VECTOR", "INFO", "Vector table rebuilt for a new embedding model.")

    cursor.execute(f"""
        CREATE VIRTUAL TABLE {VEC_TABLE} USING vec0(
            chunk_id INTEGER PRIMARY KEY,
            user_id INTEGER PARTITION KEY,
            kind TEXT,
            ref_id INTEGER,
            embedding FLOAT[{dimension}] distance_metric=cosine,
            +body TEXT,
            chunk_size=64
        );
    """)
    conn.commit()
    cursor.close()
    _set_meta(
        conn,
        model=embeddings.model_name(),
        dimension=dimension,
        chunk_count=0,
        built_at=current_time(),
        state="empty",
    )
    conn.commit()
    return True


# ---------------------------------------------------------------- chunking


def chunk_id(kind, ref_id, sequence):
    """The deterministic id of one chunk."""
    return KIND_CODES.get(kind, 9) * KIND_STRIDE + int(ref_id) * CHUNK_STRIDE + int(sequence)


def split_bullets(summary):
    """Split a session summary into one chunk per fact.

    The summariser is asked for "short bullet points, one memory per line",
    so a line is already the natural unit. `N/A` and empty summaries produce
    no chunks — they are a sentinel, not a fact.
    """
    text = (summary or "").strip()
    if not text or text.upper() == "N/A":
        return []

    chunks = []
    for line in text.splitlines():
        line = _BULLET.sub("", line.strip()).strip()
        if not line or line.upper() == "N/A":
            continue
        if len(line) <= MAX_CHUNK_CHARS:
            chunks.append(line)
            continue
        # A long line is split on sentence boundaries, then hard-cut.
        piece = ""
        for sentence in _SENTENCE.split(line):
            if len(sentence) > MAX_CHUNK_CHARS:
                if piece:
                    chunks.append(piece[:MAX_CHUNK_CHARS])
                for start in range(0, len(sentence), MAX_CHUNK_CHARS):
                    chunks.append(sentence[start:start + MAX_CHUNK_CHARS])
                piece = ""
                continue
            if len(piece) + len(sentence) + 1 > MAX_CHUNK_CHARS:
                if piece:
                    chunks.append(piece)
                piece = sentence
            else:
                piece = f"{piece} {sentence}".strip()
        if piece:
            chunks.append(piece[:MAX_CHUNK_CHARS])
        if len(chunks) >= MAX_CHUNKS_PER_REF:
            break
    return chunks[:MAX_CHUNKS_PER_REF]


def chunk_memory(title, detail=""):
    """One chunk for a memory node."""
    title = (title or "").strip()
    detail = (detail or "").strip()
    text = f"{title}\n{detail}" if detail else title
    if not text:
        return []
    return [text[:MAX_CHUNK_CHARS]]


# ---------------------------------------------------------------- writes


def _refresh_count(conn):
    """Keep the cached chunk count honest."""
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM {VEC_TABLE};").fetchone()
        _set_meta(conn, chunk_count=int(row[0]) if row else 0)
    except Exception:
        pass


def insert_chunks(conn, user_id, kind, ref_id, texts, vectors):
    """Insert chunks on an existing connection, so they commit with the row
    they belong to. Returns the number of chunks written."""
    if not texts or not vectors:
        return 0
    if not ensure_table(conn, len(vectors[0])):
        return 0
    cursor = conn.cursor()
    written = 0
    for sequence, (text, vector) in enumerate(zip(texts, vectors)):
        try:
            cursor.execute(
                f"INSERT INTO {VEC_TABLE} (chunk_id, user_id, kind, ref_id, embedding, body) "
                f"VALUES (?, ?, ?, ?, ?, ?);",
                (chunk_id(kind, ref_id, sequence), int(user_id), kind, int(ref_id),
                 sqlite_vec.serialize_float32(vector), text),
            )
            written += 1
        except Exception as error:
            system_log("VECTOR", "WARNING", f"Chunk write failed for {kind}:{ref_id}: {error}")
            break
    cursor.close()
    if written:
        _refresh_count(conn)
    return written


def delete_ref(conn, kind, ref_id):
    """Delete every chunk of one source row."""
    if not load_extension(conn):
        return 0
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT chunk_id FROM {VEC_TABLE} WHERE kind = ? AND ref_id = ?;",
                       (kind, int(ref_id)))
        ids = [row[0] for row in cursor.fetchall()]
        cursor.close()
        if not ids:
            return 0
        placeholders = ",".join("?" * len(ids))
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {VEC_TABLE} WHERE chunk_id IN ({placeholders});", ids)
        removed = cursor.rowcount
        cursor.close()
        if removed:
            _refresh_count(conn)
        return max(removed, 0)
    except Exception as error:
        system_log("VECTOR", "WARNING", f"Chunk delete failed for {kind}:{ref_id}: {error}")
        return 0


def delete_user(conn, user_id, kind=None):
    """Delete the chunks of one profile, optionally limited to one kind."""
    if not load_extension(conn):
        return 0
    try:
        cursor = conn.cursor()
        if kind:
            cursor.execute(f"DELETE FROM {VEC_TABLE} WHERE user_id = ? AND kind = ?;",
                           (int(user_id), kind))
        else:
            cursor.execute(f"DELETE FROM {VEC_TABLE} WHERE user_id = ?;", (int(user_id),))
        removed = cursor.rowcount
        cursor.close()
        if removed:
            _refresh_count(conn)
        return max(removed, 0)
    except Exception as error:
        system_log("VECTOR", "WARNING", f"Chunk bulk delete failed for user {user_id}: {error}")
        return 0


# ---------------------------------------------------------------- reads


def query_vector(query):
    """Embed a query.

    The last query is cached, so the two searches a chat turn makes (memory
    and history) share one embedding instead of paying for two.
    """
    if not query:
        return None
    if _vector_cache["query"] == query and _vector_cache["vector"] is not None:
        return _vector_cache["vector"]
    vectors = embeddings.embed([query])
    vector = vectors[0] if vectors else None
    _vector_cache["query"] = query
    _vector_cache["vector"] = vector
    return vector


def search(user_id, query, kind=None, limit=8, path=None):
    """Top matching chunks for a query. Empty list on any failure."""
    vector = query_vector(query)
    if vector is None:
        return []

    conn = get_conn(path)
    try:
        if not load_extension(conn):
            return []
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT chunk_id, kind, ref_id, body, distance FROM {VEC_TABLE} "
            f"WHERE embedding MATCH ? AND k = {int(limit)} AND user_id = ?"
            + (" AND kind = ?" if kind else "") + ";",
            [sqlite_vec.serialize_float32(vector), int(user_id)]
            + ([kind] if kind else []),
        )
        rows = cursor.fetchall()
        cursor.close()
    except Exception as error:
        system_log("VECTOR", "WARNING", f"Vector search failed: {error}")
        return []
    finally:
        conn.close()

    hits = []
    for chunk_id_value, row_kind, ref_id, body, distance in rows:
        hits.append({
            "chunk_id": chunk_id_value,
            "kind": row_kind,
            "ref_id": ref_id,
            "body": body,
            "distance": distance,
            "similarity": max(0.0, 1.0 - float(distance)),
        })
    return hits


# ---------------------------------------------------------------- rebuild


def rebuild(user_id=None, log=None):
    """Rebuild the whole index from the source tables.

    Idempotent and resumable: every source row that already has chunks is
    skipped, and each batch commits on its own.
    """
    if not available():
        system_log("VECTOR", "WARNING", "Rebuild skipped: sqlite-vec is unavailable.")
        return 0

    import history_db
    import memory_db

    conn = get_conn()
    if not load_extension(conn):
        conn.close()
        return 0
    try:
        cursor = conn.cursor()
        cursor.execute(f"DROP TABLE IF EXISTS {VEC_TABLE};")
        conn.commit()
        cursor.close()
        _set_meta(conn, model=embeddings.model_name(), dimension=None, chunk_count=0,
                  built_at=current_time(), state="building")
        conn.commit()
    except Exception as error:
        system_log("VECTOR", "WARNING", f"Rebuild could not reset the index: {error}")
        conn.close()
        return 0

    total = 0
    try:
        if user_id is None:
            rows = conn.execute("SELECT Session_id, user_id, summary FROM history;").fetchall()
        else:
            rows = conn.execute(
                "SELECT Session_id, user_id, summary FROM history WHERE user_id = ?;",
                (int(user_id),),
            ).fetchall()
        for session_id, owner, summary in rows:
            texts = split_bullets(summary)
            if not texts:
                continue
            vectors = embeddings.embed(texts)
            if not vectors:
                continue
            total += insert_chunks(conn, owner, KIND_HISTORY, session_id, texts, vectors)
            conn.commit()
            if log:
                log(f"Indexed session {session_id}")

        where = "WHERE status = 'active'"
        params = ()
        if user_id is not None:
            where += " AND user_id = ?"
            params = (int(user_id),)
        nodes = conn.execute(
            f"SELECT id, user_id, title, detail FROM profile_memory {where};", params
        ).fetchall()
        for node_id, owner, title, detail in nodes:
            texts = chunk_memory(title, detail or "")
            if not texts:
                continue
            vectors = embeddings.embed(texts)
            if not vectors:
                continue
            total += insert_chunks(conn, owner, KIND_MEMORY, node_id, texts, vectors)
            conn.commit()
            if log:
                log(f"Indexed memory {node_id}")
    except Exception as error:
        system_log("VECTOR", "WARNING", f"Rebuild stopped: {error}")
    finally:
        conn.close()

    meta_conn = get_conn()
    try:
        _set_meta(meta_conn, chunk_count=total, state="ready", built_at=current_time())
        meta_conn.commit()
    finally:
        meta_conn.close()
    system_log("VECTOR", "INFO", f"Vector index rebuilt with {total} chunk(s).")
    return total


def stats():
    """A small summary for the status payload and the Settings page."""
    meta = read_meta()
    extension = available()
    model_ready = False
    try:
        import ollama
        ollama.list()
        model_ready = True
    except Exception:
        model_ready = False
    return {
        "available": extension,
        "model": embeddings.model_name(),
        "dimension": meta.get("dimension"),
        "chunks": meta.get("chunk_count", 0),
        "built_at": meta.get("built_at"),
        "state": meta.get("state", "empty"),
        "ollama": model_ready,
    }


if __name__ == "__main__":
    import sys

    create_table()
    if "--stats" in sys.argv:
        print(stats())
    else:
        print(f"Rebuilt {rebuild()} chunk(s).")
