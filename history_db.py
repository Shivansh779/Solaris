import sqlite3

DB_PATH = "database.db"

def get_conn ():
    return sqlite3.connect(DB_PATH)

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
    cursor.close()
    conn.close()
    return response
