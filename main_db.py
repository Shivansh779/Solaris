import sqlite3
import secrets
import string

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
                is_private INTEGER NOT NULL DEFAULT 0,   --0 Public, 1 = Private
                password TEXT NULL
            );
        """
    )
    conn.commit()
    cursor.close()
    conn.close()

def generate_numeric_password(length=8):
    # string.digits provides the string '0123456789'
    digits = string.digits

    # Securely select random digits and join them together
    password = ''.join(secrets.choice(digits) for _ in range(length))
    return int(password)

def fetch_privacy_setting (user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            SELECT is_private FROM user_data WHERE user_id =?;
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
            SELECT password FROM user_data WHERE user_id = ?;
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
            SELECT user_id, name FROM user_data ORDER BY user_id ASC;
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
            SELECT prefers, name FROM user_data WHERE user_id = ?;
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
    if is_private == 1:
        cursor.execute(
            """
                INSERT INTO user_data (name, prefers, is_private, password) VALUES(?, ?, ?, ?);
            """, (name, preference, is_private, generate_numeric_password())
        )
    else:
        cursor.execute(
            """
                INSERT INTO user_data (name, prefers) VALUES (?, ?);
            """, (name, preference)
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
            UPDATE user_data SET prefers = ? WHERE user_id = ?;
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
            SELECT user_id FROM user_data WHERE name = ?;
        """, (name,)
    )
    data = cursor.fetchone()
    cursor.close()
    conn.close()
    return data