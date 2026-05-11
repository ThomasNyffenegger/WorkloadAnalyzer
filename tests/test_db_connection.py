import sqlite3
from pathlib import Path

from workload_analyzer.db.connection import connect


def test_connect_creates_schema(tmp_db_path: Path):
    conn = connect(tmp_db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    assert "roles" in tables
    assert "categories" in tables
    assert "time_entries" in tables
    assert "outlook_references" in tables
    assert "rejected_suggestions" in tables
    assert "settings" in tables
    conn.close()


def test_connect_enables_foreign_keys(tmp_db_path: Path):
    conn = connect(tmp_db_path)
    cursor = conn.execute("PRAGMA foreign_keys")
    assert cursor.fetchone()[0] == 1
    conn.close()


def test_connect_returns_row_factory(tmp_db_path: Path):
    conn = connect(tmp_db_path)
    assert conn.row_factory is sqlite3.Row
    conn.close()
