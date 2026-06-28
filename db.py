import sqlite3
import json
from datetime import datetime
import chromadb
from chromadb.utils import embedding_functions

DB_PATH = "agent_memory.db"
DEFAULT_USER_ID = "VA_default"

# ── ChromaDB setup ──────────────────────────────────────────────────────────
_chroma_client = chromadb.PersistentClient(path="./chroma_store")
_embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)
_msg_collection = _chroma_client.get_or_create_collection(
    name="message_history",
    embedding_function=_embed_fn
)

# ── SQLite setup ──────────────────────────────────────────────────────────────
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

    # ✅ Updated preferences schema — scope, confidence, source, reinforcement tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS preferences (
            user_id                 TEXT NOT NULL,
            category                TEXT NOT NULL,
            rule                    TEXT NOT NULL,
            scope                   TEXT NOT NULL DEFAULT 'global',
            confidence              REAL NOT NULL DEFAULT 0.7,
            source                  TEXT NOT NULL DEFAULT 'explicit',
            reinforcement_count     INTEGER NOT NULL DEFAULT 1,
            interactions_since_seen INTEGER NOT NULL DEFAULT 0,
            status                  TEXT NOT NULL DEFAULT 'active',
            created_at              TEXT NOT NULL,
            updated_at              TEXT NOT NULL,
            PRIMARY KEY (user_id, category, scope)
        )
    """)

    conn.commit()
    conn.close()


# ── Sessions ──────────────────────────────────────────────────────────────────
def save_session(user_input: str, final_output: str, plan_summary: list, session_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sessions (user_id, session_id, timestamp, user_input, final_output, plan_summary)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        DEFAULT_USER_ID, session_id, datetime.now().isoformat(),
        user_input, final_output, json.dumps(plan_summary)
    ))
    conn.commit()
    conn.close()


# ── Messages → ChromaDB ───────────────────────────────────────────────────────
def save_message(session_id: str, role: str, content: str):
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
    total = _msg_collection.count()
    if total == 0:
        return []

    if query:
        results = _msg_collection.query(
            query_texts=[query],
            n_results=min(limit, total),
            where={"user_id": DEFAULT_USER_ID}
        )
        docs      = results["documents"][0]
        metadatas = results["metadatas"][0]
        paired = sorted(zip(metadatas, docs), key=lambda x: x[0]["timestamp"])
        return [{"role": m["role"], "content": d} for m, d in paired]
    else:
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
        return [{"role": m["role"], "content": d} for m, d in paired[-limit:]]


def get_recent_messages(limit: int = 10) -> list:
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
    return [{"role": m["role"], "content": d} for m, d in paired[-limit:]]


def search_messages(query: str, limit: int = 10) -> list:
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


# ── Preferences → SQLite ──────────────────────────────────────────────────────

# Confidence deltas by signal source
_REINFORCEMENT_DELTA = {
    "explicit":   0.20,
    "correction": 0.15,
    "implicit":   0.08,
}

# Floors — explicit preferences never decay below these values
_DECAY_FLOORS = {
    "explicit":   0.70,
    "correction": 0.60,
    "implicit":   0.30,
}

DECAY_RATE = 0.02       # per interaction without reinforcement
CONFIDENCE_THRESHOLD = 0.50   # below this, preference is not injected


def upsert_preference(category: str, rule: str, scope: str = "global",
                      source: str = "explicit", contradiction: bool = False,
                      contradiction_strength: str = None):
    """
    Insert or update a preference with confidence scoring and reinforcement tracking.
    contradiction=True with contradiction_strength in ("weak","partial","absolute")
    triggers decay/delete instead of reinforcement.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    cursor.execute("""
        SELECT rule, confidence, source, reinforcement_count, status
        FROM preferences
        WHERE user_id=? AND category=? AND scope=?
    """, (DEFAULT_USER_ID, category, scope))
    existing = cursor.fetchone()

    if contradiction and existing:
        old_conf = existing[1]
        old_source = existing[2]
        if contradiction_strength == "absolute":
            cursor.execute("""
                UPDATE preferences SET status='deleted', updated_at=?
                WHERE user_id=? AND category=? AND scope=?
            """, (now, DEFAULT_USER_ID, category, scope))
            print(f"[PREF DB] Deleted (absolute contradiction): {category}/{scope}")
        elif contradiction_strength == "partial":
            # Update rule to new nuanced version, drop confidence
            new_conf = max(_DECAY_FLOORS.get(old_source, 0.3), old_conf - 0.30)
            cursor.execute("""
                UPDATE preferences
                SET rule=?, confidence=?, status='active', updated_at=?
                WHERE user_id=? AND category=? AND scope=?
            """, (rule, new_conf, now, DEFAULT_USER_ID, category, scope))
            print(f"[PREF DB] Partial contradiction — updated rule, confidence: {new_conf:.2f}")
        else:  # weak
            new_conf = old_conf - 0.30
            if new_conf < 0.30:
                cursor.execute("""
                    UPDATE preferences SET status='conflicted', confidence=?, updated_at=?
                    WHERE user_id=? AND category=? AND scope=?
                """, (new_conf, now, DEFAULT_USER_ID, category, scope))
                print(f"[PREF DB] Weak contradiction — marked conflicted: {category}/{scope}")
            else:
                cursor.execute("""
                    UPDATE preferences SET confidence=?, updated_at=?
                    WHERE user_id=? AND category=? AND scope=?
                """, (new_conf, now, DEFAULT_USER_ID, category, scope))
                print(f"[PREF DB] Weak contradiction — decayed to: {new_conf:.2f}")
        conn.commit()
        conn.close()
        return

    if not existing:
        # Base confidence by source
        base = {"explicit": 0.90, "correction": 0.85, "implicit": 0.55}.get(source, 0.70)
        cursor.execute("""
            INSERT INTO preferences
            (user_id, category, rule, scope, confidence, source,
             reinforcement_count, interactions_since_seen, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, 0, 'active', ?, ?)
        """, (DEFAULT_USER_ID, category, rule, scope, base, source, now, now))
        print(f"[PREF DB] New preference: {category}/{scope} conf={base:.2f} src={source}")
    else:
        old_rule, old_conf, old_source, old_count, _ = existing
        delta = _REINFORCEMENT_DELTA.get(source, 0.08)
        new_conf = min(1.0, old_conf + delta)
        # Rule text changed → slight uncertainty penalty
        if rule != old_rule:
            new_conf = max(0.50, new_conf - 0.10)
        new_count = old_count + 1
        cursor.execute("""
            UPDATE preferences
            SET rule=?, confidence=?, reinforcement_count=?,
                interactions_since_seen=0, status='active', updated_at=?
            WHERE user_id=? AND category=? AND scope=?
        """, (rule, new_conf, new_count, now, DEFAULT_USER_ID, category, scope))
        print(f"[PREF DB] Reinforced: {category}/{scope} conf={new_conf:.2f} count={new_count}")

    conn.commit()
    conn.close()


