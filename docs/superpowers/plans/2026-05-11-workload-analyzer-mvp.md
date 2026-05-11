# WorkloadAnalyzer MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Windows time-tracking app with manual category switching, SQLite persistence, system tray + floating widget UI, role/category management, and reports with Excel/CSV export. This is the foundation for the full spec; Outlook integration and system monitors come in later plans.

**Architecture:** Python + PyQt6 desktop app. Single process, three layers: persistence (SQLite via a thin repository), core state machine (TimeTracker tracks the currently-active category and writes entries on switch), and UI (Qt tray + windows). Time entries are stored sekunden-genau in UTC; rounding is presentation-only.

**Tech Stack:** Python 3.11+, PyQt6, SQLite (stdlib), openpyxl (Excel export), pytest, pytest-qt. Linting: ruff. Formatting: black.

**Reference spec:** `docs/superpowers/specs/2026-05-11-workload-analyzer-design.md`

---

## File Structure

```
WorkloadAnalyzer/
├── pyproject.toml
├── .gitignore
├── README.md
├── src/workload_analyzer/
│   ├── __init__.py
│   ├── __main__.py              # CLI entry: python -m workload_analyzer
│   ├── app.py                   # Application bootstrap (wires DB, tracker, UI)
│   ├── paths.py                 # %APPDATA% resolution
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py        # DB connection + schema init
│   │   ├── schema.sql           # DDL
│   │   └── repository.py        # All CRUD operations
│   ├── models.py                # Dataclasses: Role, Category, TimeEntry, Settings
│   ├── core/
│   │   ├── __init__.py
│   │   ├── tracker.py           # TimeTracker state machine
│   │   └── rounding.py          # Presentation-only rounding helpers
│   ├── services/
│   │   ├── __init__.py
│   │   └── export.py            # Excel + CSV export
│   └── ui/
│       ├── __init__.py
│       ├── tray.py              # QSystemTrayIcon + menu
│       ├── floating_widget.py   # Always-on-top compact widget
│       ├── settings_window.py   # Role/Category management + general settings
│       └── reports_window.py    # Charts + detail table + export
└── tests/
    ├── __init__.py
    ├── conftest.py              # pytest fixtures (temp DB)
    ├── test_repository.py
    ├── test_tracker.py
    ├── test_rounding.py
    └── test_export.py
```

**Decomposition rationale:**
- `repository.py` is one file because the table count is small and queries are short — splitting per-table would scatter trivially-related code.
- `tracker.py` is isolated from UI so it can be tested headlessly.
- UI files split by window/widget — each is independently understandable and small.
- `models.py` is shared between repository, tracker, and UI to avoid duplication.

---

## Task 1: Project Bootstrap

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/workload_analyzer/__init__.py`
- Create: `src/workload_analyzer/__main__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "workload-analyzer"
version = "0.1.0"
description = "Windows time tracker with role/category-based reporting"
requires-python = ">=3.11"
dependencies = [
    "PyQt6>=6.6",
    "openpyxl>=3.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-qt>=4.4",
    "ruff>=0.5",
    "black>=24.0",
]

