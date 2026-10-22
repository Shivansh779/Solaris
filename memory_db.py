"""Constellation Memory: profile-scoped, inspectable memory nodes.

Every row belongs to one profile and is one of:
    active     — part of the profile's working memory
    suggested  — extracted from chat, waiting for the user to approve
    archived   — kept but no longer used

Only `active` rows ever reach the model, and only as a compact context block.
"""

import sqlite3

from _log import system_log, current_time

import embeddings
import vec_db

DB_PATH = "database.db"

CATEGORIES = ("preferences", "personal", "projects", "learning", "working_style", "custom")

CATEGORY_LABELS = {
    "preferences": "Preferences",
    "personal": "Personal context",
    "projects": "Projects",
    "learning": "Learning",
    "working_style": "Working style",
    "custom": "Custom",
}

SOURCES = ("user", "extracted", "imported")
STATUSES = ("active", "suggested", "archived")

# How many active memories may be handed to the model in one request.
CONTEXT_LIMIT = 8

# How many vector hits the semantic search may contribute to one ranking.
VECTOR_HITS = 64

# How much a semantic hit outweighs one keyword hit.
VECTOR_WEIGHT = 6.0


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_table():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profile_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            detail TEXT,
            source TEXT NOT NULL DEFAULT 'user',
            status TEXT NOT NULL DEFAULT 'active',
            confidence REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES user_data (user_id)
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_user_status ON profile_memory (user_id, status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_user_category ON profile_memory (user_id, category);")
    conn.commit()
    system_log("DATABASE", "INFO", "Constellation memory table created or already exists.")
    cursor.close()
    conn.close()
    _ensure_vector_table()


# ---------------------------------------------------------------- vectors
#
# The vector index is derived from these rows: it may be missing, stale or
# empty, and the memory itself must never depend on it. Every call below is
# therefore wrapped, and a failure only costs relevance, never a node.


def _ensure_vector_table():
    """The bookkeeping table of the vector index. Needs no extension."""
    try:
        vec_db.create_table()
    except Exception as error:
        system_log("MEMORY", "WARNING", f"Vector bookkeeping table skipped: {error}")


def _embed_node(title, detail=""):
    """The (text, vector) pairs of one node. Empty when the model is offline."""
    try:
        texts = vec_db.chunk_memory(title, detail)
        if not texts:
            return []
        vectors = embeddings.embed(texts)
        if not vectors or len(vectors) != len(texts):
            return []
        return list(zip(texts, vectors))
    except Exception as error:
        system_log("MEMORY", "WARNING", f"Memory embedding skipped: {error}")
        return []


def _node_row(user_id, memory_id):
    """The status, title and detail of one node. None when it is not theirs."""
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT status, title, detail FROM profile_memory WHERE id = ? AND user_id = ?;",
            (memory_id, user_id),
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()
    return row


def _load_extension(conn):
    """Put the vector extension on this connection. False when it cannot load."""
    try:
        return bool(vec_db.load_extension(conn))
    except Exception as error:
        system_log("MEMORY", "WARNING", f"Vector extension unavailable: {error}")
        return False


def _write_chunks(conn, user_id, memory_id, pairs):
    """Replace the chunks of one node on the caller's connection.

    Always delete-then-insert, so a status flip never leaves a stale vector.
    The extension is loaded here: the delete needs it on this very connection.
    """
    try:
        _load_extension(conn)
        vec_db.delete_ref(conn, vec_db.KIND_MEMORY, memory_id)
        if not pairs:
            return 0
        texts = [text for text, _ in pairs]
        vectors = [vector for _, vector in pairs]
        return vec_db.insert_chunks(conn, user_id, vec_db.KIND_MEMORY, memory_id, texts, vectors)
    except Exception as error:
        system_log("MEMORY", "WARNING", f"Memory vector write skipped: {error}")
        return 0


def _similarities(user_id, query):
    """Cosine similarity per node id, from the vector index."""
    scores = {}
    for hit in vec_db.search(user_id, query, kind=vec_db.KIND_MEMORY, limit=VECTOR_HITS) or []:
        ref_id = hit.get("ref_id")
        if ref_id is None:
            continue
        similarity = float(hit.get("similarity") or 0.0)
        if similarity > scores.get(int(ref_id), 0.0):
            scores[int(ref_id)] = similarity
    return scores


# ---------------------------------------------------------------- writes


def add_memory(user_id, category, title, detail="", source="user", status="active", confidence=None):
    """Add one memory node. Returns its id."""
    category = category if category in CATEGORIES else "custom"
    title = (title or "").strip()
    if not title:
        raise ValueError("Memory needs a title.")
    if status not in STATUSES:
        status = "active"
    if source not in SOURCES:
        source = "user"
    detail = (detail or "").strip()
    now = current_time()
    # Embed before the write connection opens: never hold a SQLite write lock
    # across a round trip to Ollama. Only active nodes are ever retrieved, so
    # only they are worth embedding.
    pairs = _embed_node(title, detail) if status == "active" else []
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO profile_memory
            (user_id, category, title, detail, source, status, confidence, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (user_id, category, title, detail, source, status, confidence, now, now))
    memory_id = cursor.lastrowid
    if pairs:
        _write_chunks(conn, user_id, memory_id, pairs)
    conn.commit()
    cursor.close()
    conn.close()
    system_log("MEMORY", "INFO", f"Memory node {memory_id} stored for user_id={user_id} ({status}).")
    return memory_id


def update_memory(user_id, memory_id, category=None, title=None, detail=None):
    """Edit title/detail/category. Scoped to the owner; returns False if not theirs."""
    fields, values = [], []
    if category is not None:
        if category not in CATEGORIES:
            raise ValueError("Unknown memory category.")
        fields.append("category = ?")
        values.append(category)
    if title is not None:
        if not title.strip():
            raise ValueError("Memory needs a title.")
        fields.append("title = ?")
        values.append(title.strip())
    if detail is not None:
        fields.append("detail = ?")
        values.append((detail or "").strip())
    if not fields:
        return True
    fields.append("updated_at = ?")
    values.append(current_time())
    values.extend([memory_id, user_id])
    # The status decides whether the node is embedded at all, and the untouched
    # fields are part of the new chunk text. Read them before the write
    # connection opens, so no lock is held while Ollama is called.
    current = _node_row(user_id, memory_id)
    if current is None:
        return False
    status, old_title, old_detail = current
    new_title = title.strip() if title is not None else old_title
    new_detail = (detail or "").strip() if detail is not None else (old_detail or "")
    pairs = _embed_node(new_title, new_detail) if status == "active" else []
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE profile_memory SET {', '.join(fields)} WHERE id = ? AND user_id = ?;", values)
    changed = cursor.rowcount > 0
    if changed:
        _write_chunks(conn, user_id, memory_id, pairs)
    conn.commit()
    cursor.close()
    conn.close()
    return changed


def set_status(user_id, memory_id, status):
    if status not in STATUSES:
        raise ValueError("Unknown memory status.")
    # A node that becomes active needs its vector; one that leaves the active
    # set loses it. Read the text before the write connection opens.
    pairs = []
    if status == "active":
        current = _node_row(user_id, memory_id)
        if current is not None:
            pairs = _embed_node(current[1], current[2] or "")
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE profile_memory SET status = ?, updated_at = ? WHERE id = ? AND user_id = ?;",
        (status, current_time(), memory_id, user_id),
    )
    changed = cursor.rowcount > 0
    if changed:
        _write_chunks(conn, user_id, memory_id, pairs)
    conn.commit()
    cursor.close()
    conn.close()
    return changed


