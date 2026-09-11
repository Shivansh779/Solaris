import sqlite3
from datetime import datetime

from _log import system_log, current_time

DB_PATH = 'database.db'

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
    cursor.execute(
        """
            INSERT INTO user_data (name, prefers, about_user) VALUES (?, ?, ?);
        """, (name, preference, about_user)
    )
    conn.commit()
    user_id = cursor.lastrowid
    system_log("DATABASE", "INFO", f"Inserted new user profile with user_id={user_id}.")
    cursor.close()
    conn.close()
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
