import sqlite3
import json
from datetime import datetime

DB_PATH = "agent_memory.db"
DEFAULT_USER_ID = "VA_default"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Keep sessions for plan_summary tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      TEXT NOT NULL,
            session_id   TEXT NOT NULL,
            timestamp    TEXT NOT NULL,
            user_input   TEXT NOT NULL,
            final_output TEXT,
            plan_summary TEXT
        )
    """)
    
    # New messages table for conversation history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      TEXT NOT NULL,
            session_id   TEXT NOT NULL,
            role         TEXT NOT NULL,
            content      TEXT NOT NULL,
            timestamp    TEXT NOT NULL
        )
    """)
    
    conn.commit()
    conn.close()

def save_session(user_input: str, final_output: str, plan_summary: list, session_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sessions (user_id, session_id, timestamp, user_input, final_output, plan_summary)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        DEFAULT_USER_ID,
        session_id,
        datetime.now().isoformat(),
        user_input,
        final_output,
        json.dumps(plan_summary)
    ))
    conn.commit()
    conn.close()

def save_message(session_id: str, role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO messages (user_id, session_id, role, content, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (
        DEFAULT_USER_ID,
        session_id,
        role,
        content,
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()

def load_messages(limit: int = 20) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT role, content FROM messages
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (DEFAULT_USER_ID, limit))
    rows = cursor.fetchall()
    conn.close()
    # Reverse to get chronological order
    return [{"role": row[0], "content": row[1]} for row in reversed(rows)]

def load_recent_sessions(limit: int = 5) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_input, final_output, plan_summary, timestamp
        FROM sessions
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (DEFAULT_USER_ID, limit))
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "user_input": row[0],
            "final_output": row[1],
            "plan_summary": json.loads(row[2]) if row[2] else [],
            "timestamp": row[3]
        }
        for row in rows
    ]