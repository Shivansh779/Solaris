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
                is_private INTEGER NOT NULL DEFAULT 0,   --0 = Public, 1 = Private
                password TEXT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,    --0 = Inactive, 1 = Active
                activation_code TEXT NULL
            );
        """
    )
    conn.commit()
    cursor.close()
    conn.close()

def activation_code (grp_length=5):
    digits = string.digits
    pass_1 = ''.join(secrets.choice(digits) for _ in range(grp_length))
    pass_2 = ''.join(secrets.choice(digits) for _ in range(grp_length))
    code = pass_1 + '-' + pass_2
    return code

def deactivate_user (user_id):
    conn = get_conn()
    cursor = conn.cursor()
    code = activation_code()
    cursor.execute(
        """
            UPDATE user_data SET is_active = 0, activation_code = ? WHERE user_id = ?;
        """, (code, user_id)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return code


def activate_user (user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            UPDATE user_data SET is_active = 1, activation_code = NULL WHERE user_id = ?;
        """, (user_id,)
    )
    conn.commit()
    cursor.close()
    conn.close()

def fetch_activation_code (user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            SELECT activation_code FROM user_data WHERE user_id = ?;
        """, (user_id,)
    )
    data = cursor.fetchone()
    cursor.close()
    conn.close()
    return data[0] if data else 0

def generate_numeric_password(length=8):
    # string.digits provides the string '0123456789'
    digits = string.digits

    # Securely select random digits and join them together
    password = ''.join(secrets.choice(digits) for _ in range(length))
    return int(password)

password = generate_numeric_password()

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
            SELECT user_id, name, is_private, is_active FROM user_data ORDER BY user_id ASC;
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
            """, (name, preference, is_private, password)
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

def fetch_status (user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            SELECT is_active FROM user_data WHERE user_id = ?;
        """, (user_id,)
    )
    data = cursor.fetchone()
    cursor.close()
    conn.close()
    return data[0] if data else 1