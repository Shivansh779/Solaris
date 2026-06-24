import sqlite3
import random
import string

conn = sqlite3.connect('preferences.db')
cursor = conn.cursor()

def generate_user_id():
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=6))

def create_table():
    cursor.execute(
        """
            CREATE TABLE IF NOT EXISTS user_pref (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                prefers TEXT NOT NULL
            );
        """
    )
    conn.commit()

def check_existing (user_id):
    cursor.execute(
        """
            SELECT user_id FROM user_pref WHERE user_id = ?;
        """,
        (user_id,)
    )

    return cursor.fetchone() is not None

def get_preference (user_id):
    cursor.execute(
        """
            SELECT prefers, name FROM user_pref WHERE user_id = ?;
        """,
        (user_id,)
    )
    return cursor.fetchone()

def new_user (name, preference):
    user_id = generate_user_id()
    cursor.execute(
        """
            INSERT INTO user_pref (user_id, name, prefers) VALUES(?, ?, ?);
        """, (user_id, name, preference)
    )
    conn.commit()
    return user_id



