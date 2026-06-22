"""
Database layer. Plain sqlite3 (no ORM) — the schema is small and this keeps
things transparent and fast. WAL mode is enabled so large chunked uploads
(lots of small writes) don't block reads from the UI.
"""
import sqlite3
from contextlib import contextmanager
from app.config import settings

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Folders form a simple tree. parent_id = NULL means root.
CREATE TABLE IF NOT EXISTS folders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    parent_id   INTEGER REFERENCES folders(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(parent_id, name)
);

-- Completed, browsable files.
CREATE TABLE IF NOT EXISTS files (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    folder_id    INTEGER REFERENCES folders(id) ON DELETE CASCADE,
    size_bytes   INTEGER NOT NULL,
    mime_type    TEXT,
    storage_name TEXT NOT NULL UNIQUE,   -- actual filename on disk (uuid-based)
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(folder_id, name)
);

-- One row per in-progress / resumable chunked upload.
CREATE TABLE IF NOT EXISTS upload_sessions (
    id              TEXT PRIMARY KEY,          -- uuid, given to the client
    file_name       TEXT NOT NULL,
    folder_id       INTEGER REFERENCES folders(id) ON DELETE CASCADE,
    total_size      INTEGER NOT NULL,
    chunk_size      INTEGER NOT NULL,
    total_chunks    INTEGER NOT NULL,
    mime_type       TEXT,
    temp_path       TEXT NOT NULL,             -- folder holding chunk parts
    status          TEXT NOT NULL DEFAULT 'uploading',  -- uploading|completed|aborted
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Which chunk indices have already landed on disk for a session.
-- This is the thing that makes "resume after interruption" possible:
-- the client asks "which chunks do you already have?" and only sends the rest.
CREATE TABLE IF NOT EXISTS upload_chunks (
    session_id   TEXT NOT NULL REFERENCES upload_sessions(id) ON DELETE CASCADE,
    chunk_index  INTEGER NOT NULL,
    size_bytes   INTEGER NOT NULL,
    PRIMARY KEY (session_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_files_folder ON files(folder_id);
CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON upload_sessions(status);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_cursor():
    """Context manager: commit on success, rollback on error, always close."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
