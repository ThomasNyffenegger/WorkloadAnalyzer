import sqlite3
from pathlib import Path
from importlib.resources import files


def connect(db_path: Path) -> sqlite3.Connection:
    # isolation_level=None enables autocommit mode. All writes are immediate.
    # For atomic multi-table operations (e.g. entry + outlook reference), callers
    # must wrap in explicit BEGIN/COMMIT via conn.execute("BEGIN") / conn.execute("COMMIT").
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")   # concurrent reads during writes
    conn.execute("PRAGMA synchronous = NORMAL")  # safe with WAL, faster than FULL
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    schema_sql = files("workload_analyzer.db").joinpath("schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema_sql)
