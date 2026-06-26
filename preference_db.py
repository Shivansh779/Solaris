import sqlite3

DB_PATH = 'database.db'

def get_conn():
    return sqlite3.connect(DB_PATH)

def create_table():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            CREATE TABLE IF NOT EXISTS user_pref (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                prefers TEXT NOT NULL,
                is_private INTEGER NOT NULL DEFAULT 0,   --0 Public, 1 = Private
                password TEXT NULL
            );
        """
    )
    conn.commit()
    cursor.close()
    conn.close()

def fetch_privacy_setting (user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            SELECT is_private FROM user_pref WHERE user_id =?;
        """, (user_id,)
    )
    data = cursor.fetchone()
    cursor.close()
    conn.close()
    return data[0] if data else 0

def fetch_password(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            SELECT password FROM user_pref WHERE user_id = ?;
        """, (user_id,)
    )
    data = cursor.fetchone()
    cursor.close()
    conn.close()
    return data[0] if data else 0

def check_existing ():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            SELECT user_id, name FROM user_pref ORDER BY user_id ASC;
        """
    )
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return data

def get_preference (user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            SELECT prefers, name FROM user_pref WHERE user_id = ?;
        """,
        (user_id,)
    )
    data = cursor.fetchone()
    cursor.close()
    conn.close()
    return data

def new_user (name, preference, is_private):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            INSERT INTO user_pref (name, prefers, is_private) VALUES(?, ?, ?);
        """, (name, preference, is_private)
    )
    conn.commit()
    user_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return user_id

def update_user_pref (user_id, preference):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            UPDATE user_pref SET prefers = ? WHERE user_id = ?;
        """, (preference, user_id)
    )
    conn.commit()
    cursor.close()
    conn.close()

def fetch_user_id (name):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            SELECT user_id FROM user_pref WHERE name = ?;
        """, (name,)
    )
    data = cursor.fetchone()
    cursor.close()
    conn.close()
    return data