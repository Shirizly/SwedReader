"""SQLite log of processed documents. Stored under data/private/ so private source URLs are never committed."""
import sqlite3
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL UNIQUE,
    source_domain TEXT NOT NULL,
    lane TEXT NOT NULL CHECK (lane IN ('public', 'private')),
    loaded_at TEXT NOT NULL,
    word_count INTEGER,
    output_path TEXT,
    content_hash TEXT,
    status TEXT NOT NULL CHECK (status IN ('ok', 'failed')),
    error TEXT,
    published INTEGER NOT NULL DEFAULT 0
)
"""


def connect(path):
    path = str(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def upsert_document(conn, *, id, source_url, source_domain, lane, word_count=None, output_path=None,
                    content_hash=None, status="ok", error=None, loaded_at=None):
    loaded_at = loaded_at or datetime.now().astimezone().isoformat(timespec="seconds")
    conn.execute(
        """INSERT INTO documents (id, source_url, source_domain, lane, loaded_at, word_count, output_path,
                                  content_hash, status, error)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(source_url) DO UPDATE SET
             id=excluded.id, source_domain=excluded.source_domain, lane=excluded.lane,
             loaded_at=excluded.loaded_at,
             word_count=COALESCE(excluded.word_count, word_count),
             output_path=COALESCE(excluded.output_path, output_path),
             content_hash=COALESCE(excluded.content_hash, content_hash),
             status=excluded.status, error=excluded.error""",
        (id, source_url, source_domain, lane, loaded_at, word_count, output_path, content_hash, status, error))
    conn.commit()


def mark_published(conn, doc_id):
    conn.execute("UPDATE documents SET published = 1 WHERE id = ?", (doc_id,))
    conn.commit()


def list_documents(conn):
    return conn.execute("SELECT * FROM documents ORDER BY loaded_at").fetchall()
