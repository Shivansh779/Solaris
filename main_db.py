import hashlib
import hmac
import os
import secrets
import sqlite3
import string
import time
from datetime import datetime

from _log import system_log, current_time

DB_PATH = 'database.db'

# API keys are app-wide, not per profile: the hash always lives on the
# lowest user_id row, whatever profile is currently selected.
PBKDF2_ITERATIONS = 200_000
PASSWORD_LENGTH = 6
PASSWORD_ALPHABET = string.ascii_uppercase + string.digits

# Profile access (separate from the app-wide API password):
#   visibility/state are canonical, is_private/is_active stay as legacy mirrors
#   for older readers (helper_ai.current_profile_info / profiles_data).
VISIBILITY_PUBLIC = "public"
VISIBILITY_PRIVATE = "private"
STATE_ACTIVE = "active"
STATE_INACTIVE = "inactive"

# No I/O/0/1: activation codes are read off a screen and typed back in.
ACTIVATION_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ACTIVATION_LENGTH = 8

# Failed activation/password attempts before a profile is temporarily locked.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 60

ACCESS_COLUMNS = {
    "visibility": "TEXT NOT NULL DEFAULT 'public'",
    "state": "TEXT NOT NULL DEFAULT 'active'",
    "activation_code_hash": "TEXT NULL",
    "profile_password_hash": "TEXT NULL",
    "failed_attempts": "INTEGER NOT NULL DEFAULT 0",
    "lockout_until": "REAL NULL",
    "created_at": "TEXT NULL",
    "updated_at": "TEXT NULL",
    "last_active": "TEXT NULL",
}


def _hash_secret(secret):
    """PBKDF2-SHA256 in the same self-describing format as the API password."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", str(secret).encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_secret(secret, stored):
    """Constant-time check of a secret against a stored PBKDF2 hash."""
    if not stored:
        return False
    try:
        _, iterations, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", str(secret).encode(), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, AttributeError):
        system_log("SECURITY", "ERROR", "Stored secret hash is malformed.")
        return False

def get_conn():
    return sqlite3.connect(DB_PATH)

def create_table():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            CREATE TABLE IF NOT EXISTS user_data (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                prefers TEXT NOT NULL,
                about_user TEXT NOT NULL,
                is_private INTEGER NOT NULL DEFAULT 0,   --0 = Public, 1 = Private
                password TEXT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,    --0 = Inactive, 1 = Active
                activation_code TEXT NULL
            );
        """
    )
    conn.commit()
    system_log("DATABASE", "INFO", "User profile table created or already exists.")
    cursor.close()
    conn.close()
    _ensure_api_password_column()
    _ensure_profile_access_columns()

