import sqlite3

DB_PATH = 'preferences.db'

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
                prefers TEXT NOT NULL
            );
        """
    )
    conn.commit()
    cursor.close()
    conn.close()

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
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return data

def new_user (name, preference):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            INSERT INTO user_pref (name, prefers) VALUES(?, ?);
        """, (name, preference)
    )
    conn.commit()
    cursor.close()
    conn.close()