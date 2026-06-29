"""SQLite connection and schema for bac-scope."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

# Default to data/bac.db inside the project; override with BACSCOPE_DB env var.
DB_PATH = Path(
    os.environ.get(
        "BACSCOPE_DB",
        Path(__file__).resolve().parent.parent / "data" / "bac.db",
    )
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    registration_number INTEGER PRIMARY KEY,
    id_number            TEXT,
    name                 TEXT NOT NULL,
    institution          TEXT,
    stream               TEXT NOT NULL,
    result_raw           TEXT,
    passed               INTEGER NOT NULL DEFAULT 0,  -- 1 only if ناجح
    status               TEXT,   -- ناجح / مؤجل / مرفوض
    mention              TEXT,   -- honor grade (حسن جدا…) for passed only, else NULL
    total                REAL,   -- معدل الباكالوريا (final bac average)
    moyenne              REAL    -- المعدل السنوي (annual average)
);

CREATE TABLE IF NOT EXISTS grades (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    registration_number  INTEGER NOT NULL,
    subject              TEXT NOT NULL,
    score                REAL,
    FOREIGN KEY (registration_number) REFERENCES students(registration_number)
);

CREATE TABLE IF NOT EXISTS datasets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    stream       TEXT NOT NULL,
    filename     TEXT,
    row_count    INTEGER,
    uploaded_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_students_status      ON students(status);
CREATE INDEX IF NOT EXISTS idx_students_stream      ON students(stream);
CREATE INDEX IF NOT EXISTS idx_students_institution ON students(institution);
CREATE INDEX IF NOT EXISTS idx_grades_reg           ON grades(registration_number);
CREATE INDEX IF NOT EXISTS idx_grades_subject       ON grades(subject);
"""


def get_connection(read_only: bool = False) -> sqlite3.Connection:
    """Return a SQLite connection. read_only is used by the /ask endpoint."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if read_only and DB_PATH.exists():
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    """Create tables and indexes if they do not exist."""
    own = conn is None
    conn = conn or get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    if own:
        conn.close()


def reset_db() -> None:
    """Drop all data (used by seed for a clean reload)."""
    conn = get_connection()
    conn.executescript(
        "DROP TABLE IF EXISTS grades;"
        "DROP TABLE IF EXISTS students;"
        "DROP TABLE IF EXISTS datasets;"
    )
    conn.commit()
    init_db(conn)
    conn.close()