def _ensure_api_password_column():
    """Add the api_password_hash column to databases created before it existed."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(user_data);")
    columns = [row[1] for row in cursor.fetchall()]
    if "api_password_hash" not in columns:
        cursor.execute("ALTER TABLE user_data ADD COLUMN api_password_hash TEXT NULL;")
        conn.commit()
        system_log("DATABASE", "INFO", "Added api_password_hash column to user_data.")
    cursor.close()
    conn.close()


def _ensure_profile_access_columns():
    """Add profile access columns and backfill them for existing databases.

    Existing rows default to public + active. Profile content that older builds
    stored in plain text (legacy `password` / `activation_code` columns) is
    hashed in place so no raw secret is kept, and the plain text is cleared.
    """
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(user_data);")
    columns = {row[1] for row in cursor.fetchall()}

    added = [name for name in ACCESS_COLUMNS if name not in columns]
    for name in added:
        cursor.execute(f"ALTER TABLE user_data ADD COLUMN {name} {ACCESS_COLUMNS[name]};")
    if added:
        conn.commit()
        system_log("DATABASE", "INFO", "Added profile access columns: " + ", ".join(added))

    # Backfill from the legacy mirrors. Only on the run that added the column —
    # afterwards visibility/state are the source of truth and must not be reset.
    if "visibility" in added:
        cursor.execute("""
            UPDATE user_data
               SET visibility = CASE WHEN is_private = 1 THEN 'private' ELSE 'public' END;
        """)
    if "state" in added:
        cursor.execute("""
            UPDATE user_data
               SET state = CASE WHEN is_active = 0 THEN 'inactive' ELSE 'active' END;
        """)
    cursor.execute("""
        UPDATE user_data
           SET visibility = COALESCE(NULLIF(visibility, ''), 'public'),
               state = COALESCE(NULLIF(state, ''), 'active');
    """)
    cursor.execute("UPDATE user_data SET created_at = COALESCE(created_at, ?) WHERE created_at IS NULL;", (current_time(),))
    conn.commit()

    _migrate_legacy_secrets(cursor)
    conn.commit()
    cursor.close()
    conn.close()


def _migrate_legacy_secrets(cursor):
    """Hash any plain-text legacy profile secrets, then drop the plain text."""
    columns = _table_columns(cursor)
    if not {"password", "activation_code"} <= columns:
        return
    cursor.execute("""
        SELECT user_id, is_private, password, activation_code,
               profile_password_hash, activation_code_hash
          FROM user_data;
    """)
    migrated = 0
    for user_id, is_private, legacy_password, legacy_code, password_hash, code_hash in cursor.fetchall():
        if not password_hash and (legacy_password or "").strip():
            cursor.execute(
                "UPDATE user_data SET profile_password_hash = ? WHERE user_id = ?;",
                (_hash_secret(legacy_password.strip()), user_id),
            )
            migrated += 1
        if not code_hash and (legacy_code or "").strip():
            cursor.execute(
                "UPDATE user_data SET activation_code_hash = ? WHERE user_id = ?;",
                (_hash_secret(_normalize_activation(legacy_code)), user_id),
            )
            migrated += 1
        # Only wipe the plain text once a hash exists for it.
        cursor.execute("""
            UPDATE user_data
               SET password = CASE WHEN profile_password_hash IS NOT NULL THEN NULL ELSE password END,
                   activation_code = CASE WHEN activation_code_hash IS NOT NULL THEN NULL ELSE activation_code END
             WHERE user_id = ?;
        """, (user_id,))
    if migrated:
        system_log("SECURITY", "INFO", f"Migrated {migrated} legacy profile secret(s) to hashes.")


def _table_columns(cursor):
    cursor.execute("PRAGMA table_info(user_data);")
    return {row[1] for row in cursor.fetchall()}


def _normalize_activation(code):
    """'abcd-efgh' / 'ABCDEFGH' / 'abcd efgh' -> 'ABCDEFGH'."""
    return "".join(ch for ch in str(code or "").upper() if ch.isalnum())


def generate_activation_code():
    """Cryptographically secure activation code, displayed as ABCD-EFGH."""
    raw = "".join(secrets.choice(ACTIVATION_ALPHABET) for _ in range(ACTIVATION_LENGTH))
    return f"{raw[:4]}-{raw[4:]}"


def format_activation_code(code):
    raw = _normalize_activation(code)
    return f"{raw[:4]}-{raw[4:]}" if len(raw) == ACTIVATION_LENGTH else raw


# ---------------------------------------------------------------- access rows


def _access_row(cursor, user_id):
    cursor.execute("""
        SELECT visibility, state, activation_code_hash, profile_password_hash,
               failed_attempts, lockout_until
          FROM user_data WHERE user_id = ?;
    """, (user_id,))
    return cursor.fetchone()


def get_access(user_id):
    """Safe access metadata for one profile (never includes hashes)."""
    conn = get_conn()
    cursor = conn.cursor()
    row = _access_row(cursor, user_id)
    cursor.close()
    conn.close()
    if row is None:
        return None
    visibility, state, code_hash, password_hash, attempts, lockout_until = row
    return {
        "user_id": user_id,
        "visibility": visibility or VISIBILITY_PUBLIC,
        "state": state or STATE_ACTIVE,
        "has_activation_code": bool(code_hash),
        "has_profile_password": bool(password_hash),
        "locked_for": lockout_remaining(user_id),
    }


def safe_profiles():
    """Profile list for the UI: metadata only, no preference/about/memory content."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, name, visibility, state, activation_code_hash,
               profile_password_hash, lockout_until
          FROM user_data ORDER BY user_id ASC;
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    now = time.time()
    profiles = []
    for user_id, name, visibility, state, code_hash, password_hash, lockout_until in rows:
        visibility = visibility or VISIBILITY_PUBLIC
        state = state or STATE_ACTIVE
        profiles.append({
            "user_id": user_id,
            "name": name,
            "visibility": visibility,
            "state": state,
            "has_password": bool(password_hash),
            "has_activation_code": bool(code_hash),
            "locked_for": max(0, int((lockout_until or 0) - now)),
            "unlock_required": state == STATE_INACTIVE or (visibility == VISIBILITY_PRIVATE),
        })
    return profiles


