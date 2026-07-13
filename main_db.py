import sqlite3
import secrets
import string
from datetime import datetime

def system_log(category, level, message):
    with open("System_Logs.txt", "a") as f:
        f.write(f"[{level}] [{category}] [{current_time()}]: {message}\n")

def current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
    system_log("DATABASE", "INFO", "User profile table created or already exists.")
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
    system_log("DATABASE", "INFO", f"Updated user profile as inactive for user_id={user_id}.")
    cursor.close()
    conn.close()
    return code

def rename_user (user_id, new_name):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE user_data SET name = ? WHERE user_id = ?;
    """, (new_name, user_id)
    )
    system_log("DATABASE", "INFO", f"Updated user profile as renamed for user_id={user_id}.")
    conn.commit()
    cursor.close()
    conn.close()

def activate_user (user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            UPDATE user_data SET is_active = 1, activation_code = NULL WHERE user_id = ?;
        """, (user_id,)
    )
    conn.commit()
    system_log("DATABASE", "INFO", f"Updated user profile as active for user_id={user_id}.")
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
    system_log("DATABASE", "INFO", f"Retrieved activation code status for user_id={user_id}.")
    cursor.close()
    conn.close()
    return data[0] if data else 0

def generate_numeric_password(length=8):
    # string.digits provides the string '0123456789'
    digits = string.digits

    # Securely select random digits and join them together
    password = ''.join(secrets.choice(digits) for _ in range(length))
    return str(password)

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
    system_log("DATABASE", "INFO", f"Retrieved privacy setting for user_id={user_id}.")
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
    system_log("DATABASE", "INFO", f"Retrieved password status for user_id={user_id}.")
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
    system_log("DATABASE", "INFO", "Retrieved existing user profiles.")
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
    system_log("DATABASE", "INFO", f"Retrieved preferences for user_id={user_id}.")
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

def update_privacy (user_id, privacy):
    conn = get_conn()
    cursor = conn.cursor()
    if privacy == 0:
        cursor.execute("""
            UPDATE user_data SET is_private = ? WHERE user_id = ?;
        """, (privacy, user_id)
        )
    else:
        cursor.execute("""
            UPDATE user_data SET is_private = ?, password = ? WHERE user_id = ?;
        """, (privacy, password, user_id)
        )
    conn.commit()
    system_log("DATABASE", "INFO", f"Updated privacy settings for user_id={user_id}.")
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

def fetch_status (user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            SELECT is_active FROM user_data WHERE user_id = ?;
        """, (user_id,)
    )
    data = cursor.fetchone()
    system_log("DATABASE", "INFO", f"Retrieved active status for user_id={user_id}.")
    cursor.close()
    conn.close()
    return data[0] if data else 1
