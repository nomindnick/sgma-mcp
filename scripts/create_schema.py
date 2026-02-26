"""Create the SGMA database schema with all tables, FTS5, indexes, and sqlite-vec."""

import sqlite3
import sys
from pathlib import Path

import sqlite_vec

DB_PATH = Path("data/sgma.db")

SCHEMA_SQL = """
-- Core tables

CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL,
    section_number TEXT NOT NULL,
    title TEXT,
    full_text TEXT NOT NULL,
    hierarchy_path TEXT,
    content_type TEXT NOT NULL,
    amendment_history TEXT,
    effective_date TEXT,
    UNIQUE(code, section_number)
);

CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY,
    case_name TEXT NOT NULL,
    citation TEXT,
    year INTEGER,
    court TEXT,
    summary TEXT,
    full_text TEXT,
    status TEXT DEFAULT 'good_law'
);

CREATE TABLE IF NOT EXISTS definitions (
    id INTEGER PRIMARY KEY,
    term TEXT NOT NULL,
    definition_text TEXT NOT NULL,
    source_section_id INTEGER NOT NULL REFERENCES sections(id)
);

CREATE TABLE IF NOT EXISTS cross_references (
    id INTEGER PRIMARY KEY,
    from_type TEXT NOT NULL,
    from_id INTEGER NOT NULL,
    to_type TEXT NOT NULL,
    to_id INTEGER NOT NULL,
    relationship TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guidance_documents (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    document_type TEXT NOT NULL,
    title TEXT NOT NULL,
    date TEXT,
    full_text TEXT,
    metadata JSON
);

CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY,
    basin_name TEXT NOT NULL,
    basin_number TEXT,
    gsa_name TEXT,
    plan_type TEXT,
    evaluation_date TEXT,
    determination TEXT,
    full_text TEXT
);

CREATE TABLE IF NOT EXISTS agency_documents (
    id INTEGER PRIMARY KEY,
    document_type TEXT NOT NULL,
    title TEXT NOT NULL,
    date TEXT,
    full_text TEXT,
    metadata JSON
);

CREATE TABLE IF NOT EXISTS auxiliary_content (
    id INTEGER PRIMARY KEY,
    content_type TEXT NOT NULL,
    title TEXT,
    text TEXT NOT NULL,
    metadata JSON
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    chunk_text TEXT NOT NULL,
    chunk_heading TEXT,
    embedding BLOB
);

-- FTS5 virtual table (content-external, synced via triggers)

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_text,
    content='chunks',
    content_rowid='id'
);

-- Triggers to keep FTS5 in sync with chunks table

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, chunk_text) VALUES (new.id, new.chunk_text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, chunk_text) VALUES ('delete', old.id, old.chunk_text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, chunk_text) VALUES ('delete', old.id, old.chunk_text);
    INSERT INTO chunks_fts(rowid, chunk_text) VALUES (new.id, new.chunk_text);
END;

-- Indexes

CREATE INDEX IF NOT EXISTS idx_sections_code_number ON sections(code, section_number);
CREATE INDEX IF NOT EXISTS idx_definitions_term ON definitions(term);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_cross_references_from ON cross_references(from_type, from_id);
CREATE INDEX IF NOT EXISTS idx_cross_references_to ON cross_references(to_type, to_id);
CREATE INDEX IF NOT EXISTS idx_cases_year ON cases(year);
CREATE INDEX IF NOT EXISTS idx_auxiliary_content_type ON auxiliary_content(content_type);
"""


def create_schema(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)

    # Set per-connection PRAGMAs (these don't persist across connections)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Load sqlite-vec before schema DDL so vec0 virtual tables can be created
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    conn.executescript(SCHEMA_SQL)

    vec_version = conn.execute("SELECT vec_version()").fetchone()[0]
    print(f"sqlite-vec version: {vec_version}")

    # Verify all tables exist
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]
    print(f"Tables created: {', '.join(tables)}")

    # Verify FTS5
    fts_tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%fts%'"
        ).fetchall()
    ]
    print(f"FTS5 tables: {', '.join(fts_tables)}")

    conn.close()
    print(f"\nDatabase created at {db_path} ({db_path.stat().st_size} bytes)")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH
    create_schema(path)