def set_visibility(user_id, visibility):
    if visibility not in (VISIBILITY_PUBLIC, VISIBILITY_PRIVATE):
        raise ValueError("Unknown visibility.")
    _set_access_field(user_id, "visibility", visibility)
    if visibility == VISIBILITY_PUBLIC:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE user_data SET profile_password_hash = NULL WHERE user_id = ?;", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
    return True


def set_state(user_id, state):
    if state not in (STATE_ACTIVE, STATE_INACTIVE):
        raise ValueError("Unknown state.")
    _set_access_field(user_id, "state", state)
    return True


def _set_access_field(user_id, field, value):
    """Write visibility/state and keep the legacy mirror column in step."""
    mirror = {"visibility": "is_private", "state": "is_active"}[field]
    mirror_value = {
        "visibility": 1 if value == VISIBILITY_PRIVATE else 0,
        "state": 1 if value == STATE_ACTIVE else 0,
    }[field]
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE user_data SET {field} = ?, {mirror} = ?, updated_at = ? WHERE user_id = ?;",
        (value, mirror_value, current_time(), user_id),
    )
    conn.commit()
    cursor.close()
    conn.close()
    system_log("PROFILE", "INFO", f"Profile {user_id} {field} set to {value}.")


def touch_last_active(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE user_data SET last_active = ? WHERE user_id = ?;", (current_time(), user_id))
    conn.commit()
    cursor.close()
    conn.close()


# ---------------------------------------------------------------- credentials


def issue_activation_code(user_id):
    """Generate a new activation code, store only its hash, return the display form."""
    code = generate_activation_code()
    set_activation_code(user_id, code)
    return code


def set_activation_code(user_id, code):
    raw = _normalize_activation(code)
    if len(raw) != ACTIVATION_LENGTH:
        raise ValueError(f"Activation codes are {ACTIVATION_LENGTH} characters.")
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE user_data SET activation_code_hash = ?, activation_code = NULL, updated_at = ? WHERE user_id = ?;",
        (_hash_secret(raw), current_time(), user_id),
    )
    conn.commit()
    cursor.close()
    conn.close()
    system_log("SECURITY", "INFO", f"Activation code hash stored for user_id={user_id}.")
    return True


def verify_activation_code(user_id, code):
    conn = get_conn()
    cursor = conn.cursor()
    row = _access_row(cursor, user_id)
    cursor.close()
    conn.close()
    if row is None:
        return False
    return _verify_secret(_normalize_activation(code), row[2])


def set_profile_password(user_id, password):
    """Set (or replace) a private profile's password. Never stores plain text."""
    password = (password or "").strip()
    if len(password) < 4:
        raise ValueError("Profile passwords need at least 4 characters.")
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE user_data SET profile_password_hash = ?, password = NULL, updated_at = ? WHERE user_id = ?;",
        (_hash_secret(password), current_time(), user_id),
    )
    conn.commit()
    cursor.close()
    conn.close()
    system_log("SECURITY", "INFO", f"Profile password hash stored for user_id={user_id}.")
    return True


def verify_profile_password(user_id, password):
    conn = get_conn()
    cursor = conn.cursor()
    row = _access_row(cursor, user_id)
    cursor.close()
    conn.close()
    if row is None:
        return False
    return _verify_secret(password or "", row[3])


def has_profile_password(user_id):
    access = get_access(user_id)
    return bool(access and access["has_profile_password"])


# ---------------------------------------------------------------- throttling


def lockout_remaining(user_id):
    """Seconds left on this profile's credential lockout (0 when unlocked)."""
    conn = get_conn()
    cursor = conn.cursor()
    row = _access_row(cursor, user_id)
    cursor.close()
    conn.close()
    if row is None or not row[5]:
        return 0
    return max(0, int(row[5] - time.time()))