def increment_interactions_since_seen():
    """
    Call once per run_agent() to age all preferences that were NOT reinforced this run.
    Decay is applied lazily in load_preferences().
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE preferences
        SET interactions_since_seen = interactions_since_seen + 1
        WHERE user_id=? AND status='active'
    """, (DEFAULT_USER_ID,))
    conn.commit()
    conn.close()


def load_preferences(agent_scope: str = None, confidence_threshold: float = CONFIDENCE_THRESHOLD) -> dict:
    """
    Load active preferences, applying decay and filtering by scope + confidence.
    Returns: {category: {rule, scope, confidence, source, reinforcement_count}}
    agent_scope: if provided, returns only 'global' and matching scope preferences.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT category, rule, scope, confidence, source,
               reinforcement_count, interactions_since_seen
        FROM preferences
        WHERE user_id=? AND status='active'
    """, (DEFAULT_USER_ID,))
    rows = cursor.fetchall()
    conn.close()

    result = {}
    for category, rule, scope, confidence, source, count, since_seen in rows:
        # Filter by scope
        if agent_scope and scope not in ("global", agent_scope):
            continue

        # Apply decay lazily
        floor = _DECAY_FLOORS.get(source, 0.30)
        decayed_conf = max(floor, confidence - (DECAY_RATE * since_seen))

        if decayed_conf < confidence_threshold:
            continue

        result[category] = {
            "rule":                rule,
            "scope":               scope,
            "confidence":          decayed_conf,
            "source":              source,
            "reinforcement_count": count
        }

    return result


def delete_preference(category: str, scope: str = "global"):
    """Hard delete a preference (for explicit user removal requests)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM preferences WHERE user_id=? AND category=? AND scope=?
    """, (DEFAULT_USER_ID, category, scope))
    conn.commit()
    conn.close()


# Legacy shim — keeps old callers working during transition
def save_preference(category: str, rule: str):
    upsert_preference(category, rule, scope="global", source="explicit")