def delete_memory(user_id, memory_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM profile_memory WHERE id = ? AND user_id = ?;", (memory_id, user_id))
    changed = cursor.rowcount > 0
    if changed:
        _write_chunks(conn, user_id, memory_id, [])
    conn.commit()
    cursor.close()
    conn.close()
    if changed:
        system_log("MEMORY", "INFO", f"Memory node {memory_id} forgotten for user_id={user_id}.")
    return changed


def clear_profile(user_id):
    """Forget everything for one profile. Returns the number of nodes removed."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM profile_memory WHERE user_id = ?;", (user_id,))
    removed = cursor.rowcount
    try:
        _load_extension(conn)
        vec_db.delete_user(conn, user_id, kind=vec_db.KIND_MEMORY)
    except Exception as error:
        system_log("MEMORY", "WARNING", f"Memory vectors not cleared: {error}")
    conn.commit()
    cursor.close()
    conn.close()
    system_log("MEMORY", "WARNING", f"Cleared {removed} memory node(s) for user_id={user_id}.")
    return removed


def clear_suggestions(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM profile_memory WHERE user_id = ? AND status = 'suggested';", (user_id,))
    conn.commit()
    removed = cursor.rowcount
    cursor.close()
    conn.close()
    return removed


def existing_titles(user_id):
    """Lower-cased titles for the active and suggested nodes (dedupe for extraction)."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT LOWER(title) FROM profile_memory WHERE user_id = ? AND status != 'archived';",
        (user_id,),
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {row[0] for row in rows}


# ---------------------------------------------------------------- reads


def get_memory(user_id, memory_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, category, title, detail, source, status, confidence, created_at, updated_at
          FROM profile_memory WHERE id = ? AND user_id = ?;
    """, (memory_id, user_id))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return _as_dict(row) if row else None


def list_memories(user_id, status=None, category=None):
    """Memory nodes for one profile, newest first."""
    clauses, values = ["user_id = ?"], [user_id]
    if status:
        if status not in STATUSES:
            raise ValueError("Unknown memory status.")
        clauses.append("status = ?")
        values.append(status)
    if category:
        clauses.append("category = ?")
        values.append(category)
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT id, user_id, category, title, detail, source, status, confidence, created_at, updated_at
          FROM profile_memory WHERE {' AND '.join(clauses)}
         ORDER BY updated_at DESC, id DESC;
    """, values)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [_as_dict(row) for row in rows]


def counts(user_id):
    """{'active': n, 'suggested': n, 'archived': n} for badges."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status, COUNT(*) FROM profile_memory WHERE user_id = ? GROUP BY status;",
        (user_id,),
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    counts_map = {status: 0 for status in STATUSES}
    for status, count in rows:
        counts_map[status] = count
    return counts_map


def build_context(user_id, query="", limit=CONTEXT_LIMIT, exclude_ids=None):
    """Compact block of the most relevant active memories for one request.

    Relevance is category + keyword overlap with the current question, plus
    the semantic similarity of the vector index; the model never receives the
    whole memory store. An excluded node (manifest id "memory:12" or the plain
    id) is left out of the text and of the used list.
    """
    memories = list_memories(user_id, status="active")
    if not memories:
        return "", []

    excluded = set(exclude_ids or ())
    if excluded:
        memories = [node for node in memories if not _excluded(node["id"], excluded)]
        if not memories:
            return "", []

    words = {w for w in _words(query) if len(w) > 3}

    # The vector block is optional: without it the ranking is exactly the
    # keyword ranking it always was. It must never break a reply.
    similarity = {}
    try:
        similarity = _similarities(user_id, query)
    except Exception as error:
        system_log("MEMORY", "WARNING", f"Semantic ranking skipped: {error}")

    def score(memory):
        text = f"{memory['title']} {memory['detail'] or ''}".lower()
        overlap = len(words & _words(text))
        # Preferences and working style shape every answer; the rest compete on relevance.
        base = 2 if memory["category"] in ("preferences", "working_style") else 0
        semantic = VECTOR_WEIGHT * similarity.get(memory["id"], 0.0)
        return (overlap * 3 + base + semantic, memory["updated_at"])

    ranked = sorted(memories, key=score, reverse=True)[:limit]
    lines, used = [], []
    for memory in ranked:
        line = f"- [{CATEGORY_LABELS.get(memory['category'], memory['category'])}] {memory['title']}"
        if memory["detail"]:
            line += f" — {memory['detail']}"
        lines.append(line)
        # "size" is how many characters this node contributed to the prompt.
        used.append({
            "id": memory["id"],
            "category": memory["category"],
            "title": memory["title"],
            "size": len(line),
        })
    return "\n".join(lines), used


def _excluded(memory_id, excluded):
    """True when this node is excluded, by manifest id ("memory:12") or plain id."""
    return f"memory:{memory_id}" in excluded or str(memory_id) in excluded


def _words(text):
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in (text or ""))
    return set(cleaned.split())


def _as_dict(row):
    keys = ("id", "user_id", "category", "title", "detail", "source",
            "status", "confidence", "created_at", "updated_at")
    return dict(zip(keys, row))


# ---------------------------------------------------------------- extraction


# Explicit, self-describing statements only — silence beats noisy guesses.
_SUGGESTION_PATTERNS = (
    ("preferences", ("i prefer", "i like", "i don't like", "i dislike", "please always", "please never",
                     "i want you to always", "keep answers")),
    ("learning", ("i'm learning", "i am learning", "i'm studying", "i am studying",
                  "i'm trying to learn", "i want to learn")),
    ("projects", ("my project", "i'm building", "i am building", "i'm working on", "i am working on",
                  "we're building", "we are building")),
    ("working_style", ("i like to see", "show me the plan", "before you code", "i prefer to review",
                       "explain first", "walk me through")),
    ("personal", ("i work as", "i live in", "my timezone", "remember that")),
)

MAX_TITLE = 120


def extract_suggestions(user_id, message):
    """Turn one user message into at most a couple of *suggested* memory nodes.

    Nothing becomes active memory without approval: suggestions land with
    status='suggested' and wait for the user in the Memory view.
    """
    text = (message or "").strip()
    if not text or len(text) > 600:
        return []
    lowered = text.lower()
    if lowered.startswith("."):
        return []

    known = existing_titles(user_id)
    created = []
    for category, markers in _SUGGESTION_PATTERNS:
        if category in [c[0] for c in created]:
            continue
        for marker in markers:
            index = lowered.find(marker)
            if index == -1:
                continue
            snippet = text[index:].strip().rstrip(".!?")
            snippet = snippet.split("\n")[0].strip()
            if not snippet:
                continue
            title = snippet[:MAX_TITLE].strip()
            if len(title) < 8 or title.lower() in known:
                continue
            memory_id = add_memory(
                user_id, category, title,
                detail="", source="extracted", status="suggested", confidence=0.5,
            )
            created.append((category, memory_id))
            known.add(title.lower())
            break
    return created