[project.scripts]
workload-analyzer = "workload_analyzer.__main__:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.pytest_cache/
*.db
*.db-journal
dist/
build/
.ruff_cache/
```

- [ ] **Step 3: Create empty package markers**

`src/workload_analyzer/__init__.py`:
```python
__version__ = "0.1.0"
```

`tests/__init__.py`: empty file.

- [ ] **Step 4: Create temporary `__main__.py` stub**

`src/workload_analyzer/__main__.py`:
```python
def main() -> int:
    print("WorkloadAnalyzer not yet implemented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Create `tests/conftest.py` skeleton**

```python
import pytest
import sqlite3
from pathlib import Path


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"
```

- [ ] **Step 6: Install and verify**

Run:
```bash
python -m pip install -e ".[dev]"
python -m workload_analyzer
pytest -q
```

Expected: stub message prints; pytest collects zero tests and exits 0.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore src tests
git commit -m "chore: bootstrap WorkloadAnalyzer project"
```

---

## Task 2: Path Resolution

**Files:**
- Create: `src/workload_analyzer/paths.py`
- Create: `tests/test_paths.py`

- [ ] **Step 1: Write failing test**

`tests/test_paths.py`:
```python
import os
from pathlib import Path

from workload_analyzer.paths import data_dir, db_path


def test_data_dir_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    result = data_dir()
    assert result == tmp_path / "WorkloadAnalyzer"
    assert result.exists()


def test_db_path_inside_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert db_path() == tmp_path / "WorkloadAnalyzer" / "workload.db"
```

- [ ] **Step 2: Run test, expect failure**

Run: `pytest tests/test_paths.py -v`
Expected: ImportError (`paths` not found).

- [ ] **Step 3: Implement**

`src/workload_analyzer/paths.py`:
```python
import os
from pathlib import Path

APP_DIR_NAME = "WorkloadAnalyzer"
DB_FILE_NAME = "workload.db"


def data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if not base:
        base = str(Path.home())
    d = Path(base) / APP_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return data_dir() / DB_FILE_NAME
```

- [ ] **Step 4: Run test, expect pass**

Run: `pytest tests/test_paths.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/workload_analyzer/paths.py tests/test_paths.py
git commit -m "feat(paths): resolve APPDATA-based data and DB paths"
```

---

## Task 3: Database Schema

**Files:**
- Create: `src/workload_analyzer/db/__init__.py`
- Create: `src/workload_analyzer/db/schema.sql`
- Create: `src/workload_analyzer/db/connection.py`
- Create: `tests/test_db_connection.py`

The schema includes all spec tables now so later plans don't need migrations.

- [ ] **Step 1: Create `db/__init__.py`** (empty file)

- [ ] **Step 2: Create `db/schema.sql`**

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#888888',
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    active INTEGER NOT NULL DEFAULT 1,
    outlook_category_name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_categories_role ON categories(role_id);
CREATE INDEX IF NOT EXISTS idx_categories_outlook ON categories(outlook_category_name);

CREATE TABLE IF NOT EXISTS time_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    start_ts INTEGER NOT NULL,  -- unix seconds, UTC
    end_ts INTEGER,             -- NULL while active
    source TEXT NOT NULL,       -- enum: manual, auto_outlook, auto_meeting, manual_override, screen_lock_recovery, idle_recovery
    comment TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    modified_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_entries_start ON time_entries(start_ts);
CREATE INDEX IF NOT EXISTS idx_entries_end ON time_entries(end_ts);
CREATE INDEX IF NOT EXISTS idx_entries_category ON time_entries(category_id);

CREATE TABLE IF NOT EXISTS outlook_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time_entry_id INTEGER NOT NULL REFERENCES time_entries(id) ON DELETE CASCADE,
    outlook_item_id TEXT NOT NULL,
    subject TEXT,
    item_type TEXT NOT NULL  -- mail, task, appointment
);

CREATE TABLE IF NOT EXISTS rejected_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    outlook_category_name TEXT NOT NULL,
    app_category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    rejection_count INTEGER NOT NULL DEFAULT 0,
    silenced INTEGER NOT NULL DEFAULT 0,
    last_rejected_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(outlook_category_name, app_category_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

- [ ] **Step 3: Write failing test for `connect()`**

`tests/test_db_connection.py`:
```python
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
```

- [ ] **Step 4: Run test, expect failure**

Run: `pytest tests/test_db_connection.py -v`
Expected: ImportError.

- [ ] **Step 5: Implement `connection.py`**

```python
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
```

Make sure `pyproject.toml` includes the SQL file:

Append to `pyproject.toml`:
```toml
[tool.setuptools.package-data]
"workload_analyzer.db" = ["*.sql"]
```

- [ ] **Step 6: Run test, expect pass**

Run: `pytest tests/test_db_connection.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add src/workload_analyzer/db tests/test_db_connection.py pyproject.toml
git commit -m "feat(db): initialize SQLite schema with all spec tables"
```

---

## Task 4: Models

**Files:**
- Create: `src/workload_analyzer/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing test**

`tests/test_models.py`:
```python
from workload_analyzer.models import Role, Category, TimeEntry, EntrySource


def test_entry_source_values():
    assert EntrySource.MANUAL.value == "manual"
    assert EntrySource.AUTO_OUTLOOK.value == "auto_outlook"
    assert EntrySource.AUTO_MEETING.value == "auto_meeting"
    assert EntrySource.MANUAL_OVERRIDE.value == "manual_override"
    assert EntrySource.SCREEN_LOCK_RECOVERY.value == "screen_lock_recovery"
    assert EntrySource.IDLE_RECOVERY.value == "idle_recovery"


def test_role_dataclass():
    r = Role(id=1, name="Entwicklung")
    assert r.id == 1
    assert r.name == "Entwicklung"


def test_category_dataclass():
    c = Category(id=2, name="Frontend", color="#ff0000", role_id=1, active=True)
    assert c.color == "#ff0000"
    assert c.active is True
    assert c.outlook_category_name is None


def test_time_entry_active_when_end_ts_none():
    e = TimeEntry(
        id=10, category_id=2, start_ts=1000, end_ts=None,
        source=EntrySource.MANUAL, comment=None,
    )
    assert e.is_active() is True


def test_time_entry_duration_seconds():
    e = TimeEntry(
        id=10, category_id=2, start_ts=1000, end_ts=1300,
        source=EntrySource.MANUAL, comment=None,
    )
    assert e.duration_seconds() == 300
```

- [ ] **Step 2: Run test, expect failure**

Run: `pytest tests/test_models.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `models.py`**

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EntrySource(str, Enum):
    MANUAL = "manual"
    AUTO_OUTLOOK = "auto_outlook"
    AUTO_MEETING = "auto_meeting"
    MANUAL_OVERRIDE = "manual_override"
    SCREEN_LOCK_RECOVERY = "screen_lock_recovery"
    IDLE_RECOVERY = "idle_recovery"


@dataclass
class Role:
    id: Optional[int]
    name: str


@dataclass
class Category:
    id: Optional[int]
    name: str
    color: str
    role_id: int
    active: bool = True
    outlook_category_name: Optional[str] = None


@dataclass
class TimeEntry:
    id: Optional[int]
    category_id: int
    start_ts: int
    end_ts: Optional[int]
    source: EntrySource
    comment: Optional[str] = None

    def is_active(self) -> bool:
        return self.end_ts is None

    def duration_seconds(self) -> int:
        if self.end_ts is None:
            return 0
        return self.end_ts - self.start_ts
```

- [ ] **Step 4: Run test, expect pass**

Run: `pytest tests/test_models.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/workload_analyzer/models.py tests/test_models.py
git commit -m "feat(models): add Role, Category, TimeEntry dataclasses"
```

---

## Task 5: Repository — Roles

**Files:**
- Create: `src/workload_analyzer/db/repository.py`
- Create: `tests/test_repository_roles.py`

The repository takes an open `sqlite3.Connection` (dependency injection — easy to test).

- [ ] **Step 1: Write failing tests**

`tests/test_repository_roles.py`:
```python
import pytest

from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import Role


@pytest.fixture
def repo(tmp_db_path):
    conn = connect(tmp_db_path)
    yield Repository(conn)
    conn.close()


def test_create_role_returns_id(repo: Repository):
    role_id = repo.create_role("Entwicklung")
    assert isinstance(role_id, int)
    assert role_id > 0


def test_list_roles_returns_all(repo: Repository):
    repo.create_role("Entwicklung")
    repo.create_role("Projektleitung")
    roles = repo.list_roles()
    assert len(roles) == 2
    names = [r.name for r in roles]
    assert "Entwicklung" in names
    assert "Projektleitung" in names


def test_create_role_duplicate_name_raises(repo: Repository):
    repo.create_role("Entwicklung")
    with pytest.raises(Exception):
        repo.create_role("Entwicklung")


def test_rename_role(repo: Repository):
    rid = repo.create_role("Dev")
    repo.rename_role(rid, "Entwicklung")
    assert repo.get_role(rid).name == "Entwicklung"


def test_delete_role(repo: Repository):
    rid = repo.create_role("Tmp")
    repo.delete_role(rid)
    assert repo.get_role(rid) is None
```

- [ ] **Step 2: Run test, expect failure**

Run: `pytest tests/test_repository_roles.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement Repository roles**

`src/workload_analyzer/db/repository.py`:
```python
import sqlite3
from typing import Optional

from workload_analyzer.models import Role


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # --- Roles ---

    def create_role(self, name: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO roles (name) VALUES (?)", (name,)
        )
        return cur.lastrowid

    def list_roles(self) -> list[Role]:
        rows = self.conn.execute(
            "SELECT id, name FROM roles ORDER BY name"
        ).fetchall()
        return [Role(id=r["id"], name=r["name"]) for r in rows]

    def get_role(self, role_id: int) -> Optional[Role]:
        row = self.conn.execute(
            "SELECT id, name FROM roles WHERE id = ?", (role_id,)
        ).fetchone()
        if row is None:
            return None
        return Role(id=row["id"], name=row["name"])

    def rename_role(self, role_id: int, new_name: str) -> None:
        self.conn.execute(
            "UPDATE roles SET name = ? WHERE id = ?", (new_name, role_id)
        )

    def delete_role(self, role_id: int) -> None:
        self.conn.execute("DELETE FROM roles WHERE id = ?", (role_id,))
```

- [ ] **Step 4: Run test, expect pass**

Run: `pytest tests/test_repository_roles.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/workload_analyzer/db/repository.py tests/test_repository_roles.py
git commit -m "feat(repo): CRUD for roles"
```

---

## Task 6: Repository — Categories

**Files:**
- Modify: `src/workload_analyzer/db/repository.py`
- Create: `tests/test_repository_categories.py`

- [ ] **Step 1: Write failing tests**

`tests/test_repository_categories.py`:
```python
import pytest

from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository


@pytest.fixture
def repo(tmp_db_path):
    conn = connect(tmp_db_path)
    r = Repository(conn)
    r.create_role("Entwicklung")
    yield r
    conn.close()


def test_create_category(repo):
    role_id = repo.list_roles()[0].id
    cid = repo.create_category(name="Frontend", color="#ff0000", role_id=role_id)
    assert cid > 0


def test_list_categories_includes_role_name(repo):
    role_id = repo.list_roles()[0].id
    repo.create_category(name="Frontend", color="#ff0000", role_id=role_id)
    cats = repo.list_categories()
    assert len(cats) == 1
    assert cats[0].name == "Frontend"
    assert cats[0].role_id == role_id


def test_list_active_categories_excludes_inactive(repo):
    role_id = repo.list_roles()[0].id
    cid1 = repo.create_category(name="Active", color="#0", role_id=role_id)
    cid2 = repo.create_category(name="Inactive", color="#0", role_id=role_id)
    repo.set_category_active(cid2, False)
    active = repo.list_categories(active_only=True)
    assert [c.id for c in active] == [cid1]


def test_update_category(repo):
    role_id = repo.list_roles()[0].id
    cid = repo.create_category(name="Old", color="#000", role_id=role_id)
    repo.update_category(cid, name="New", color="#fff", role_id=role_id, active=True, outlook_category_name="OL")
    cats = repo.list_categories()
    assert cats[0].name == "New"
    assert cats[0].color == "#fff"
    assert cats[0].outlook_category_name == "OL"


def test_find_category_by_outlook_name(repo):
    role_id = repo.list_roles()[0].id
    cid = repo.create_category(name="Frontend", color="#0", role_id=role_id, outlook_category_name="Project A - FE")
    found = repo.find_category_by_outlook_name("Project A - FE")
    assert found is not None
    assert found.id == cid


def test_delete_category(repo):
    role_id = repo.list_roles()[0].id
    cid = repo.create_category(name="Tmp", color="#0", role_id=role_id)
    repo.delete_category(cid)
    assert repo.list_categories() == []
```

- [ ] **Step 2: Run test, expect failure**

Run: `pytest tests/test_repository_categories.py -v`
Expected: AttributeError on `create_category`.

- [ ] **Step 3: Extend Repository**

Append to `src/workload_analyzer/db/repository.py`:
```python
    # --- Categories ---

    def create_category(
        self,
        name: str,
        color: str,
        role_id: int,
        active: bool = True,
        outlook_category_name: Optional[str] = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO categories (name, color, role_id, active, outlook_category_name)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, color, role_id, 1 if active else 0, outlook_category_name),
        )
        return cur.lastrowid

    def list_categories(self, active_only: bool = False) -> list["Category"]:
        from workload_analyzer.models import Category
        sql = "SELECT id, name, color, role_id, active, outlook_category_name FROM categories"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY name"
        rows = self.conn.execute(sql).fetchall()
        return [
            Category(
                id=r["id"], name=r["name"], color=r["color"],
                role_id=r["role_id"], active=bool(r["active"]),
                outlook_category_name=r["outlook_category_name"],
            )
            for r in rows
        ]

    def get_category(self, category_id: int) -> Optional["Category"]:
        from workload_analyzer.models import Category
        row = self.conn.execute(
            "SELECT id, name, color, role_id, active, outlook_category_name "
            "FROM categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        if row is None:
            return None
        return Category(
            id=row["id"], name=row["name"], color=row["color"],
            role_id=row["role_id"], active=bool(row["active"]),
            outlook_category_name=row["outlook_category_name"],
        )

    def update_category(
        self, category_id: int, name: str, color: str, role_id: int,
        active: bool, outlook_category_name: Optional[str],
    ) -> None:
        self.conn.execute(
            """
            UPDATE categories
            SET name = ?, color = ?, role_id = ?, active = ?, outlook_category_name = ?
            WHERE id = ?
            """,
            (name, color, role_id, 1 if active else 0, outlook_category_name, category_id),
        )

    def set_category_active(self, category_id: int, active: bool) -> None:
        self.conn.execute(
            "UPDATE categories SET active = ? WHERE id = ?",
            (1 if active else 0, category_id),
        )

    def find_category_by_outlook_name(self, outlook_name: str) -> Optional["Category"]:
        from workload_analyzer.models import Category
        row = self.conn.execute(
            "SELECT id, name, color, role_id, active, outlook_category_name "
            "FROM categories WHERE outlook_category_name = ?",
            (outlook_name,),
        ).fetchone()
        if row is None:
            return None
        return Category(
            id=row["id"], name=row["name"], color=row["color"],
            role_id=row["role_id"], active=bool(row["active"]),
            outlook_category_name=row["outlook_category_name"],
        )

    def delete_category(self, category_id: int) -> None:
        self.conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
```

- [ ] **Step 4: Run test, expect pass**

Run: `pytest tests/test_repository_categories.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/workload_analyzer/db/repository.py tests/test_repository_categories.py
git commit -m "feat(repo): CRUD for categories"
```

---

## Task 7: Repository — Time Entries (no overlap invariant)

**Files:**
- Modify: `src/workload_analyzer/db/repository.py`
- Create: `tests/test_repository_entries.py`

The non-overlap invariant is enforced **here** at insert/update time. Closed entries (end_ts NOT NULL) must not overlap with any other closed entry. At most one open entry (end_ts NULL) may exist.

- [ ] **Step 1: Write failing tests**

`tests/test_repository_entries.py`:
```python
import pytest

from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository, OverlapError
from workload_analyzer.models import EntrySource


@pytest.fixture
def repo(tmp_db_path):
    conn = connect(tmp_db_path)
    r = Repository(conn)
    rid = r.create_role("Entwicklung")
    r.create_category(name="A", color="#0", role_id=rid)
    r.create_category(name="B", color="#0", role_id=rid)
    yield r
    conn.close()


def test_start_entry_returns_id(repo):
    cat = repo.list_categories()[0]
    eid = repo.start_entry(category_id=cat.id, start_ts=1000, source=EntrySource.MANUAL)
    assert eid > 0


def test_only_one_open_entry_allowed(repo):
    cat = repo.list_categories()[0]
    repo.start_entry(category_id=cat.id, start_ts=1000, source=EntrySource.MANUAL)
    with pytest.raises(OverlapError):
        repo.start_entry(category_id=cat.id, start_ts=2000, source=EntrySource.MANUAL)


def test_close_open_entry(repo):
    cat = repo.list_categories()[0]
    eid = repo.start_entry(category_id=cat.id, start_ts=1000, source=EntrySource.MANUAL)
    repo.close_entry(eid, end_ts=1500)
    open_entry = repo.get_open_entry()
    assert open_entry is None


def test_get_open_entry_returns_active(repo):
    cat = repo.list_categories()[0]
    eid = repo.start_entry(category_id=cat.id, start_ts=1000, source=EntrySource.MANUAL)
    open_entry = repo.get_open_entry()
    assert open_entry is not None
    assert open_entry.id == eid
    assert open_entry.is_active()


def test_insert_closed_entry_no_overlap_ok(repo):
    cat = repo.list_categories()[0]
    repo.insert_closed_entry(category_id=cat.id, start_ts=1000, end_ts=2000, source=EntrySource.MANUAL)
    repo.insert_closed_entry(category_id=cat.id, start_ts=2000, end_ts=3000, source=EntrySource.MANUAL)


def test_insert_overlapping_closed_entry_rejected(repo):
    cat = repo.list_categories()[0]
    repo.insert_closed_entry(category_id=cat.id, start_ts=1000, end_ts=2000, source=EntrySource.MANUAL)
    with pytest.raises(OverlapError):
        repo.insert_closed_entry(category_id=cat.id, start_ts=1500, end_ts=2500, source=EntrySource.MANUAL)


def test_update_entry_rejects_overlap(repo):
    cat = repo.list_categories()[0]
    repo.insert_closed_entry(category_id=cat.id, start_ts=1000, end_ts=2000, source=EntrySource.MANUAL)
    eid2 = repo.insert_closed_entry(category_id=cat.id, start_ts=3000, end_ts=4000, source=EntrySource.MANUAL)
    with pytest.raises(OverlapError):
        repo.update_entry(eid2, category_id=cat.id, start_ts=1500, end_ts=2500, comment=None)


def test_delete_entry(repo):
    cat = repo.list_categories()[0]
    eid = repo.insert_closed_entry(category_id=cat.id, start_ts=1000, end_ts=2000, source=EntrySource.MANUAL)
    repo.delete_entry(eid)
    assert repo.list_entries_between(0, 10000) == []


def test_list_entries_between(repo):
    cat = repo.list_categories()[0]
    repo.insert_closed_entry(category_id=cat.id, start_ts=1000, end_ts=2000, source=EntrySource.MANUAL)
    repo.insert_closed_entry(category_id=cat.id, start_ts=5000, end_ts=6000, source=EntrySource.MANUAL)
    rows = repo.list_entries_between(0, 3000)
    assert len(rows) == 1
```

- [ ] **Step 2: Run test, expect failure**

Run: `pytest tests/test_repository_entries.py -v`
Expected: ImportError on `OverlapError`.

- [ ] **Step 3: Extend Repository with entries + OverlapError**

Append to `src/workload_analyzer/db/repository.py`:
```python
class OverlapError(ValueError):
    """Raised when a time entry would overlap with an existing entry."""


# Add methods to the Repository class:
```

Append inside `class Repository`:
```python
    # --- Time entries ---

    def get_open_entry(self) -> Optional["TimeEntry"]:
        from workload_analyzer.models import TimeEntry, EntrySource
        row = self.conn.execute(
            "SELECT id, category_id, start_ts, end_ts, source, comment "
            "FROM time_entries WHERE end_ts IS NULL"
        ).fetchone()
        if row is None:
            return None
        return TimeEntry(
            id=row["id"], category_id=row["category_id"],
            start_ts=row["start_ts"], end_ts=row["end_ts"],
            source=EntrySource(row["source"]), comment=row["comment"],
        )

    def start_entry(self, category_id: int, start_ts: int, source: "EntrySource") -> int:
        if self.get_open_entry() is not None:
            raise OverlapError("Another entry is currently open")
        self._check_no_overlap(start_ts, None, exclude_id=None)
        cur = self.conn.execute(
            "INSERT INTO time_entries (category_id, start_ts, end_ts, source) "
            "VALUES (?, ?, NULL, ?)",
            (category_id, start_ts, source.value),
        )
        return cur.lastrowid

    def close_entry(self, entry_id: int, end_ts: int) -> None:
        row = self.conn.execute(
            "SELECT start_ts FROM time_entries WHERE id = ?", (entry_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"No entry {entry_id}")
        if end_ts <= row["start_ts"]:
            raise ValueError("end_ts must be after start_ts")
        self._check_no_overlap(row["start_ts"], end_ts, exclude_id=entry_id)
        self.conn.execute(
            "UPDATE time_entries SET end_ts = ?, modified_at = datetime('now') WHERE id = ?",
            (end_ts, entry_id),
        )

    def insert_closed_entry(
        self, category_id: int, start_ts: int, end_ts: int,
        source: "EntrySource", comment: Optional[str] = None,
    ) -> int:
        if end_ts <= start_ts:
            raise ValueError("end_ts must be after start_ts")
        self._check_no_overlap(start_ts, end_ts, exclude_id=None)
        cur = self.conn.execute(
            "INSERT INTO time_entries (category_id, start_ts, end_ts, source, comment) "
            "VALUES (?, ?, ?, ?, ?)",
            (category_id, start_ts, end_ts, source.value, comment),
        )
        return cur.lastrowid

    def update_entry(
        self, entry_id: int, category_id: int, start_ts: int, end_ts: Optional[int],
        comment: Optional[str],
    ) -> None:
        if end_ts is not None and end_ts <= start_ts:
            raise ValueError("end_ts must be after start_ts")
        self._check_no_overlap(start_ts, end_ts, exclude_id=entry_id)
        self.conn.execute(
            """
            UPDATE time_entries
            SET category_id = ?, start_ts = ?, end_ts = ?, comment = ?,
                modified_at = datetime('now')
            WHERE id = ?
            """,
            (category_id, start_ts, end_ts, comment, entry_id),
        )

    def delete_entry(self, entry_id: int) -> None:
        self.conn.execute("DELETE FROM time_entries WHERE id = ?", (entry_id,))

    def list_entries_between(self, from_ts: int, to_ts: int) -> list["TimeEntry"]:
        from workload_analyzer.models import TimeEntry, EntrySource
        rows = self.conn.execute(
            """
            SELECT id, category_id, start_ts, end_ts, source, comment
            FROM time_entries
            WHERE start_ts < ? AND (end_ts IS NULL OR end_ts > ?)
            ORDER BY start_ts
            """,
            (to_ts, from_ts),
        ).fetchall()
        return [
            TimeEntry(
                id=r["id"], category_id=r["category_id"],
                start_ts=r["start_ts"], end_ts=r["end_ts"],
                source=EntrySource(r["source"]), comment=r["comment"],
            )
            for r in rows
        ]

    def _check_no_overlap(
        self, start_ts: int, end_ts: Optional[int], exclude_id: Optional[int],
    ) -> None:
        # An overlap exists if any other entry has (start_ts < new_end) AND (end_ts IS NULL OR end_ts > new_start).
        # If new_end is None (open entry), treat as +infinity.
        effective_end = end_ts if end_ts is not None else 2**63 - 1
        params: list = [effective_end, start_ts]
        sql = (
            "SELECT id FROM time_entries "
            "WHERE start_ts < ? "
            "AND (end_ts IS NULL OR end_ts > ?)"
        )
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        sql += " LIMIT 1"
        row = self.conn.execute(sql, params).fetchone()
        if row is not None:
            raise OverlapError(
                f"Entry [{start_ts}, {end_ts}] overlaps existing entry id={row['id']}"
            )
```

Also add `TimeEntry, EntrySource` to lazy imports already inside methods — already done.

- [ ] **Step 4: Run test, expect pass**

Run: `pytest tests/test_repository_entries.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/workload_analyzer/db/repository.py tests/test_repository_entries.py
git commit -m "feat(repo): time entry CRUD with non-overlap invariant"
```

---

## Task 8: Repository — Settings KV

**Files:**
- Modify: `src/workload_analyzer/db/repository.py`
- Create: `tests/test_repository_settings.py`

- [ ] **Step 1: Write failing tests**

`tests/test_repository_settings.py`:
```python
import pytest

from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository


@pytest.fixture
def repo(tmp_db_path):
    conn = connect(tmp_db_path)
    yield Repository(conn)
    conn.close()


def test_get_setting_default(repo):
    assert repo.get_setting("missing", default="x") == "x"


def test_set_and_get_setting(repo):
    repo.set_setting("rounding_minutes", "15")
    assert repo.get_setting("rounding_minutes") == "15"


def test_overwrite_setting(repo):
    repo.set_setting("k", "1")
    repo.set_setting("k", "2")
    assert repo.get_setting("k") == "2"
```

- [ ] **Step 2: Run test, expect failure**

Run: `pytest tests/test_repository_settings.py -v`
Expected: AttributeError.

- [ ] **Step 3: Extend Repository**

Append inside `class Repository`:
```python
    # --- Settings ---

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return default
        return row["value"]

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
```

- [ ] **Step 4: Run test, expect pass**

Run: `pytest tests/test_repository_settings.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/workload_analyzer/db/repository.py tests/test_repository_settings.py
git commit -m "feat(repo): settings key-value store"
```

---

## Task 9: Core — TimeTracker switching & pausing

**Files:**
- Create: `src/workload_analyzer/core/__init__.py`
- Create: `src/workload_analyzer/core/tracker.py`
- Create: `tests/test_tracker.py`

The TimeTracker is the in-memory state machine sitting over the repository. It exposes `start`, `switch_to`, `pause`, `resume`, `current_state()`. Time source is injected as a callable returning a unix timestamp so tests are deterministic. Lock/unlock and Outlook-driven flows come in later plans — for MVP the tracker only knows: idle → started → switched → paused.

- [ ] **Step 1: Create `core/__init__.py`** (empty)

- [ ] **Step 2: Write failing tests**

`tests/test_tracker.py`:
```python
import pytest

from workload_analyzer.core.tracker import TimeTracker, TrackerState
from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource


class FakeClock:
    def __init__(self, start: int = 1000):
        self.now = start

    def __call__(self) -> int:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += seconds


@pytest.fixture
def setup(tmp_db_path):
    conn = connect(tmp_db_path)
    repo = Repository(conn)
    rid = repo.create_role("R")
    c1 = repo.create_category(name="A", color="#0", role_id=rid)
    c2 = repo.create_category(name="B", color="#0", role_id=rid)
    clock = FakeClock()
    tracker = TimeTracker(repo=repo, clock=clock)
    yield tracker, repo, clock, c1, c2
    conn.close()


def test_initial_state_is_idle(setup):
    tracker, *_ = setup
    state = tracker.current_state()
    assert state.kind == TrackerState.Kind.IDLE
    assert state.category_id is None


def test_start_creates_open_entry(setup):
    tracker, repo, clock, c1, _ = setup
    tracker.start(category_id=c1, source=EntrySource.MANUAL)
    state = tracker.current_state()
    assert state.kind == TrackerState.Kind.TRACKING
    assert state.category_id == c1
    assert repo.get_open_entry() is not None


def test_switch_closes_previous_opens_new(setup):
    tracker, repo, clock, c1, c2 = setup
    tracker.start(category_id=c1, source=EntrySource.MANUAL)
    clock.advance(60)
    tracker.switch_to(category_id=c2, source=EntrySource.MANUAL)
    entries = repo.list_entries_between(0, 99999)
    assert len(entries) == 2
    closed = [e for e in entries if not e.is_active()]
    open_ = [e for e in entries if e.is_active()]
    assert len(closed) == 1
    assert closed[0].category_id == c1
    assert closed[0].duration_seconds() == 60
    assert len(open_) == 1
    assert open_[0].category_id == c2


def test_switch_to_same_category_is_noop(setup):
    tracker, repo, clock, c1, _ = setup
    tracker.start(category_id=c1, source=EntrySource.MANUAL)
    clock.advance(30)
    tracker.switch_to(category_id=c1, source=EntrySource.MANUAL)
    entries = repo.list_entries_between(0, 99999)
    assert len(entries) == 1  # still one open entry


def test_pause_closes_open_entry(setup):
    tracker, repo, clock, c1, _ = setup
    tracker.start(category_id=c1, source=EntrySource.MANUAL)
    clock.advance(60)
    tracker.pause()
    assert tracker.current_state().kind == TrackerState.Kind.PAUSED
    assert repo.get_open_entry() is None


def test_resume_opens_new_entry_on_last_category(setup):
    tracker, repo, clock, c1, _ = setup
    tracker.start(category_id=c1, source=EntrySource.MANUAL)
    clock.advance(60)
    tracker.pause()
    clock.advance(120)
    tracker.resume()
    state = tracker.current_state()
    assert state.kind == TrackerState.Kind.TRACKING
    assert state.category_id == c1


def test_pause_when_idle_is_noop(setup):
    tracker, *_ = setup
    tracker.pause()
    assert tracker.current_state().kind == TrackerState.Kind.IDLE


def test_load_state_from_db_picks_up_open_entry(setup, tmp_db_path):
    tracker, repo, clock, c1, _ = setup
    tracker.start(category_id=c1, source=EntrySource.MANUAL)
    # Recreate tracker on same db
    tracker2 = TimeTracker(repo=repo, clock=clock)
    tracker2.load_state()
    assert tracker2.current_state().kind == TrackerState.Kind.TRACKING
    assert tracker2.current_state().category_id == c1
```

- [ ] **Step 3: Run test, expect failure**

Run: `pytest tests/test_tracker.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement TimeTracker**

`src/workload_analyzer/core/tracker.py`:
```python
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource


@dataclass(frozen=True)
class TrackerState:
    class Kind(str, Enum):
        IDLE = "idle"
        TRACKING = "tracking"
        PAUSED = "paused"

    kind: "TrackerState.Kind"
    category_id: Optional[int]
    started_at: Optional[int]  # unix seconds of the current open entry's start


class TimeTracker:
    def __init__(self, repo: Repository, clock: Callable[[], int]):
        self.repo = repo
        self.clock = clock
        self._state = TrackerState(
            kind=TrackerState.Kind.IDLE, category_id=None, started_at=None,
        )
        self._last_category_id: Optional[int] = None

    def current_state(self) -> TrackerState:
        return self._state

    def load_state(self) -> None:
        """Rehydrate tracker from DB (e.g., after app restart)."""
        open_entry = self.repo.get_open_entry()
        if open_entry is not None:
            self._state = TrackerState(
                kind=TrackerState.Kind.TRACKING,
                category_id=open_entry.category_id,
                started_at=open_entry.start_ts,
            )
            self._last_category_id = open_entry.category_id

    def start(self, category_id: int, source: EntrySource) -> None:
        if self._state.kind == TrackerState.Kind.TRACKING:
            return self.switch_to(category_id, source)
        now = self.clock()
        self.repo.start_entry(category_id=category_id, start_ts=now, source=source)
        self._state = TrackerState(
            kind=TrackerState.Kind.TRACKING, category_id=category_id, started_at=now,
        )
        self._last_category_id = category_id

    def switch_to(self, category_id: int, source: EntrySource) -> None:
        if (
            self._state.kind == TrackerState.Kind.TRACKING
            and self._state.category_id == category_id
        ):
            return  # noop
        now = self.clock()
        open_entry = self.repo.get_open_entry()
        if open_entry is not None:
            self.repo.close_entry(open_entry.id, end_ts=now)
        self.repo.start_entry(category_id=category_id, start_ts=now, source=source)
        self._state = TrackerState(
            kind=TrackerState.Kind.TRACKING, category_id=category_id, started_at=now,
        )
        self._last_category_id = category_id

    def pause(self) -> None:
        if self._state.kind != TrackerState.Kind.TRACKING:
            return
        now = self.clock()
        open_entry = self.repo.get_open_entry()
        if open_entry is not None:
            self.repo.close_entry(open_entry.id, end_ts=now)
        self._state = TrackerState(
            kind=TrackerState.Kind.PAUSED,
            category_id=None,
            started_at=None,
        )

    def resume(self) -> None:
        if self._state.kind != TrackerState.Kind.PAUSED:
            return
        if self._last_category_id is None:
            return
        self.start(self._last_category_id, source=EntrySource.MANUAL)
```

- [ ] **Step 5: Run test, expect pass**

Run: `pytest tests/test_tracker.py -v`
Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add src/workload_analyzer/core tests/test_tracker.py
git commit -m "feat(core): TimeTracker with start/switch/pause/resume"
```

---

## Task 10: Rounding Helper

**Files:**
- Create: `src/workload_analyzer/core/rounding.py`
- Create: `tests/test_rounding.py`

Rounding is presentation-only and operates on per-day aggregates per category. We round each entry's start and end to the nearest N-minute boundary, then drop entries whose rounded duration is 0. Adjacent entries that collide because of rounding keep their original order — the earlier entry wins, the later is pushed.

For the MVP we only need a function that aggregates a list of `(category_id, duration_seconds)` and rounds individual entries; total-preserving redistribution comes in a later plan. **Important:** the rounded total per category-day may differ from the raw sum by at most one rounding step.

- [ ] **Step 1: Write failing tests**

`tests/test_rounding.py`:
```python
import pytest

from workload_analyzer.core.rounding import round_seconds


@pytest.mark.parametrize("seconds,step_min,expected", [
    (0, 5, 0),
    (60, 5, 0),       # 1 min rounds down with step 5
    (150, 5, 300),    # 2.5 min rounds up to 5
    (449, 5, 300),    # 7.5 min rounds down
    (450, 5, 600),    # exactly 7.5 rounds up
    (901, 15, 900),
    (899, 15, 900),
])
def test_round_seconds_nearest(seconds, step_min, expected):
    assert round_seconds(seconds, step_min) == expected


def test_round_seconds_step_zero_returns_input():
    assert round_seconds(123, 0) == 123


def test_round_seconds_negative_raises():
    with pytest.raises(ValueError):
        round_seconds(-1, 5)
```

- [ ] **Step 2: Run test, expect failure**

Run: `pytest tests/test_rounding.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

`src/workload_analyzer/core/rounding.py`:
```python
def round_seconds(seconds: int, step_minutes: int) -> int:
    """Round a duration in seconds to the nearest step_minutes boundary.

    step_minutes == 0 disables rounding. Ties round up.
    """
    if seconds < 0:
        raise ValueError("seconds must be non-negative")
    if step_minutes == 0:
        return seconds
    step = step_minutes * 60
    # Add half a step so that ties round up consistently.
    return ((seconds + step // 2) // step) * step
```

- [ ] **Step 4: Run test, expect pass**

Run: `pytest tests/test_rounding.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/workload_analyzer/core/rounding.py tests/test_rounding.py
git commit -m "feat(core): per-entry duration rounding helper"
```

---

## Task 11: Export — Excel & CSV

**Files:**
- Create: `src/workload_analyzer/services/__init__.py`
- Create: `src/workload_analyzer/services/export.py`
- Create: `tests/test_export.py`

Two sheets in the Excel: `Summary` (rows: role/category, columns: hours per day in range, totals) and `Details` (one row per time_entry).
CSV mirrors `Details` only (analysis-friendly).

- [ ] **Step 1: Create `services/__init__.py`** (empty)

- [ ] **Step 2: Write failing tests**

`tests/test_export.py`:
```python
import csv
from pathlib import Path

import pytest
from openpyxl import load_workbook

from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource
from workload_analyzer.services.export import export_csv, export_xlsx


@pytest.fixture
def repo_with_entries(tmp_db_path):
    conn = connect(tmp_db_path)
    repo = Repository(conn)
    rid = repo.create_role("Entwicklung")
    cid = repo.create_category(name="Frontend", color="#0", role_id=rid)
    repo.insert_closed_entry(category_id=cid, start_ts=1700000000, end_ts=1700003600, source=EntrySource.MANUAL)
    repo.insert_closed_entry(category_id=cid, start_ts=1700003600, end_ts=1700007200, source=EntrySource.MANUAL, comment="note")
    yield repo
    conn.close()


def test_export_csv_writes_rows(repo_with_entries, tmp_path: Path):
    out = tmp_path / "out.csv"
    export_csv(repo_with_entries, from_ts=0, to_ts=9999999999, out_path=out)
    with out.open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["start", "end", "duration_minutes", "role", "category", "source", "comment"]
    assert len(rows) == 3
    assert rows[1][3] == "Entwicklung"
    assert rows[1][4] == "Frontend"


def test_export_xlsx_has_summary_and_details_sheets(repo_with_entries, tmp_path: Path):
    out = tmp_path / "out.xlsx"
    export_xlsx(repo_with_entries, from_ts=0, to_ts=9999999999, rounding_minutes=0, out_path=out)
    wb = load_workbook(out)
    assert "Summary" in wb.sheetnames
    assert "Details" in wb.sheetnames
    details = wb["Details"]
    headers = [c.value for c in details[1]]
    assert "category" in headers
    assert "duration_minutes" in headers


def test_export_xlsx_summary_aggregates_per_category(repo_with_entries, tmp_path: Path):
    out = tmp_path / "out.xlsx"
    export_xlsx(repo_with_entries, from_ts=0, to_ts=9999999999, rounding_minutes=0, out_path=out)
    wb = load_workbook(out)
    summary = wb["Summary"]
    rows = list(summary.iter_rows(values_only=True))
    # Expect header + one data row for "Frontend" with 120 minutes total
    data_rows = [r for r in rows[1:] if r[0] is not None]
    assert len(data_rows) == 1
    role, category, total_minutes = data_rows[0][0], data_rows[0][1], data_rows[0][2]
    assert role == "Entwicklung"
    assert category == "Frontend"
    assert total_minutes == 120
```

- [ ] **Step 3: Run test, expect failure**

Run: `pytest tests/test_export.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement export**

`src/workload_analyzer/services/export.py`:
```python
import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook

from workload_analyzer.core.rounding import round_seconds
from workload_analyzer.db.repository import Repository


def _ts_to_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def _gather_rows(repo: Repository, from_ts: int, to_ts: int, rounding_minutes: int):
    """Yield (start, end, duration_min, role, category, source, comment) tuples."""
    cats = {c.id: c for c in repo.list_categories()}
    roles = {r.id: r for r in repo.list_roles()}
    for entry in repo.list_entries_between(from_ts, to_ts):
        if entry.end_ts is None:
            continue
        cat = cats.get(entry.category_id)
        if cat is None:
            continue
        role = roles.get(cat.role_id)
        role_name = role.name if role else ""
        duration_s = round_seconds(entry.duration_seconds(), rounding_minutes)
        if duration_s == 0 and rounding_minutes != 0:
            continue
        yield (
            _ts_to_iso(entry.start_ts),
            _ts_to_iso(entry.end_ts),
            duration_s // 60,
            role_name,
            cat.name,
            entry.source.value,
            entry.comment or "",
        )


def export_csv(repo: Repository, from_ts: int, to_ts: int, out_path: Path, rounding_minutes: int = 0) -> None:
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["start", "end", "duration_minutes", "role", "category", "source", "comment"])
        for row in _gather_rows(repo, from_ts, to_ts, rounding_minutes):
            writer.writerow(row)


def export_xlsx(repo: Repository, from_ts: int, to_ts: int, rounding_minutes: int, out_path: Path) -> None:
    rows = list(_gather_rows(repo, from_ts, to_ts, rounding_minutes))

    wb = Workbook()
    # Summary first
    summary = wb.active
    summary.title = "Summary"
    summary.append(["Role", "Category", "Total minutes"])
    totals: dict[tuple[str, str], int] = defaultdict(int)
    for start, end, dur, role, cat, src, comment in rows:
        totals[(role, cat)] += dur
    for (role, cat), dur in sorted(totals.items()):
        summary.append([role, cat, dur])

    # Details
    details = wb.create_sheet("Details")
    details.append(["start", "end", "duration_minutes", "role", "category", "source", "comment"])
    for row in rows:
        details.append(list(row))

    wb.save(out_path)
```

- [ ] **Step 5: Run test, expect pass**

Run: `pytest tests/test_export.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/workload_analyzer/services tests/test_export.py
git commit -m "feat(export): CSV and XLSX export with Summary + Details"
```

---

## Task 12: UI — Application Bootstrap & Tray Icon

**Files:**
- Create: `src/workload_analyzer/ui/__init__.py`
- Create: `src/workload_analyzer/ui/tray.py`
- Create: `src/workload_analyzer/app.py`
- Modify: `src/workload_analyzer/__main__.py`

This task is mostly plumbing — UI tests for tray icons are flaky in headless CI, so we keep this manual-verify. The tray menu is built from a small list of `QAction`s wired to tracker methods.

- [ ] **Step 1: Create `ui/__init__.py`** (empty)

- [ ] **Step 2: Implement `TrayIcon`**

`src/workload_analyzer/ui/tray.py`:
```python
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QApplication

from workload_analyzer.core.tracker import TimeTracker, TrackerState
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource


def _make_color_icon(color_hex: str) -> QIcon:
    pix = QPixmap(32, 32)
    pix.fill(QColor("transparent"))
    p = QPainter(pix)
    p.setBrush(QColor(color_hex))
    p.setPen(QColor("#222"))
    p.drawEllipse(4, 4, 24, 24)
    p.end()
    return QIcon(pix)


class TrayIcon(QObject):
    open_settings = pyqtSignal()
    open_reports = pyqtSignal()
    toggle_widget = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, repo: Repository, tracker: TimeTracker, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.repo = repo
        self.tracker = tracker

        self.icon = QSystemTrayIcon(_make_color_icon("#888888"))
        self.icon.setToolTip("WorkloadAnalyzer")

        self._build_menu()
        self.icon.show()

        # Refresh tooltip and menu state every 5 seconds.
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(5000)
        self.refresh()

    def _build_menu(self) -> None:
        self.menu = QMenu()

        self._header_action = QAction("Not tracking", self.menu)
        self._header_action.setEnabled(False)
        self.menu.addAction(self._header_action)
        self.menu.addSeparator()

        self._switch_menu = self.menu.addMenu("Switch to…")
        self._refresh_switch_menu()

        pause_action = QAction("Pause", self.menu)
        pause_action.triggered.connect(self._on_pause)
        self.menu.addAction(pause_action)
        self._pause_action = pause_action

        resume_action = QAction("Resume", self.menu)
        resume_action.triggered.connect(self.tracker.resume)
        self.menu.addAction(resume_action)
        self._resume_action = resume_action

        self.menu.addSeparator()

        widget_action = QAction("Toggle floating widget", self.menu)
        widget_action.triggered.connect(self.toggle_widget.emit)
        self.menu.addAction(widget_action)

        reports_action = QAction("Reports…", self.menu)
        reports_action.triggered.connect(self.open_reports.emit)
        self.menu.addAction(reports_action)

        settings_action = QAction("Settings…", self.menu)
        settings_action.triggered.connect(self.open_settings.emit)
        self.menu.addAction(settings_action)

        self.menu.addSeparator()

        quit_action = QAction("Quit", self.menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        self.menu.addAction(quit_action)

        self.icon.setContextMenu(self.menu)

    def _refresh_switch_menu(self) -> None:
        self._switch_menu.clear()
        for cat in self.repo.list_categories(active_only=True):
            act = QAction(cat.name, self._switch_menu)
            act.setIcon(_make_color_icon(cat.color))
            act.triggered.connect(lambda _checked=False, cid=cat.id: self.tracker.switch_to(cid, EntrySource.MANUAL))
            self._switch_menu.addAction(act)

    def refresh(self) -> None:
        self._refresh_switch_menu()
        state = self.tracker.current_state()
        if state.kind == TrackerState.Kind.TRACKING and state.category_id is not None:
            cat = self.repo.get_category(state.category_id)
            if cat:
                role = self.repo.get_role(cat.role_id)
                role_name = role.name if role else ""
                self._header_action.setText(f"{cat.name} ({role_name})")
                self.icon.setIcon(_make_color_icon(cat.color))
                self.icon.setToolTip(f"Tracking: {cat.name}")
            self._pause_action.setEnabled(True)
            self._resume_action.setEnabled(False)
        elif state.kind == TrackerState.Kind.PAUSED:
            self._header_action.setText("Paused")
            self.icon.setIcon(_make_color_icon("#cccc44"))
            self.icon.setToolTip("WorkloadAnalyzer (paused)")
            self._pause_action.setEnabled(False)
            self._resume_action.setEnabled(True)
        else:
            self._header_action.setText("Not tracking")
            self.icon.setIcon(_make_color_icon("#888888"))
            self.icon.setToolTip("WorkloadAnalyzer")
            self._pause_action.setEnabled(False)
            self._resume_action.setEnabled(False)

    def _on_pause(self) -> None:
        self.tracker.pause()
        self.refresh()
```

- [ ] **Step 3: Implement `app.py`**

`src/workload_analyzer/app.py`:
```python
import sys
import time

from PyQt6.QtWidgets import QApplication, QInputDialog

from workload_analyzer.core.tracker import TimeTracker, TrackerState
from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource
from workload_analyzer.paths import db_path
from workload_analyzer.ui.tray import TrayIcon


def run() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # keep tray running

    conn = connect(db_path())
    repo = Repository(conn)
    tracker = TimeTracker(repo=repo, clock=lambda: int(time.time()))
    tracker.load_state()

    # First-run: if there are no categories, force settings.
    if not repo.list_categories(active_only=True):
        from workload_analyzer.ui.settings_window import SettingsWindow
        win = SettingsWindow(repo)
        win.exec()

    # If still no categories, exit politely.
    cats = repo.list_categories(active_only=True)
    if not cats:
        return 0

    # If not currently tracking, ask which category to start with.
    if tracker.current_state().kind != TrackerState.Kind.TRACKING:
        names = [c.name for c in cats]
        choice, ok = QInputDialog.getItem(None, "Womit beginnst du?", "Kategorie:", names, 0, False)
        if ok:
            cat = next(c for c in cats if c.name == choice)
            tracker.start(category_id=cat.id, source=EntrySource.MANUAL)

    tray = TrayIcon(repo=repo, tracker=tracker)

    # Wire windows on demand.
    def open_settings():
        from workload_analyzer.ui.settings_window import SettingsWindow
        SettingsWindow(repo).exec()
        tray.refresh()

    def open_reports():
        from workload_analyzer.ui.reports_window import ReportsWindow
        ReportsWindow(repo).exec()

    floating_widget = None

    def toggle_widget():
        nonlocal floating_widget
        from workload_analyzer.ui.floating_widget import FloatingWidget
        if floating_widget is None or not floating_widget.isVisible():
            floating_widget = FloatingWidget(repo=repo, tracker=tracker)
            floating_widget.show()
        else:
            floating_widget.hide()

    tray.open_settings.connect(open_settings)
    tray.open_reports.connect(open_reports)
    tray.toggle_widget.connect(toggle_widget)
    tray.quit_requested.connect(app.quit)

    return app.exec()
```

- [ ] **Step 4: Update `__main__.py`**

```python
from workload_analyzer.app import run


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Manual verification**

Run: `python -m workload_analyzer`
Expected: Tray icon appears. Since no categories exist yet, settings window opens (will be implemented in next tasks; for now the import will fail — that's the next task's job to make the path work end-to-end).

Skip manual run for now if dependent modules don't exist; just verify the file is syntactically valid:
```bash
python -c "import workload_analyzer.ui.tray; import workload_analyzer.app"
```
Expected: ImportError for `ui.settings_window` is acceptable until Task 14 — but `ui.tray` and `app` themselves should at least parse. Use `python -m py_compile`:
```bash
python -m py_compile src/workload_analyzer/ui/tray.py src/workload_analyzer/app.py
```
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add src/workload_analyzer/ui/tray.py src/workload_analyzer/app.py src/workload_analyzer/ui/__init__.py src/workload_analyzer/__main__.py
git commit -m "feat(ui): tray icon with category switching and pause/resume"
```

---

## Task 13: UI — Floating Widget

**Files:**
- Create: `src/workload_analyzer/ui/floating_widget.py`

A small frameless window with: colored dot, category name, role name, elapsed time, category dropdown, pause/resume button. Always on top, draggable, position remembered in `settings` (`floating_widget_x`, `floating_widget_y`).

- [ ] **Step 1: Implement `floating_widget.py`**

```python
from typing import Optional

from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtGui import QMouseEvent, QColor
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from workload_analyzer.core.tracker import TimeTracker, TrackerState
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource


class FloatingWidget(QWidget):
    def __init__(self, repo: Repository, tracker: TimeTracker, parent: Optional[QWidget] = None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.repo = repo
        self.tracker = tracker
        self._drag_pos: Optional[QPoint] = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet("QWidget { background: #222; color: #eee; border-radius: 6px; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        top = QHBoxLayout()
        self.dot = QLabel("●")
        self.dot.setStyleSheet("color: #888; font-size: 18px;")
        top.addWidget(self.dot)
        self.label = QLabel("Not tracking")
        top.addWidget(self.label, 1)
        layout.addLayout(top)

        self.elapsed = QLabel("00:00:00")
        self.elapsed.setStyleSheet("font-family: monospace; font-size: 14px;")
        layout.addWidget(self.elapsed)

        bottom = QHBoxLayout()
        self.combo = QComboBox()
        bottom.addWidget(self.combo, 1)
        self.pause_btn = QPushButton("⏸")
        self.pause_btn.setFixedWidth(32)
        self.pause_btn.clicked.connect(self._on_pause)
        bottom.addWidget(self.pause_btn)
        layout.addLayout(bottom)

        self.combo.activated.connect(self._on_combo)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(1000)

        self._restore_position()
        self.refresh()

    def _restore_position(self) -> None:
        x = self.repo.get_setting("floating_widget_x")
        y = self.repo.get_setting("floating_widget_y")
        if x is not None and y is not None:
            self.move(int(x), int(y))

    def _save_position(self) -> None:
        self.repo.set_setting("floating_widget_x", str(self.x()))
        self.repo.set_setting("floating_widget_y", str(self.y()))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None
        self._save_position()

    def _populate_combo(self) -> None:
        current = self.combo.currentData()
        self.combo.blockSignals(True)
        self.combo.clear()
        for c in self.repo.list_categories(active_only=True):
            self.combo.addItem(c.name, c.id)
        state = self.tracker.current_state()
        if state.category_id is not None:
            idx = self.combo.findData(state.category_id)
            if idx >= 0:
                self.combo.setCurrentIndex(idx)
        elif current is not None:
            idx = self.combo.findData(current)
            if idx >= 0:
                self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)

    def _on_combo(self, _index: int) -> None:
        cid = self.combo.currentData()
        if cid is not None:
            self.tracker.switch_to(cid, EntrySource.MANUAL)
            self.refresh()

    def _on_pause(self) -> None:
        state = self.tracker.current_state()
        if state.kind == TrackerState.Kind.TRACKING:
            self.tracker.pause()
        elif state.kind == TrackerState.Kind.PAUSED:
            self.tracker.resume()
        self.refresh()

    def refresh(self) -> None:
        self._populate_combo()
        state = self.tracker.current_state()
        if state.kind == TrackerState.Kind.TRACKING and state.category_id is not None:
            cat = self.repo.get_category(state.category_id)
            role = self.repo.get_role(cat.role_id) if cat else None
            self.dot.setStyleSheet(f"color: {cat.color if cat else '#888'}; font-size: 18px;")
            self.label.setText(f"{cat.name}  ·  {role.name if role else ''}")
            import time
            elapsed = int(time.time()) - (state.started_at or int(time.time()))
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            self.elapsed.setText(f"{h:02d}:{m:02d}:{s:02d}")
            self.pause_btn.setText("⏸")
        elif state.kind == TrackerState.Kind.PAUSED:
            self.dot.setStyleSheet("color: #cc4; font-size: 18px;")
            self.label.setText("Paused")
            self.elapsed.setText("--:--:--")
            self.pause_btn.setText("▶")
        else:
            self.dot.setStyleSheet("color: #888; font-size: 18px;")
            self.label.setText("Not tracking")
            self.elapsed.setText("00:00:00")
            self.pause_btn.setText("⏸")
```

- [ ] **Step 2: Verify parse**

Run: `python -m py_compile src/workload_analyzer/ui/floating_widget.py`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add src/workload_analyzer/ui/floating_widget.py
git commit -m "feat(ui): always-on-top floating widget with quick switch and pause"
```

---

## Task 14: UI — Settings Window

**Files:**
- Create: `src/workload_analyzer/ui/settings_window.py`

Two tabs:
1. **Roles & Categories** — table with add/edit/delete buttons; column for role assignment, color picker, active checkbox, Outlook category name (text). "Import from Outlook" button is disabled in MVP (label: *coming in next phase*).
2. **General** — Rounding minutes (combo: 0/5/10/15).

- [ ] **Step 1: Implement `settings_window.py`**

```python
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from workload_analyzer.db.repository import Repository


class SettingsWindow(QDialog):
    def __init__(self, repo: Repository, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("WorkloadAnalyzer — Einstellungen")
        self.resize(720, 520)

        tabs = QTabWidget(self)
        tabs.addTab(self._build_categories_tab(), "Rollen & Kategorien")
        tabs.addTab(self._build_general_tab(), "Allgemein")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    # --- Roles & Categories ---

    def _build_categories_tab(self) -> QWidget:
        w = QWidget(self)
        outer = QHBoxLayout(w)

        # Left: roles
        roles_box = QVBoxLayout()
        roles_box.addWidget(QLabel("Rollen"))
        self.roles_list = QListWidget()
        roles_box.addWidget(self.roles_list)
        rh = QHBoxLayout()
        add_role = QPushButton("Hinzufügen")
        add_role.clicked.connect(self._add_role)
        rename_role = QPushButton("Umbenennen")
        rename_role.clicked.connect(self._rename_role)
        del_role = QPushButton("Löschen")
        del_role.clicked.connect(self._delete_role)
        rh.addWidget(add_role)
        rh.addWidget(rename_role)
        rh.addWidget(del_role)
        roles_box.addLayout(rh)
        outer.addLayout(roles_box, 1)

        # Right: categories
        cats_box = QVBoxLayout()
        cats_box.addWidget(QLabel("Kategorien"))
        self.cat_table = QTableWidget(0, 5)
        self.cat_table.setHorizontalHeaderLabels(["Name", "Rolle", "Farbe", "Aktiv", "Outlook-Name"])
        self.cat_table.horizontalHeader().setStretchLastSection(True)
        cats_box.addWidget(self.cat_table)

        ch = QHBoxLayout()
        add_cat = QPushButton("Hinzufügen")
        add_cat.clicked.connect(self._add_category)
        edit_cat = QPushButton("Bearbeiten")
        edit_cat.clicked.connect(self._edit_category)
        del_cat = QPushButton("Löschen")
        del_cat.clicked.connect(self._delete_category)
        import_outlook = QPushButton("Aus Outlook importieren (Phase 2)")
        import_outlook.setEnabled(False)
        ch.addWidget(add_cat)
        ch.addWidget(edit_cat)
        ch.addWidget(del_cat)
        ch.addWidget(import_outlook)
        cats_box.addLayout(ch)
        outer.addLayout(cats_box, 2)

        self._refresh_roles()
        self._refresh_categories()
        return w

    def _refresh_roles(self) -> None:
        self.roles_list.clear()
        for r in self.repo.list_roles():
            item = QListWidgetItem(r.name)
            item.setData(Qt.ItemDataRole.UserRole, r.id)
            self.roles_list.addItem(item)

    def _refresh_categories(self) -> None:
        cats = self.repo.list_categories()
        roles = {r.id: r.name for r in self.repo.list_roles()}
        self.cat_table.setRowCount(len(cats))
        for row, c in enumerate(cats):
            self.cat_table.setItem(row, 0, QTableWidgetItem(c.name))
            self.cat_table.setItem(row, 1, QTableWidgetItem(roles.get(c.role_id, "")))
            color_item = QTableWidgetItem(c.color)
            color_item.setBackground(QColor(c.color))
            self.cat_table.setItem(row, 2, color_item)
            self.cat_table.setItem(row, 3, QTableWidgetItem("✓" if c.active else "—"))
            self.cat_table.setItem(row, 4, QTableWidgetItem(c.outlook_category_name or ""))
            self.cat_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, c.id)

    def _add_role(self) -> None:
        name, ok = QInputDialog.getText(self, "Neue Rolle", "Name:")
        if ok and name.strip():
            try:
                self.repo.create_role(name.strip())
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))
            self._refresh_roles()

    def _rename_role(self) -> None:
        item = self.roles_list.currentItem()
        if not item:
            return
        rid = item.data(Qt.ItemDataRole.UserRole)
        new, ok = QInputDialog.getText(self, "Umbenennen", "Name:", text=item.text())
        if ok and new.strip():
            self.repo.rename_role(rid, new.strip())
            self._refresh_roles()
            self._refresh_categories()

    def _delete_role(self) -> None:
        item = self.roles_list.currentItem()
        if not item:
            return
        rid = item.data(Qt.ItemDataRole.UserRole)
        # Block delete if categories reference this role
        if any(c.role_id == rid for c in self.repo.list_categories()):
            QMessageBox.warning(self, "Nicht möglich", "Rolle wird noch von Kategorien verwendet.")
            return
        if QMessageBox.question(self, "Löschen?", f"Rolle '{item.text()}' löschen?") == QMessageBox.StandardButton.Yes:
            self.repo.delete_role(rid)
            self._refresh_roles()

    def _add_category(self) -> None:
        roles = self.repo.list_roles()
        if not roles:
            QMessageBox.warning(self, "Keine Rollen", "Bitte zuerst eine Rolle anlegen.")
            return
        dlg = _CategoryDialog(self, roles=roles)
        if dlg.exec():
            data = dlg.values()
            try:
                self.repo.create_category(**data)
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))
            self._refresh_categories()

    def _edit_category(self) -> None:
        row = self.cat_table.currentRow()
        if row < 0:
            return
        cid = self.cat_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        cat = self.repo.get_category(cid)
        if not cat:
            return
        roles = self.repo.list_roles()
        dlg = _CategoryDialog(self, roles=roles, initial=cat)
        if dlg.exec():
            data = dlg.values()
            self.repo.update_category(cid, **data)
            self._refresh_categories()

    def _delete_category(self) -> None:
        row = self.cat_table.currentRow()
        if row < 0:
            return
        cid = self.cat_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "Löschen?", "Kategorie löschen?") == QMessageBox.StandardButton.Yes:
            try:
                self.repo.delete_category(cid)
            except Exception as e:
                QMessageBox.warning(self, "Fehler", f"Kategorie ist in Zeiteinträgen referenziert: {e}")
            self._refresh_categories()

    # --- General ---

    def _build_general_tab(self) -> QWidget:
        w = QWidget(self)
        form = QFormLayout(w)

        self.rounding_combo = QComboBox()
        for v in [0, 5, 10, 15]:
            label = "Aus" if v == 0 else f"{v} Min"
            self.rounding_combo.addItem(label, v)
        current = int(self.repo.get_setting("rounding_minutes", "0") or "0")
        idx = self.rounding_combo.findData(current)
        if idx >= 0:
            self.rounding_combo.setCurrentIndex(idx)
        self.rounding_combo.currentIndexChanged.connect(self._save_rounding)
        form.addRow("Rundung:", self.rounding_combo)

        info = QLabel("Hotkeys, Autostart, Backup und Outlook-Integration kommen in den nächsten Phasen.")
        info.setStyleSheet("color: #888;")
        info.setWordWrap(True)
        form.addRow(info)

        return w

    def _save_rounding(self) -> None:
        val = self.rounding_combo.currentData()
        self.repo.set_setting("rounding_minutes", str(val))


class _CategoryDialog(QDialog):
    def __init__(self, parent, roles, initial=None):
        super().__init__(parent)
        self.setWindowTitle("Kategorie")
        self.roles = roles

        layout = QFormLayout(self)
        self.name = QLineEdit(initial.name if initial else "")
        layout.addRow("Name:", self.name)

        self.role_combo = QComboBox()
        for r in roles:
            self.role_combo.addItem(r.name, r.id)
        if initial:
            idx = self.role_combo.findData(initial.role_id)
            if idx >= 0:
                self.role_combo.setCurrentIndex(idx)
        layout.addRow("Rolle:", self.role_combo)

        color_box = QHBoxLayout()
        self.color = initial.color if initial else "#3388cc"
        self.color_btn = QPushButton()
        self.color_btn.setStyleSheet(f"background: {self.color};")
        self.color_btn.clicked.connect(self._pick_color)
        color_box.addWidget(self.color_btn)
        layout.addRow("Farbe:", color_box)

        self.active = QCheckBox()
        self.active.setChecked(initial.active if initial else True)
        layout.addRow("Aktiv:", self.active)

        self.outlook_name = QLineEdit(initial.outlook_category_name if initial and initial.outlook_category_name else "")
        layout.addRow("Outlook-Name:", self.outlook_name)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(QColor(self.color), self)
        if c.isValid():
            self.color = c.name()
            self.color_btn.setStyleSheet(f"background: {self.color};")

    def values(self) -> dict:
        return {
            "name": self.name.text().strip(),
            "color": self.color,
            "role_id": self.role_combo.currentData(),
            "active": self.active.isChecked(),
            "outlook_category_name": self.outlook_name.text().strip() or None,
        }
```

- [ ] **Step 2: Verify parse**

Run: `python -m py_compile src/workload_analyzer/ui/settings_window.py`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add src/workload_analyzer/ui/settings_window.py
git commit -m "feat(ui): settings window for roles, categories and rounding"
```

---

## Task 15: UI — Reports Window

**Files:**
- Create: `src/workload_analyzer/ui/reports_window.py`

Layout: date-range picker on top; tabs for **Tabelle** (QTableWidget with all entries in range, editable inline via row dialog), **Diagramm** (matplotlib donut by role+category). Export buttons in toolbar.

- [ ] **Step 1: Add matplotlib dependency**

Edit `pyproject.toml`, append to `dependencies`:
```toml
    "matplotlib>=3.8",
```

Reinstall:
```bash
python -m pip install -e ".[dev]"
```

- [ ] **Step 2: Implement `reports_window.py`**

```python
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)
from PyQt6.QtCore import QDate

from workload_analyzer.core.rounding import round_seconds
from workload_analyzer.db.repository import OverlapError, Repository
from workload_analyzer.services.export import export_csv, export_xlsx


def _qdate_to_ts(date: QDate, end_of_day: bool = False) -> int:
    py = date.toPyDate()
    dt = datetime(py.year, py.month, py.day)
    if end_of_day:
        dt = dt + timedelta(days=1)
    return int(dt.timestamp())


class ReportsWindow(QDialog):
    def __init__(self, repo: Repository, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("WorkloadAnalyzer — Auswertungen")
        self.resize(900, 600)

        layout = QVBoxLayout(self)

        # Date range toolbar
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Von:"))
        self.from_date = QDateEdit(QDate.currentDate().addDays(-7))
        self.from_date.setCalendarPopup(True)
        toolbar.addWidget(self.from_date)
        toolbar.addWidget(QLabel("Bis:"))
        self.to_date = QDateEdit(QDate.currentDate())
        self.to_date.setCalendarPopup(True)
        toolbar.addWidget(self.to_date)
        refresh = QPushButton("Aktualisieren")
        refresh.clicked.connect(self._refresh)
        toolbar.addWidget(refresh)
        toolbar.addStretch(1)
        csv_btn = QPushButton("CSV exportieren")
        csv_btn.clicked.connect(self._export_csv)
        toolbar.addWidget(csv_btn)
        xlsx_btn = QPushButton("Excel exportieren")
        xlsx_btn.clicked.connect(self._export_xlsx)
        toolbar.addWidget(xlsx_btn)
        layout.addLayout(toolbar)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_table_tab(), "Tabelle")
        self.tabs.addTab(self._build_chart_tab(), "Diagramm")
        layout.addWidget(self.tabs)

        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.accept)
        close.accepted.connect(self.accept)
        layout.addWidget(close)

        self._refresh()

    def _range(self) -> tuple[int, int]:
        return _qdate_to_ts(self.from_date.date()), _qdate_to_ts(self.to_date.date(), end_of_day=True)

    # --- Table ---

    def _build_table_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Start", "Ende", "Dauer (Min)", "Rolle", "Kategorie", "Quelle", "Kommentar"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.table)
        h = QHBoxLayout()
        edit_btn = QPushButton("Bearbeiten")
        edit_btn.clicked.connect(self._edit_entry)
        del_btn = QPushButton("Löschen")
        del_btn.clicked.connect(self._delete_entry)
        h.addWidget(edit_btn)
        h.addWidget(del_btn)
        h.addStretch(1)
        v.addLayout(h)
        return w

    def _refresh_table(self) -> None:
        from_ts, to_ts = self._range()
        entries = [e for e in self.repo.list_entries_between(from_ts, to_ts) if e.end_ts is not None]
        cats = {c.id: c for c in self.repo.list_categories()}
        roles = {r.id: r for r in self.repo.list_roles()}
        rounding = int(self.repo.get_setting("rounding_minutes", "0") or "0")
        self.table.setRowCount(len(entries))
        for row, e in enumerate(entries):
            cat = cats.get(e.category_id)
            role = roles.get(cat.role_id) if cat else None
            dur = round_seconds(e.duration_seconds(), rounding) // 60
            start_str = datetime.fromtimestamp(e.start_ts).isoformat(sep=" ", timespec="minutes")
            end_str = datetime.fromtimestamp(e.end_ts).isoformat(sep=" ", timespec="minutes")
            for col, val in enumerate([start_str, end_str, str(dur), role.name if role else "", cat.name if cat else "", e.source.value, e.comment or ""]):
                item = QTableWidgetItem(val)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, e.id)
                self.table.setItem(row, col, item)

    def _edit_entry(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        eid = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        from_ts, to_ts = self._range()
        entry = next((e for e in self.repo.list_entries_between(from_ts, to_ts) if e.id == eid), None)
        if entry is None:
            return
        dlg = _EntryEditDialog(self, repo=self.repo, entry=entry)
        if dlg.exec():
            data = dlg.values()
            try:
                self.repo.update_entry(eid, **data)
            except OverlapError as e:
                QMessageBox.warning(self, "Überlappung", str(e))
            self._refresh()

    def _delete_entry(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        eid = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "Löschen?", "Eintrag löschen?") == QMessageBox.StandardButton.Yes:
            self.repo.delete_entry(eid)
            self._refresh()

    # --- Chart ---

    def _build_chart_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.figure = Figure(figsize=(6, 5))
        self.canvas = FigureCanvas(self.figure)
        v.addWidget(self.canvas)
        self.group_combo = QComboBox()
        self.group_combo.addItem("Nach Rolle", "role")
        self.group_combo.addItem("Nach Kategorie", "category")
        self.group_combo.currentIndexChanged.connect(self._refresh_chart)
        v.addWidget(self.group_combo)
        return w

    def _refresh_chart(self) -> None:
        from_ts, to_ts = self._range()
        entries = [e for e in self.repo.list_entries_between(from_ts, to_ts) if e.end_ts is not None]
        cats = {c.id: c for c in self.repo.list_categories()}
        roles = {r.id: r for r in self.repo.list_roles()}
        rounding = int(self.repo.get_setting("rounding_minutes", "0") or "0")
        group_mode = self.group_combo.currentData()

        totals: dict[str, int] = {}
        colors: dict[str, str] = {}
        for e in entries:
            cat = cats.get(e.category_id)
            if cat is None:
                continue
            if group_mode == "role":
                role = roles.get(cat.role_id)
                key = role.name if role else "(no role)"
                colors.setdefault(key, "#888888")
            else:
                key = cat.name
                colors[key] = cat.color
            totals[key] = totals.get(key, 0) + round_seconds(e.duration_seconds(), rounding)

        self.figure.clear()
        ax = self.figure.add_subplot(111)
        if not totals:
            ax.text(0.5, 0.5, "Keine Daten im Zeitraum", ha="center", va="center")
            ax.set_axis_off()
        else:
            labels = list(totals.keys())
            sizes = [totals[k] / 3600 for k in labels]
            ax.pie(sizes, labels=[f"{l}\n{s:.1f}h" for l, s in zip(labels, sizes)], colors=[colors[l] for l in labels], wedgeprops={"width": 0.4})
            ax.set_title("Stunden pro " + ("Rolle" if group_mode == "role" else "Kategorie"))
        self.canvas.draw()

    # --- Refresh & Export ---

    def _refresh(self) -> None:
        self._refresh_table()
        self._refresh_chart()

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "CSV speichern", "workload.csv", "CSV (*.csv)")
        if not path:
            return
        from_ts, to_ts = self._range()
        rounding = int(self.repo.get_setting("rounding_minutes", "0") or "0")
        export_csv(self.repo, from_ts=from_ts, to_ts=to_ts, out_path=Path(path), rounding_minutes=rounding)

    def _export_xlsx(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Excel speichern", "workload.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        from_ts, to_ts = self._range()
        rounding = int(self.repo.get_setting("rounding_minutes", "0") or "0")
        export_xlsx(self.repo, from_ts=from_ts, to_ts=to_ts, rounding_minutes=rounding, out_path=Path(path))


class _EntryEditDialog(QDialog):
    def __init__(self, parent, repo: Repository, entry):
        super().__init__(parent)
        self.repo = repo
        self.entry = entry
        self.setWindowTitle("Eintrag bearbeiten")
        form = QFormLayout(self)

        self.cat_combo = QComboBox()
        for c in repo.list_categories():
            self.cat_combo.addItem(c.name, c.id)
        idx = self.cat_combo.findData(entry.category_id)
        if idx >= 0:
            self.cat_combo.setCurrentIndex(idx)
        form.addRow("Kategorie:", self.cat_combo)

        self.start_edit = QLineEdit(datetime.fromtimestamp(entry.start_ts).isoformat(sep=" ", timespec="minutes"))
        self.end_edit = QLineEdit(datetime.fromtimestamp(entry.end_ts).isoformat(sep=" ", timespec="minutes"))
        form.addRow("Start:", self.start_edit)
        form.addRow("Ende:", self.end_edit)

        self.comment_edit = QLineEdit(entry.comment or "")
        form.addRow("Kommentar:", self.comment_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> dict:
        return {
            "category_id": self.cat_combo.currentData(),
            "start_ts": int(datetime.fromisoformat(self.start_edit.text().strip()).timestamp()),
            "end_ts": int(datetime.fromisoformat(self.end_edit.text().strip()).timestamp()),
            "comment": self.comment_edit.text().strip() or None,
        }
```

- [ ] **Step 3: Verify parse**

Run: `python -m py_compile src/workload_analyzer/ui/reports_window.py`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add src/workload_analyzer/ui/reports_window.py pyproject.toml
git commit -m "feat(ui): reports window with table, donut chart and export"
```

---

## Task 16: End-to-End Smoke Test

**Files:**
- Create: `tests/test_smoke.py`

A non-UI smoke test that exercises the full stack: create role, create category, switch via tracker, close entry, export.

- [ ] **Step 1: Write test**

`tests/test_smoke.py`:
```python
import time
from pathlib import Path

import pytest

from workload_analyzer.core.tracker import TimeTracker, TrackerState
from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource
from workload_analyzer.services.export import export_csv, export_xlsx


def test_full_flow(tmp_db_path: Path, tmp_path: Path):
    conn = connect(tmp_db_path)
    repo = Repository(conn)

    rid = repo.create_role("Entwicklung")
    c1 = repo.create_category(name="Frontend", color="#ff0000", role_id=rid)
    c2 = repo.create_category(name="Backend", color="#00ff00", role_id=rid)

    clock = [1700000000]
    tracker = TimeTracker(repo=repo, clock=lambda: clock[0])

    tracker.start(c1, source=EntrySource.MANUAL)
    clock[0] += 1800  # 30 min
    tracker.switch_to(c2, source=EntrySource.MANUAL)
    clock[0] += 3600  # 60 min
    tracker.pause()

    assert tracker.current_state().kind == TrackerState.Kind.PAUSED
    entries = repo.list_entries_between(0, 2_000_000_000)
    closed = [e for e in entries if e.end_ts is not None]
    assert len(closed) == 2

    csv_path = tmp_path / "out.csv"
    export_csv(repo, from_ts=0, to_ts=2_000_000_000, out_path=csv_path)
    assert csv_path.read_text(encoding="utf-8").count("\n") >= 3  # header + 2 rows

    xlsx_path = tmp_path / "out.xlsx"
    export_xlsx(repo, from_ts=0, to_ts=2_000_000_000, rounding_minutes=15, out_path=xlsx_path)
    assert xlsx_path.exists()

    conn.close()
```

- [ ] **Step 2: Run all tests**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_smoke.py
git commit -m "test: end-to-end smoke covering tracker + export"
```

---

## Task 17: README & MVP Manual Verification

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README**

```markdown
# WorkloadAnalyzer (MVP)

Windows time tracker with role/category-based reporting.

## Development

```
python -m pip install -e ".[dev]"
pytest
python -m workload_analyzer
```

## MVP scope

- Manual category switching from tray icon and floating widget
- Role and category management
- Pause/resume
- Reports: table, donut chart, CSV/Excel export
- SQLite storage at `%APPDATA%/WorkloadAnalyzer/workload.db`

## Coming next

- Outlook COM integration (auto category detection from open mails/tasks)
- Meeting auto-detection with lock mode
- Screen-lock / idle handling with recovery popup
- Global hotkeys, autostart with Windows, auto-backup
- PyInstaller + Inno Setup packaging
```

- [ ] **Step 2: Manual run**

Run: `python -m workload_analyzer`
Verify (manually):
- Tray icon appears.
- First run prompts to set up categories — open Settings, create one role and one category, close settings.
- Prompt asks which category to start with; pick one.
- Tray menu shows current category and quick-switch entries.
- Toggle floating widget — drag it, close it.
- Open Reports — chart and table reflect tracked time.
- Export CSV/XLSX — files open correctly.
- Quit via tray.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add MVP README"
```

---

## Self-Review Notes

**Spec coverage (Plan 1 / MVP only):**
- ✅ Datenmodell (alle Tabellen, Task 3)
- ✅ Rollen & Kategorien CRUD (Task 5, 6, 14)
- ✅ Tray-Icon (Task 12)
- ✅ Floating Widget (Task 13)
- ✅ TimeTracker mit Switch/Pause (Task 9)
- ✅ Non-Overlap-Invariante (Task 7)
- ✅ Rundung (Task 10, angewandt in Export/Reports)
- ✅ Reports + Excel/CSV-Export (Task 11, 15)
- ✅ %APPDATA%-Pfad (Task 2)
- ✅ Edit/Delete von Einträgen (Task 15)
- ⏭️ Outlook-Erkennung (Plan 2)
- ⏭️ Meeting/Lock-Modus (Plan 2)
- ⏭️ Idle + Screen-Lock (Plan 3)
- ⏭️ Hotkeys, Autostart, Backup (Plan 4)
- ⏭️ PyInstaller + Inno Setup (Plan 4)
- ⏭️ Lernregeln (`rejected_suggestions`, Schema bereit; UI in Plan 2)
- ⏭️ Reminder nach 2h (Plan 4)

**Placeholder scan:** No TBDs / TODOs / "fill in later" patterns found.

**Type consistency:** `TimeTracker`, `Repository`, `TrackerState`, `EntrySource`, `OverlapError` used consistently across tasks. `clock` is `Callable[[], int]` throughout.
