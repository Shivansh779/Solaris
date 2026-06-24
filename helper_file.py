import sqlite3
import random
import string

conn = sqlite3.connect('preferences.db')
cursor = conn.cursor()

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

def check_existing ():
    cursor.execute(
        """
            SELECT user_id, name FROM user_pref ORDER BY user_id ASC;
        """
    )
    return cursor.fetchone()

def get_preference (user_id):
    cursor.execute(
        """
            SELECT prefers, name FROM user_pref WHERE user_id = ?;
        """,
        (user_id,)
    )
    return cursor.fetchone()

def new_user (name, preference):
    cursor.execute(
        """
            INSERT INTO user_pref (name, prefers) VALUES(?, ?);
        """, (name, preference)
    )
    conn.commit()



check_existing()