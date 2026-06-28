import sqlite3
import json
from datetime import datetime
import chromadb
from chromadb.utils import embedding_functions

DB_PATH = "agent_memory.db"
DEFAULT_USER_ID = "VA_default"

# ── ChromaDB setup ──────────────────────────────────────────────────────────
# Persists to disk in ./chroma_store — no server needed
_chroma_client = chromadb.PersistentClient(path="./chroma_store")

_embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"   # free, local, fast (~80MB download once)
)

# One collection per data type
_msg_collection = _chroma_client.get_or_create_collection(
    name="message_history",
    embedding_function=_embed_fn
)

# ── SQLite setup (kept for sessions + preferences) ──────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

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

    # Preferences: one row per category per user, upsert on conflict
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS preferences (
            user_id   TEXT NOT NULL,
            category  TEXT NOT NULL,
            rule      TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, category)
        )
    """)

    conn.commit()
    conn.close()


# ── Sessions ─────────────────────────────────────────────────────────────────
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


# ── Messages → ChromaDB ──────────────────────────────────────────────────────
def save_message(session_id: str, role: str, content: str):
    """Embed and store a message in ChromaDB."""
    doc_id = f"{DEFAULT_USER_ID}_{session_id}_{role}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    _msg_collection.add(
        documents=[content],
        metadatas=[{
            "user_id":    DEFAULT_USER_ID,
            "session_id": session_id,
            "role":       role,
            "timestamp":  datetime.now().isoformat()
        }],
        ids=[doc_id]
    )


def load_messages(query: str = None, limit: int = 20) -> list:
    """
    If query is provided: return top-k semantically relevant messages.
    If query is None:     return the most recent `limit` messages (fallback).
    """
    total = _msg_collection.count()
    if total == 0:
        return []

    if query:
        # Semantic retrieval — return messages most relevant to current query
        results = _msg_collection.query(
            query_texts=[query],
            n_results=min(limit, total),
            where={"user_id": DEFAULT_USER_ID}
        )
        docs      = results["documents"][0]
        metadatas = results["metadatas"][0]
        # Sort by timestamp so LLM sees chronological order
        paired = sorted(zip(metadatas, docs), key=lambda x: x[0]["timestamp"])
        return [{"role": m["role"], "content": d} for m, d in paired]

    else:
        # Recency fallback — fetch all and take last N
        results = _msg_collection.get(
            where={"user_id": DEFAULT_USER_ID},
            include=["documents", "metadatas"]
        )
        if not results["documents"]:
            return []
        paired = sorted(
            zip(results["metadatas"], results["documents"]),
            key=lambda x: x[0]["timestamp"]
        )
        recent = paired[-limit:]
        return [{"role": m["role"], "content": d} for m, d in recent]


# ── Preferences → SQLite ─────────────────────────────────────────────────────
def save_preference(category: str, rule: str):
    """Upsert a preference — same category always overwrites."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO preferences (user_id, category, rule, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, category) DO UPDATE SET
            rule       = excluded.rule,
            updated_at = excluded.updated_at
    """, (DEFAULT_USER_ID, category, rule, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def load_preferences() -> dict:
    """Return all preferences as a flat dict {category: rule}."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT category, rule FROM preferences
        WHERE user_id = ?
    """, (DEFAULT_USER_ID,))
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}


def delete_preference(category: str):
    """Remove a specific preference category."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM preferences WHERE user_id = ? AND category = ?
    """, (DEFAULT_USER_ID, category))
    conn.commit()
    conn.close()

def get_recent_messages(limit: int = 10) -> list:
    """Always returns the most recent N messages in chronological order."""
    total = _msg_collection.count()
    if total == 0:
        return []

    results = _msg_collection.get(
        where={"user_id": DEFAULT_USER_ID},
        include=["documents", "metadatas"]
    )
    if not results["documents"]:
        return []

    paired = sorted(
        zip(results["metadatas"], results["documents"]),
        key=lambda x: x[0]["timestamp"]
    )
    recent = paired[-limit:]
    return [{"role": m["role"], "content": d} for m, d in recent]


def search_messages(query: str, limit: int = 10) -> list:
    """Semantic search — returns messages most relevant to the query."""
    total = _msg_collection.count()
    if total == 0:
        return []

    results = _msg_collection.query(
        query_texts=[query],
        n_results=min(limit, total),
        where={"user_id": DEFAULT_USER_ID}
    )
    docs      = results["documents"][0]
    metadatas = results["metadatas"][0]
    paired = sorted(zip(metadatas, docs), key=lambda x: x[0]["timestamp"])
    return [{"role": m["role"], "content": d} for m, d in paired]