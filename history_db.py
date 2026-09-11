import sqlite3
from datetime import datetime

from _log import system_log, current_time

DB_PATH = "database.db"

def get_conn ():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def create_table():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            Session_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            summary TEXT,
            created_on TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES user_data (user_id)
        );
    """)
    conn.commit()
    system_log("DATABASE", "INFO", "History table created or already exists.")
    cursor.close()
    conn.close()
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS web_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            query TEXT,
            provider TEXT,
            depth INTEGER,
            urls TEXT,
            created_on TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES user_data (user_id)
        );
    """)
    conn.commit()
    system_log("DATABASE", "INFO", "Web log table created or already exists.")
    cursor.close()
    conn.close()

def store_web_log (user_id, query, provider, depth, urls):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO web_log (user_id, query, provider, depth, urls, created_on) VALUES (?, ?, ?, ?, ?, ?);
    """, (user_id, query, provider, depth, urls, current_time())
    )
    conn.commit()
    system_log("DATABASE", "INFO", f"Inserted web log entry for user_id={user_id}, provider={provider}.")
    cursor.close()
    conn.close()

def store_history (time, user_id, summary):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO history (user_id, summary, created_on) VALUES (?, ?, ?);
    """, (user_id, summary, time)
    )
    conn.commit()
    system_log("DATABASE", "INFO", f"Inserted history summary for user_id={user_id}.")
    cursor.close()
    conn.close()

def access_history (user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
            SELECT summary, created_on
            FROM history 
            WHERE user_id = ? 
            ORDER BY Session_id DESC 
            LIMIT 20;
        """, (user_id,)
    )
    response = cursor.fetchall()
    system_log("DATABASE", "INFO", f"Retrieved history summaries for user_id={user_id}.")
    cursor.close()
    conn.close()
    return response
