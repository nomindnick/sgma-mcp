"""Tests for database schema creation."""

import sqlite3
import tempfile
from pathlib import Path

import pytest
import sqlite_vec

from scripts.create_schema import create_schema

EXPECTED_TABLES = [
    "sections",
    "cases",
    "definitions",
    "cross_references",
    "guidance_documents",
    "evaluations",
    "agency_documents",
    "auxiliary_content",
    "chunks",
]


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    create_schema(path)
    return path


@pytest.fixture
def conn(db_path):
    c = sqlite3.connect(db_path)
    c.enable_load_extension(True)
    sqlite_vec.load(c)
    c.enable_load_extension(False)
    yield c
    c.close()


class TestTablesExist:
    def test_all_tables_created(self, conn):
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        for table in EXPECTED_TABLES:
            assert table in tables, f"Missing table: {table}"

    def test_fts5_table_exists(self, conn):
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%fts%'"
            ).fetchall()
        }
        assert "chunks_fts" in tables

    def test_table_count(self, conn):
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'chunks_fts%'"
            ).fetchall()
        ]
        assert len(tables) == 9


class TestColumnVerification:
    def test_sections_columns(self, conn):
        cols = {row[1] for row in conn.execute("PRAGMA table_info(sections)").fetchall()}
        expected = {
            "id", "code", "section_number", "title", "full_text",
            "hierarchy_path", "content_type", "amendment_history", "effective_date",
        }
        assert expected == cols

    def test_cases_columns(self, conn):
        cols = {row[1] for row in conn.execute("PRAGMA table_info(cases)").fetchall()}
        expected = {
            "id", "case_name", "citation", "year", "court",
            "summary", "full_text", "status",
        }
        assert expected == cols

    def test_chunks_columns(self, conn):
        cols = {row[1] for row in conn.execute("PRAGMA table_info(chunks)").fetchall()}
        expected = {
            "id", "source_type", "source_id", "chunk_index",
            "chunk_text", "chunk_heading", "embedding",
        }
        assert expected == cols


class TestConstraints:
    def test_sections_unique_constraint(self, conn):
        conn.execute(
            "INSERT INTO sections (code, section_number, full_text, content_type) "
            "VALUES ('water_code', '10720', 'test text', 'statute')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sections (code, section_number, full_text, content_type) "
                "VALUES ('water_code', '10720', 'duplicate', 'statute')"
            )

    def test_different_codes_same_number_allowed(self, conn):
        conn.execute(
            "INSERT INTO sections (code, section_number, full_text, content_type) "
            "VALUES ('water_code', '100', 'wc text', 'statute')"
        )
        conn.execute(
            "INSERT INTO sections (code, section_number, full_text, content_type) "
            "VALUES ('gov_code', '100', 'gc text', 'statute')"
        )
        count = conn.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
        assert count == 2


class TestFTS5Sync:
    def test_insert_trigger(self, conn):
        conn.execute(
            "INSERT INTO chunks (source_type, source_id, chunk_index, chunk_text) "
            "VALUES ('section', 1, 0, 'groundwater sustainability plan')"
        )
        results = conn.execute(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'groundwater'"
        ).fetchall()
        assert len(results) == 1

    def test_delete_trigger(self, conn):
        conn.execute(
            "INSERT INTO chunks (id, source_type, source_id, chunk_index, chunk_text) "
            "VALUES (99, 'section', 1, 0, 'minimum threshold subsidence')"
        )
        conn.execute("DELETE FROM chunks WHERE id = 99")
        results = conn.execute(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'subsidence'"
        ).fetchall()
        assert len(results) == 0

    def test_update_trigger(self, conn):
        conn.execute(
            "INSERT INTO chunks (id, source_type, source_id, chunk_index, chunk_text) "
            "VALUES (88, 'section', 1, 0, 'original text about basins')"
        )
        conn.execute("UPDATE chunks SET chunk_text = 'updated text about aquifers' WHERE id = 88")
        old = conn.execute(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'basins'"
        ).fetchall()
        new = conn.execute(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'aquifers'"
        ).fetchall()
        assert len(old) == 0
        assert len(new) == 1


class TestSqliteVec:
    def test_vec_loads(self, conn):
        version = conn.execute("SELECT vec_version()").fetchone()[0]
        assert version is not None
        assert len(version) > 0
