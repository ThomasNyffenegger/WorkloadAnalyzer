import pytest
import sqlite3
from pathlib import Path


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"
