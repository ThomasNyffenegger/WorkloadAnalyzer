import sqlite3
from pathlib import Path
from importlib.resources import files


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    schema_sql = files("workload_analyzer.db").joinpath("schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema_sql)