def register_failed_attempt(user_id):
    """Count a failed credential attempt; returns seconds of lockout applied."""
    conn = get_conn()
    cursor = conn.cursor()
    row = _access_row(cursor, user_id)
    if row is None:
        cursor.close()
        conn.close()
        return 0
    attempts = (row[4] or 0) + 1
    lockout_until = None
    if attempts >= MAX_FAILED_ATTEMPTS:
        attempts = 0
        lockout_until = time.time() + LOCKOUT_SECONDS
    cursor.execute(
        "UPDATE user_data SET failed_attempts = ?, lockout_until = ? WHERE user_id = ?;",
        (attempts, lockout_until, user_id),
    )
    conn.commit()
    cursor.close()
    conn.close()
    system_log("SECURITY", "WARNING", f"Failed profile credential attempt for user_id={user_id}.")
    return LOCKOUT_SECONDS if lockout_until else 0


def reset_failed_attempts(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE user_data SET failed_attempts = 0, lockout_until = NULL WHERE user_id = ?;",
        (user_id,),
    )
    conn.commit()
    cursor.close()
    conn.close()

def _primary_user_id(cursor):
    cursor.execute("SELECT user_id FROM user_data ORDER BY user_id ASC LIMIT 1;")
    row = cursor.fetchone()
    return row[0] if row else None

def generate_api_password():
    """Return a fresh 6 character password (uppercase letters and digits)."""
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH))

def api_password_set():
    """True when an API password hash has been stored."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT api_password_hash FROM user_data ORDER BY user_id ASC LIMIT 1;")
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return bool(row and row[0])

def set_api_password(password):
    """Hash and store the API password. Returns False when no profile exists yet."""
    stored = _hash_secret(password)

    conn = get_conn()
    cursor = conn.cursor()
    user_id = _primary_user_id(cursor)
    if user_id is None:
        cursor.close()
        conn.close()
        return False
    cursor.execute("UPDATE user_data SET api_password_hash = ? WHERE user_id = ?;", (stored, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    system_log("SECURITY", "INFO", "API password hash stored for user_id=%s." % user_id)
    return True

def verify_api_password(password):
    """Check a password against the stored hash."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT api_password_hash FROM user_data ORDER BY user_id ASC LIMIT 1;")
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if not row or not row[0]:
        return False
    return _verify_secret(password, row[0])

def check_existing ():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            SELECT user_id, name FROM user_data ORDER BY user_id ASC;
        """
    )
    data = cursor.fetchall()
    system_log("DATABASE", "INFO", "Retrieved existing user profiles.")
    cursor.close()
    conn.close()
    return data

def get_data (user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            SELECT prefers, name, about_user FROM user_data WHERE user_id = ?;
        """,
        (user_id,)
    )
    data = cursor.fetchone()
    system_log("DATABASE", "INFO", f"Retrieved preferences for user_id={user_id}.")
    cursor.close()
    conn.close()
    return data

def new_user (name, preference, about_user):
    conn = get_conn()
    cursor = conn.cursor()
    now = current_time()
    cursor.execute(
        """
            INSERT INTO user_data (name, prefers, about_user, is_private, is_active,
                                   visibility, state, created_at, updated_at, last_active)
            VALUES (?, ?, ?, 0, 1, 'public', 'active', ?, ?, ?);
        """, (name, preference, about_user, now, now, now)
    )
    conn.commit()
    user_id = cursor.lastrowid
    cursor.close()
    conn.close()
    # Every profile starts with an activation code; only its hash is kept.
    issue_activation_code(user_id)
    system_log("DATABASE", "INFO", f"Inserted new user profile with user_id={user_id}.")
    return user_id

def update_user_pref (user_id, preference):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            UPDATE user_data SET prefers = ? WHERE user_id = ?;
        """, (preference, user_id)
    )
    conn.commit()
    system_log("DATABASE", "INFO", f"Updated preferences for user_id={user_id}.")
    cursor.close()
    conn.close()

def update_about_user (about_user, user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE user_data SET about_user = ? WHERE user_id = ?;
    """, (about_user, user_id)
    )
    conn.commit()
    system_log("DATABASE", "INFO", f"Updated about user_id={user_id}.")
    cursor.close()
    conn.close()

def fetch_user_id (name):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            SELECT user_id FROM user_data WHERE name = ?;
        """, (name,)
    )
    data = cursor.fetchone()
    system_log("DATABASE", "INFO", "Retrieved user_id by profile name.")
    cursor.close()
    conn.close()
    return data
