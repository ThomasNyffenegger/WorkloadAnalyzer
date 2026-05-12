# Outlook Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automatic category detection via classic Outlook COM — polls every 15s, shows suggestion popups, handles meeting lock, learns from rejections.

**Architecture:** `OutlookMonitor(QObject)` polls COM in the main thread via QTimer and emits Qt signals. `app.py` wires these signals to `TimeTracker` and popup dialogs. `Repository` gets CRUD for `rejected_suggestions`. Settings window gets an Outlook tab.

**Tech Stack:** PyQt6, pywin32 (COM), SQLite (existing), pytest-qt (tests with fake COM objects)

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `pyproject.toml` | Modify | Add `pywin32>=306` dependency |
| `src/workload_analyzer/models.py` | Modify | Add `RejectedSuggestion` dataclass |
| `src/workload_analyzer/db/repository.py` | Modify | Add `record_rejection`, `is_silenced`, `list_rejected_suggestions`, `set_silenced` |
| `src/workload_analyzer/services/outlook_monitor.py` | Create | `OutlookMonitor(QObject)` with QTimer polling + signals |
| `src/workload_analyzer/ui/suggestion_popup.py` | Create | `SuggestionPopup` + `MeetingCategoryDialog` |
| `src/workload_analyzer/ui/import_outlook_dialog.py` | Create | `ImportOutlookDialog` — reads Outlook categories via COM |
| `src/workload_analyzer/ui/tray.py` | Modify | Add `set_outlook_available(bool)`, orange icon when Outlook down |
| `src/workload_analyzer/ui/settings_window.py` | Modify | Add Outlook tab: poll interval + rejected suggestions table + import button |
| `src/workload_analyzer/app.py` | Modify | Create monitor, wire signals, implement `_on_category_detected` / `_on_meeting_started` / `_on_meeting_ended` |
| `tests/test_repository_rejected_suggestions.py` | Create | Unit tests for rejected_suggestions CRUD |
| `tests/test_outlook_monitor.py` | Create | Unit tests with fake COM objects |

---

### Task 1: Add pywin32 dependency + RejectedSuggestion model

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/workload_analyzer/models.py`

- [ ] **Step 1: Add pywin32 to pyproject.toml**

In `pyproject.toml`, add `"pywin32>=306"` to the `dependencies` list so it reads:

```toml
dependencies = [
    "PyQt6>=6.6",
    "openpyxl>=3.1",
    "matplotlib>=3.8",
    "pywin32>=306",
]
```

- [ ] **Step 2: Install the updated dependency**

```
pip install -e ".[dev]" --quiet
```

Expected: no errors, `pywin32` installs (Windows only).

- [ ] **Step 3: Add RejectedSuggestion dataclass to models.py**

Open `src/workload_analyzer/models.py`. Append at the end:

```python
@dataclass
class RejectedSuggestion:
    id: Optional[int]
    outlook_category_name: str
    app_category_id: int
    rejection_count: int
    silenced: bool
    last_rejected_at: str
```

- [ ] **Step 4: Verify models.py compiles**

```
python -m py_compile src/workload_analyzer/models.py && echo OK
```

Expected: `OK`

- [ ] **Step 5: Run existing tests to confirm no regressions**

```
python -m pytest tests/ -q
```

Expected: 55 passed.

- [ ] **Step 6: Commit**

```
git add pyproject.toml src/workload_analyzer/models.py
git commit -m "feat: add pywin32 dependency and RejectedSuggestion model"
```

---

### Task 2: Repository — rejected_suggestions CRUD

**Files:**
- Modify: `src/workload_analyzer/db/repository.py`
- Create: `tests/test_repository_rejected_suggestions.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_repository_rejected_suggestions.py`:

```python
import pytest
from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository


@pytest.fixture
def repo(tmp_db_path):
    return Repository(connect(tmp_db_path))


@pytest.fixture
def setup(repo):
    """Create a role + category for FK requirements."""
    role_id = repo.create_role("Dev")
    cat_id = repo.create_category("Coding", "#ff0000", role_id, outlook_category_name="coding")
    return {"role_id": role_id, "cat_id": cat_id}


def test_not_silenced_initially(repo, setup):
    assert repo.is_silenced("coding", setup["cat_id"]) is False


def test_record_rejection_increments_count(repo, setup):
    repo.record_rejection("coding", setup["cat_id"])
    repo.record_rejection("coding", setup["cat_id"])
    suggestions = repo.list_rejected_suggestions()
    assert len(suggestions) == 1
    assert suggestions[0].rejection_count == 2
    assert suggestions[0].silenced is False


def test_silenced_after_three_rejections(repo, setup):
    repo.record_rejection("coding", setup["cat_id"])
    repo.record_rejection("coding", setup["cat_id"])
    assert repo.is_silenced("coding", setup["cat_id"]) is False
    repo.record_rejection("coding", setup["cat_id"])
    assert repo.is_silenced("coding", setup["cat_id"]) is True


def test_immediate_silence(repo, setup):
    repo.record_rejection("coding", setup["cat_id"], immediate_silence=True)
    assert repo.is_silenced("coding", setup["cat_id"]) is True


def test_set_silenced_reactivates(repo, setup):
    repo.record_rejection("coding", setup["cat_id"], immediate_silence=True)
    s = repo.list_rejected_suggestions()[0]
    repo.set_silenced(s.id, False)
    assert repo.is_silenced("coding", setup["cat_id"]) is False


def test_list_rejected_suggestions_fields(repo, setup):
    repo.record_rejection("coding", setup["cat_id"])
    items = repo.list_rejected_suggestions()
    assert len(items) == 1
    s = items[0]
    assert s.outlook_category_name == "coding"
    assert s.app_category_id == setup["cat_id"]
    assert s.rejection_count == 1
    assert s.silenced is False
    assert s.last_rejected_at is not None
```

- [ ] **Step 2: Run tests to confirm they fail**

```
python -m pytest tests/test_repository_rejected_suggestions.py -v
```

Expected: 6 failures (methods not yet defined).

- [ ] **Step 3: Add CRUD methods to repository.py**

Open `src/workload_analyzer/db/repository.py`. Add a new section `# --- Rejected Suggestions ---` after the `# --- Settings ---` section:

```python
    # --- Rejected Suggestions ---

    def record_rejection(
        self, outlook_name: str, app_category_id: int, immediate_silence: bool = False,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO rejected_suggestions
                (outlook_category_name, app_category_id, rejection_count, silenced, last_rejected_at)
            VALUES (?, ?, 1, 0, datetime('now'))
            ON CONFLICT(outlook_category_name, app_category_id) DO UPDATE SET
                rejection_count = rejection_count + 1,
                last_rejected_at = datetime('now')
            """,
            (outlook_name, app_category_id),
        )
        if immediate_silence:
            self.conn.execute(
                "UPDATE rejected_suggestions SET silenced = 1 "
                "WHERE outlook_category_name = ? AND app_category_id = ?",
                (outlook_name, app_category_id),
            )
        else:
            row = self.conn.execute(
                "SELECT rejection_count FROM rejected_suggestions "
                "WHERE outlook_category_name = ? AND app_category_id = ?",
                (outlook_name, app_category_id),
            ).fetchone()
            if row and row["rejection_count"] >= 3:
                self.conn.execute(
                    "UPDATE rejected_suggestions SET silenced = 1 "
                    "WHERE outlook_category_name = ? AND app_category_id = ?",
                    (outlook_name, app_category_id),
                )

    def is_silenced(self, outlook_name: str, app_category_id: int) -> bool:
        row = self.conn.execute(
            "SELECT silenced FROM rejected_suggestions "
            "WHERE outlook_category_name = ? AND app_category_id = ?",
            (outlook_name, app_category_id),
        ).fetchone()
        return False if row is None else bool(row["silenced"])

    def list_rejected_suggestions(self) -> list["RejectedSuggestion"]:
        from workload_analyzer.models import RejectedSuggestion
        rows = self.conn.execute(
            """
            SELECT id, outlook_category_name, app_category_id,
                   rejection_count, silenced, last_rejected_at
            FROM rejected_suggestions
            ORDER BY last_rejected_at DESC
            """
        ).fetchall()
        return [
            RejectedSuggestion(
                id=r["id"],
                outlook_category_name=r["outlook_category_name"],
                app_category_id=r["app_category_id"],
                rejection_count=r["rejection_count"],
                silenced=bool(r["silenced"]),
                last_rejected_at=r["last_rejected_at"],
            )
            for r in rows
        ]

    def set_silenced(self, suggestion_id: int, silenced: bool) -> None:
        self.conn.execute(
            "UPDATE rejected_suggestions SET silenced = ? WHERE id = ?",
            (1 if silenced else 0, suggestion_id),
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```
python -m pytest tests/test_repository_rejected_suggestions.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Run full suite**

```
python -m pytest tests/ -q
```

Expected: 61 passed.

- [ ] **Step 6: Commit**

```
git add src/workload_analyzer/db/repository.py tests/test_repository_rejected_suggestions.py
git commit -m "feat(db): rejected_suggestions CRUD in repository"
```

---

### Task 3: OutlookMonitor — category detection + availability

**Files:**
- Create: `src/workload_analyzer/services/outlook_monitor.py`
- Create: `tests/test_outlook_monitor.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_outlook_monitor.py`:

```python
import pytest
from workload_analyzer.services.outlook_monitor import OutlookMonitor


# ---------------------------------------------------------------------------
# Fake COM objects (no pywin32 required)
# ---------------------------------------------------------------------------

class FakeItem:
    def __init__(self, categories="", subject="", start=None, end=None):
        self.Categories = categories
        self.Subject = subject
        self.Start = start
        self.End = end


class FakeInspector:
    def __init__(self, item=None):
        self.CurrentItem = item


class FakeFolder:
    def __init__(self, items=None):
        self.Items = items or []


class FakeNamespace:
    def __init__(self, appointments=None):
        self._appointments = appointments or []

    def GetDefaultFolder(self, folder_id):
        return FakeFolder(self._appointments)


class FakeOutlookApp:
    def __init__(self, inspector=None, appointments=None):
        self._inspector = inspector
        self._ns = FakeNamespace(appointments)

    def ActiveInspector(self):
        return self._inspector

    def GetNamespace(self, name):
        return self._ns


def _make_monitor(app_obj):
    """Create an OutlookMonitor with a fake Outlook factory."""
    return OutlookMonitor(outlook_factory=lambda: app_obj)


# ---------------------------------------------------------------------------
# Tests: category detection
# ---------------------------------------------------------------------------

def test_category_detected_emitted(qtbot):
    app_obj = FakeOutlookApp(inspector=FakeInspector(FakeItem(categories="Coding")))
    monitor = _make_monitor(app_obj)

    detected = []
    monitor.category_detected.connect(detected.append)
    monitor._poll()

    assert detected == ["Coding"]


def test_category_detected_strips_first_only(qtbot):
    """Only the first comma-separated category is used."""
    app_obj = FakeOutlookApp(inspector=FakeInspector(FakeItem(categories="Coding, Meetings")))
    monitor = _make_monitor(app_obj)

    detected = []
    monitor.category_detected.connect(detected.append)
    monitor._poll()

    assert detected == ["Coding"]


def test_no_signal_when_category_unchanged(qtbot):
    app_obj = FakeOutlookApp(inspector=FakeInspector(FakeItem(categories="Coding")))
    monitor = _make_monitor(app_obj)
    monitor._poll()  # first poll sets _last_category

    detected = []
    monitor.category_detected.connect(detected.append)
    monitor._poll()  # second poll — same category, no signal

    assert detected == []


def test_no_signal_when_no_inspector(qtbot):
    app_obj = FakeOutlookApp(inspector=None)
    monitor = _make_monitor(app_obj)

    detected = []
    monitor.category_detected.connect(detected.append)
    monitor._poll()

    assert detected == []


def test_availability_false_on_error(qtbot):
    def failing_factory():
        raise RuntimeError("Outlook not running")

    monitor = OutlookMonitor(outlook_factory=failing_factory)

    availability = []
    monitor.availability_changed.connect(availability.append)
    monitor._poll()

    assert availability == [False]


def test_availability_true_on_recovery(qtbot):
    """After an error, a successful poll emits availability_changed(True)."""
    calls = [0]

    def flaky_factory():
        calls[0] += 1
        if calls[0] == 1:
            raise RuntimeError("down")
        return FakeOutlookApp()

    monitor = OutlookMonitor(outlook_factory=flaky_factory)
    availability = []
    monitor.availability_changed.connect(availability.append)

    monitor._poll()  # fails → False
    monitor._poll()  # succeeds → True

    assert availability == [False, True]


def test_no_duplicate_availability_signals(qtbot):
    """availability_changed is only emitted when state actually changes."""
    def failing_factory():
        raise RuntimeError("down")

    monitor = OutlookMonitor(outlook_factory=failing_factory)
    availability = []
    monitor.availability_changed.connect(availability.append)

    monitor._poll()
    monitor._poll()
    monitor._poll()

    assert availability == [False]  # emitted once, not three times
```

- [ ] **Step 2: Run tests to confirm they fail**

```
python -m pytest tests/test_outlook_monitor.py -v
```

Expected: ImportError or 7 failures.

- [ ] **Step 3: Create outlook_monitor.py**

Create `src/workload_analyzer/services/outlook_monitor.py`:

```python
"""Outlook COM monitor — polls Outlook every N seconds and emits Qt signals."""
from __future__ import annotations

import datetime
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class OutlookMonitor(QObject):
    """Polls classic Outlook via COM (main thread, QTimer) and emits signals.

    Pass ``outlook_factory`` in tests to inject a fake Outlook application
    object instead of the real COM server.
    """

    category_detected = pyqtSignal(str)        # Outlook category name from active inspector
    meeting_started = pyqtSignal(str, object)   # (meeting title, Optional[str] outlook_category)
    meeting_ended = pyqtSignal()
    availability_changed = pyqtSignal(bool)     # True = Outlook reachable

    def __init__(
        self,
        outlook_factory: Optional[Callable] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        if outlook_factory is not None:
            self._factory = outlook_factory
        else:
            self._factory = self._default_factory

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)

        # Internal state for debouncing
        self._last_category: Optional[str] = None
        self._in_meeting: bool = False
        self._available: Optional[bool] = None  # None = never polled yet

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, interval_seconds: int = 15) -> None:
        """Start polling at the given interval."""
        self._timer.start(interval_seconds * 1000)

    def stop(self) -> None:
        """Stop polling."""
        self._timer.stop()

    def set_interval(self, seconds: int) -> None:
        """Change poll interval. Takes effect on the next tick."""
        if self._timer.isActive():
            self._timer.start(seconds * 1000)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _default_factory():
        import win32com.client  # noqa: PLC0415 — lazy import, Windows only
        return win32com.client.GetActiveObject("Outlook.Application")

    def _poll(self) -> None:
        """Single poll cycle. Called by QTimer and directly in tests."""
        try:
            app = self._factory()
        except Exception:
            if self._available is not False:
                self._available = False
                self.availability_changed.emit(False)
            self._last_category = None
            self._in_meeting = False
            return

        if self._available is not True:
            self._available = True
            self.availability_changed.emit(True)

        self._check_inspector(app)
        self._check_meeting(app)

    def _check_inspector(self, app) -> None:
        """Detect the category of the item open in the active inspector."""
        category: Optional[str] = None
        try:
            inspector = app.ActiveInspector()
            if inspector is not None:
                cats = inspector.CurrentItem.Categories
                if cats:
                    category = cats.split(",")[0].strip() or None
        except Exception:
            pass

        if category != self._last_category:
            self._last_category = category
            if category:
                self.category_detected.emit(category)

    def _check_meeting(self, app) -> None:
        """Detect whether a calendar appointment is currently running."""
        now = datetime.datetime.now()
        title: Optional[str] = None
        outlook_cat: Optional[str] = None

        try:
            ns = app.GetNamespace("MAPI")
            folder = ns.GetDefaultFolder(9)  # olFolderCalendar = 9
            for item in folder.Items:
                try:
                    if item.Start <= now <= item.End:
                        title = item.Subject
                        cats = item.Categories
                        outlook_cat = cats.split(",")[0].strip() if cats else None
                        break
                except Exception:
                    continue
        except Exception:
            pass

        if title is not None and not self._in_meeting:
            self._in_meeting = True
            self.meeting_started.emit(title, outlook_cat)
        elif title is None and self._in_meeting:
            self._in_meeting = False
            self.meeting_ended.emit()
```

- [ ] **Step 4: Run tests to confirm they pass**

```
python -m pytest tests/test_outlook_monitor.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Add meeting tests to test_outlook_monitor.py**

Append to `tests/test_outlook_monitor.py`:

```python
# ---------------------------------------------------------------------------
# Tests: meeting detection
# ---------------------------------------------------------------------------

def test_meeting_started_signal(qtbot):
    import datetime
    now = datetime.datetime.now()
    appt = FakeItem(
        subject="Team Sync",
        categories="Meetings",
        start=now - datetime.timedelta(minutes=5),
        end=now + datetime.timedelta(minutes=25),
    )
    app_obj = FakeOutlookApp(appointments=[appt])
    monitor = _make_monitor(app_obj)

    started = []
    monitor.meeting_started.connect(lambda t, c: started.append((t, c)))
    monitor._poll()

    assert started == [("Team Sync", "Meetings")]


def test_meeting_ended_signal(qtbot):
    import datetime
    now = datetime.datetime.now()
    appt = FakeItem(
        subject="Team Sync",
        start=now - datetime.timedelta(minutes=5),
        end=now + datetime.timedelta(minutes=25),
    )
    app_obj = FakeOutlookApp(appointments=[appt])
    monitor = _make_monitor(app_obj)
    monitor._poll()  # sets _in_meeting = True

    # Now remove the appointment (meeting over)
    app_obj._ns = FakeNamespace(appointments=[])
    ended = []
    monitor.meeting_ended.connect(lambda: ended.append(True))
    monitor._poll()

    assert ended == [True]


def test_no_duplicate_meeting_started(qtbot):
    import datetime
    now = datetime.datetime.now()
    appt = FakeItem(
        subject="Team Sync",
        start=now - datetime.timedelta(minutes=5),
        end=now + datetime.timedelta(minutes=25),
    )
    app_obj = FakeOutlookApp(appointments=[appt])
    monitor = _make_monitor(app_obj)
    monitor._poll()  # first poll

    started = []
    monitor.meeting_started.connect(lambda t, c: started.append(t))
    monitor._poll()  # second poll — already in meeting

    assert started == []


def test_meeting_no_category(qtbot):
    import datetime
    now = datetime.datetime.now()
    appt = FakeItem(
        subject="1:1",
        categories="",  # no category
        start=now - datetime.timedelta(minutes=1),
        end=now + datetime.timedelta(minutes=30),
    )
    app_obj = FakeOutlookApp(appointments=[appt])
    monitor = _make_monitor(app_obj)

    started = []
    monitor.meeting_started.connect(lambda t, c: started.append((t, c)))
    monitor._poll()

    assert started == [("1:1", None)]
```

- [ ] **Step 6: Run all monitor tests**

```
python -m pytest tests/test_outlook_monitor.py -v
```

Expected: 11 passed.

- [ ] **Step 7: Run full suite**

```
python -m pytest tests/ -q
```

Expected: 72 passed.

- [ ] **Step 8: Commit**

```
git add src/workload_analyzer/services/outlook_monitor.py tests/test_outlook_monitor.py
git commit -m "feat(services): OutlookMonitor with category and meeting detection"
```

---

### Task 4: SuggestionPopup + MeetingCategoryDialog

**Files:**
- Create: `src/workload_analyzer/ui/suggestion_popup.py`

- [ ] **Step 1: Create suggestion_popup.py**

Create `src/workload_analyzer/ui/suggestion_popup.py`:

```python
"""Popups for Outlook-driven suggestions and meeting category selection."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from workload_analyzer.models import Category

# Return codes from SuggestionPopup.exec()
SUGGESTION_YES = 1
SUGGESTION_NO = 2
SUGGESTION_NEVER = 3


class SuggestionPopup(QDialog):
    """Non-auto-closing popup asking whether to accept an Outlook category suggestion.

    Call exec() and check the return code against SUGGESTION_YES / SUGGESTION_NO /
    SUGGESTION_NEVER.
    """

    def __init__(
        self,
        outlook_name: str,
        app_category_name: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Kategorie erkannt")
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)

        label = QLabel(
            f'Outlook erkennt: "<b>{outlook_name}</b>" '
            f"→ <b>{app_category_name}</b>. Übernehmen?"
        )
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        layout.addWidget(label)

        btns = QHBoxLayout()
        yes_btn = QPushButton("Ja")
        no_btn = QPushButton("Nein")
        never_btn = QPushButton("Nie mehr")

        yes_btn.setDefault(True)
        yes_btn.clicked.connect(lambda: self.done(SUGGESTION_YES))
        no_btn.clicked.connect(lambda: self.done(SUGGESTION_NO))
        never_btn.clicked.connect(lambda: self.done(SUGGESTION_NEVER))

        btns.addWidget(yes_btn)
        btns.addWidget(no_btn)
        btns.addWidget(never_btn)
        layout.addLayout(btns)


class MeetingCategoryDialog(QDialog):
    """Blocking dialog asking which category to assign to a meeting with no Outlook category.

    Closing via the X button returns QDialog.DialogCode.Rejected — caller keeps
    the current tracking category unchanged.
    """

    def __init__(self, meeting_title: str, categories: list[Category], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Meeting gestartet")
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumWidth(340)

        layout = QVBoxLayout(self)

        label = QLabel(f"Meeting <b>{meeting_title}</b> gestartet. Welche Kategorie?")
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        layout.addWidget(label)

        self._combo = QComboBox()
        for cat in categories:
            self._combo.addItem(cat.name, userData=cat.id)
        layout.addWidget(self._combo)

        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        layout.addWidget(ok_btn)

    def selected_category_id(self) -> Optional[int]:
        return self._combo.currentData()
```

- [ ] **Step 2: Verify compilation**

```
python -m py_compile src/workload_analyzer/ui/suggestion_popup.py && echo OK
```

Expected: `OK`

- [ ] **Step 3: Run full test suite**

```
python -m pytest tests/ -q
```

Expected: 72 passed (no regressions).

- [ ] **Step 4: Commit**

```
git add src/workload_analyzer/ui/suggestion_popup.py
git commit -m "feat(ui): SuggestionPopup and MeetingCategoryDialog"
```

---

### Task 5: TrayIcon — Outlook availability indicator

**Files:**
- Modify: `src/workload_analyzer/ui/tray.py`

- [ ] **Step 1: Add `_outlook_available` flag and `set_outlook_available` to TrayIcon**

Open `src/workload_analyzer/ui/tray.py`.

In `__init__`, after `self.tracker = tracker`, add:

```python
        self._outlook_available: bool = True
```

After the `_on_pause` method at the bottom of the class, add:

```python
    def set_outlook_available(self, available: bool) -> None:
        """Called when OutlookMonitor reports availability change."""
        self._outlook_available = available
        self.refresh()
```

In `refresh()`, add the following block at the **very end** of the method (after all the if/elif/else branches), to override the icon when Outlook is down:

```python
        # Override icon colour when Outlook is unreachable
        if not self._outlook_available:
            self.icon.setIcon(_make_color_icon("#ff8800"))
            self.icon.setToolTip(self.icon.toolTip() + " ⚠ Outlook nicht verfügbar")
```

- [ ] **Step 2: Verify compilation**

```
python -m py_compile src/workload_analyzer/ui/tray.py && echo OK
```

Expected: `OK`

- [ ] **Step 3: Run full suite**

```
python -m pytest tests/ -q
```

Expected: 72 passed.

- [ ] **Step 4: Commit**

```
git add src/workload_analyzer/ui/tray.py
git commit -m "feat(ui): TrayIcon shows orange icon when Outlook unavailable"
```

---

### Task 6: Wire OutlookMonitor in app.py

**Files:**
- Modify: `src/workload_analyzer/app.py`

- [ ] **Step 1: Replace app.py with the wired version**

The current `src/workload_analyzer/app.py` has no Outlook integration. Replace its entire contents:

```python
import sys
import time

from PyQt6.QtWidgets import QApplication, QInputDialog

from workload_analyzer.core.tracker import TimeTracker, TrackerState
from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource
from workload_analyzer.paths import db_path
from workload_analyzer.services.outlook_monitor import OutlookMonitor
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

    # ------------------------------------------------------------------
    # Outlook Monitor
    # ------------------------------------------------------------------
    poll_seconds = int(repo.get_setting("outlook_poll_seconds", "15") or "15")
    monitor = OutlookMonitor()
    _active_popup = [None]  # list to allow mutation in nested closures

    def _on_category_detected(outlook_name: str) -> None:
        from workload_analyzer.ui.suggestion_popup import (
            SuggestionPopup, SUGGESTION_YES, SUGGESTION_NO, SUGGESTION_NEVER,
        )
        cat = repo.find_category_by_outlook_name(outlook_name)
        if cat is None:
            return
        if repo.is_silenced(outlook_name, cat.id):
            return
        # Close any previously open popup (treated as rejection)
        if _active_popup[0] is not None and _active_popup[0].isVisible():
            _active_popup[0].done(SUGGESTION_NO)
        popup = SuggestionPopup(outlook_name, cat.name)
        _active_popup[0] = popup
        result = popup.exec()
        if result == SUGGESTION_YES:
            tracker.switch_to(cat.id, EntrySource.AUTO_OUTLOOK)
        elif result == SUGGESTION_NO:
            repo.record_rejection(outlook_name, cat.id)
        elif result == SUGGESTION_NEVER:
            repo.record_rejection(outlook_name, cat.id, immediate_silence=True)

    def _on_meeting_started(title: str, outlook_category) -> None:
        from workload_analyzer.ui.suggestion_popup import MeetingCategoryDialog
        active_cats = repo.list_categories(active_only=True)
        if outlook_category:
            cat = repo.find_category_by_outlook_name(outlook_category)
            if cat:
                tracker.switch_to(cat.id, EntrySource.AUTO_MEETING)
                return
        # No mapped category — ask user
        dlg = MeetingCategoryDialog(title, active_cats)
        if dlg.exec():
            cat_id = dlg.selected_category_id()
            if cat_id is not None:
                tracker.switch_to(cat_id, EntrySource.AUTO_MEETING)

    def _on_meeting_ended() -> None:
        pass  # Lock release — tracker continues on current category

    monitor.category_detected.connect(_on_category_detected)
    monitor.meeting_started.connect(_on_meeting_started)
    monitor.meeting_ended.connect(_on_meeting_ended)
    monitor.availability_changed.connect(tray.set_outlook_available)
    monitor.start(poll_seconds)

    # ------------------------------------------------------------------
    # Settings / Reports / Widget
    # ------------------------------------------------------------------
    def open_settings():
        from workload_analyzer.ui.settings_window import SettingsWindow
        win = SettingsWindow(repo, monitor=monitor)
        win.exec()
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

    def _quit():
        monitor.stop()
        app.quit()

    tray.quit_requested.connect(_quit)

    return app.exec()
```

- [ ] **Step 2: Verify compilation**

```
python -m py_compile src/workload_analyzer/app.py && echo OK
```

Expected: `OK`

- [ ] **Step 3: Run full suite**

```
python -m pytest tests/ -q
```

Expected: 72 passed.

- [ ] **Step 4: Commit**

```
git add src/workload_analyzer/app.py
git commit -m "feat(app): wire OutlookMonitor signals in app startup"
```

---

### Task 7: Settings window — Outlook tab

**Files:**
- Modify: `src/workload_analyzer/ui/settings_window.py`

- [ ] **Step 1: Update SettingsWindow.__init__ to accept monitor parameter**

Open `src/workload_analyzer/ui/settings_window.py`.

Change the `__init__` signature from:
```python
    def __init__(self, repo: Repository, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.repo = repo
```
to:
```python
    def __init__(self, repo: Repository, monitor=None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.repo = repo
        self._monitor = monitor  # Optional[OutlookMonitor] — may be None in tests
```

- [ ] **Step 2: Add Outlook tab to the tabs widget**

In `__init__`, change:
```python
        tabs = QTabWidget(self)
        tabs.addTab(self._build_categories_tab(), "Rollen & Kategorien")
        tabs.addTab(self._build_general_tab(), "Allgemein")
```
to:
```python
        tabs = QTabWidget(self)
        tabs.addTab(self._build_categories_tab(), "Rollen & Kategorien")
        tabs.addTab(self._build_general_tab(), "Allgemein")
        tabs.addTab(self._build_outlook_tab(), "Outlook")
```

- [ ] **Step 3: Enable the Import button in the categories tab**

Find these two lines in `_build_categories_tab`:
```python
        import_outlook = QPushButton("Aus Outlook importieren (Phase 2)")
        import_outlook.setEnabled(False)
```
Replace with:
```python
        import_outlook = QPushButton("Aus Outlook importieren")
        import_outlook.clicked.connect(self._import_from_outlook)
```

- [ ] **Step 4: Add the Outlook tab builder and helper methods**

After the `_save_rounding` method (around line 207), add:

```python
    def _build_outlook_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        # Poll interval
        form = QFormLayout()
        self._poll_spin = QSpinBox()
        self._poll_spin.setRange(5, 60)
        self._poll_spin.setSuffix(" s")
        current_poll = int(self.repo.get_setting("outlook_poll_seconds", "15") or "15")
        self._poll_spin.setValue(current_poll)
        self._poll_spin.valueChanged.connect(self._save_poll_interval)
        form.addRow("Poll-Intervall:", self._poll_spin)
        layout.addLayout(form)

        layout.addWidget(QLabel("Stummgeschaltete Erkennungen:"))

        self._rejected_table = QTableWidget(0, 4)
        self._rejected_table.setHorizontalHeaderLabels(
            ["Outlook-Name", "App-Kategorie", "Ablehnungen", "Aktion"]
        )
        self._rejected_table.horizontalHeader().setStretchLastSection(True)
        self._rejected_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._rejected_table)

        self._refresh_rejected()
        return w

    def _save_poll_interval(self, value: int) -> None:
        self.repo.set_setting("outlook_poll_seconds", str(value))
        if self._monitor is not None:
            self._monitor.set_interval(value)

    def _refresh_rejected(self) -> None:
        suggestions = self.repo.list_rejected_suggestions()
        cats = {c.id: c.name for c in self.repo.list_categories()}
        self._rejected_table.setRowCount(0)
        self._suggestion_ids: list[int] = []
        for s in suggestions:
            row = self._rejected_table.rowCount()
            self._rejected_table.insertRow(row)
            self._suggestion_ids.append(s.id)
            self._rejected_table.setItem(row, 0, QTableWidgetItem(s.outlook_category_name))
            self._rejected_table.setItem(row, 1, QTableWidgetItem(cats.get(s.app_category_id, "?")))
            self._rejected_table.setItem(row, 2, QTableWidgetItem(str(s.rejection_count)))
            label = "Aktiv" if not s.silenced else "Stumm"
            action_btn = QPushButton("Reaktivieren" if s.silenced else "Stumm schalten")
            action_btn.clicked.connect(
                lambda _checked=False, sid=s.id, silenced=s.silenced: self._toggle_silenced(sid, silenced)
            )
            status_item = QTableWidgetItem(label)
            self._rejected_table.setItem(row, 3, status_item)
            self._rejected_table.setCellWidget(row, 3, action_btn)

    def _toggle_silenced(self, suggestion_id: int, currently_silenced: bool) -> None:
        self.repo.set_silenced(suggestion_id, not currently_silenced)
        self._refresh_rejected()

    def _import_from_outlook(self) -> None:
        from workload_analyzer.ui.import_outlook_dialog import ImportOutlookDialog
        dlg = ImportOutlookDialog(self.repo, self)
        if dlg.exec():
            self._refresh_categories()
```

You also need to add `QSpinBox` and `QTableWidget` to the existing imports at the top of `settings_window.py`. The current import already has `QTableWidget`; add `QSpinBox`:

Change:
```python
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
```
to:
```python
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
```

- [ ] **Step 5: Verify compilation**

```
python -m py_compile src/workload_analyzer/ui/settings_window.py && echo OK
```

Expected: `OK`

- [ ] **Step 6: Run full suite**

```
python -m pytest tests/ -q
```

Expected: 72 passed.

- [ ] **Step 7: Commit**

```
git add src/workload_analyzer/ui/settings_window.py
git commit -m "feat(ui): Outlook tab in settings (poll interval, rejected suggestions, import)"
```

---

### Task 8: ImportOutlookDialog

**Files:**
- Create: `src/workload_analyzer/ui/import_outlook_dialog.py`

- [ ] **Step 1: Create import_outlook_dialog.py**

Create `src/workload_analyzer/ui/import_outlook_dialog.py`:

```python
"""Dialog to import categories from classic Outlook into WorkloadAnalyzer."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QTableWidget, QVBoxLayout, QWidget,
)

from workload_analyzer.db.repository import Repository


# Mapping from Outlook OlCategoryColor enum int to approximate hex colour.
_OUTLOOK_COLORS: dict[int, str] = {
    0: "#888888",   # None
    1: "#e7a1a2",   # Red
    2: "#f9ba89",   # Orange
    3: "#f7d67b",   # Peach
    4: "#fcf26b",   # Yellow
    5: "#9dc27b",   # Green
    6: "#84b5b7",   # Teal
    7: "#d0c57b",   # Olive
    8: "#7ba5c5",   # Blue
    9: "#9999d8",   # Purple
    10: "#c27ba0",  # Maroon
    11: "#a0a0a0",  # Steel
    12: "#8c8c8c",  # DarkSteel
    13: "#7f7f7f",  # Gray
    14: "#595959",  # DarkGray
    15: "#222222",  # Black
    16: "#c53030",  # DarkRed
    17: "#d65f27",  # DarkOrange
    18: "#d4ac35",  # DarkPeach
    19: "#d4c730",  # DarkYellow
    20: "#5d9e4a",  # DarkGreen
    21: "#3f8c8e",  # DarkTeal
    22: "#7f7830",  # DarkOlive
    23: "#3560a3",  # DarkBlue
    24: "#6060a0",  # DarkPurple
    25: "#a03c78",  # DarkMaroon
}


def _outlook_color_to_hex(color_int: int) -> str:
    return _OUTLOOK_COLORS.get(color_int, "#888888")


class ImportOutlookDialog(QDialog):
    """Reads all Outlook categories via COM and lets the user map them to app categories.

    For each checked Outlook category the user can either:
    - Create a new app category (option "— Neu anlegen —")
    - Assign to an existing app category

    On OK, new categories are created and existing ones get their
    ``outlook_category_name`` updated.
    """

    def __init__(self, repo: Repository, parent=None):
        super().__init__(parent)
        self._repo = repo
        self.setWindowTitle("Aus Outlook importieren")
        self.resize(640, 420)
        self._app_categories = repo.list_categories()
        self._roles = repo.list_roles()
        self._outlook_data: list[tuple[str, str]] = []  # (name, color_hex)
        self._build_ui()
        self._load_outlook_categories()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Wähle Outlook-Kategorien zum Importieren aus:"))

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Outlook-Name", "Farbe", "Importieren", "App-Kategorie"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _load_outlook_categories(self) -> None:
        try:
            import win32com.client
            app = win32com.client.GetActiveObject("Outlook.Application")
            ns = app.GetNamespace("MAPI")
            outlook_cats = ns.Categories
        except Exception as exc:
            QMessageBox.critical(
                self, "Outlook nicht verfügbar",
                f"Outlook konnte nicht geöffnet werden:\n{exc}"
            )
            # Close the dialog after the message box
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self.reject)
            return

        self._table.setRowCount(0)
        self._outlook_data.clear()

        for i in range(outlook_cats.Count):
            try:
                cat = outlook_cats.Item(i + 1)
                name = cat.Name
                color_hex = _outlook_color_to_hex(int(cat.Color))
            except Exception:
                continue

            self._outlook_data.append((name, color_hex))
            row = self._table.rowCount()
            self._table.insertRow(row)

            # Column 0: name
            from PyQt6.QtWidgets import QTableWidgetItem
            self._table.setItem(row, 0, QTableWidgetItem(name))

            # Column 1: colour swatch
            dot = QLabel()
            dot.setFixedSize(16, 16)
            dot.setStyleSheet(
                f"background-color: {color_hex}; border-radius: 8px;"
            )
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.addWidget(dot)
            cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            self._table.setCellWidget(row, 1, cell)

            # Column 2: checkbox
            cb = QCheckBox()
            cb_cell = QWidget()
            cb_layout = QHBoxLayout(cb_cell)
            cb_layout.addWidget(cb)
            cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            self._table.setCellWidget(row, 2, cb_cell)

            # Column 3: app category combo
            combo = QComboBox()
            combo.addItem("— Neu anlegen —", userData=None)
            for app_cat in self._app_categories:
                combo.addItem(app_cat.name, userData=app_cat.id)
            self._table.setCellWidget(row, 3, combo)

    def _save(self) -> None:
        if not self._roles:
            QMessageBox.warning(self, "Fehler", "Bitte zuerst eine Rolle anlegen.")
            return

        default_role_id = self._roles[0].id

        for row in range(self._table.rowCount()):
            cb_cell = self._table.cellWidget(row, 2)
            cb = cb_cell.findChild(QCheckBox)
            if not cb or not cb.isChecked():
                continue

            outlook_name, color_hex = self._outlook_data[row]
            combo: QComboBox = self._table.cellWidget(row, 3)
            app_cat_id: Optional[int] = combo.currentData()

            if app_cat_id is None:
                # Create a new app category
                self._repo.create_category(
                    name=outlook_name,
                    color=color_hex,
                    role_id=default_role_id,
                    outlook_category_name=outlook_name,
                )
            else:
                # Update existing category's Outlook mapping
                cat = self._repo.get_category(app_cat_id)
                if cat:
                    self._repo.update_category(
                        app_cat_id,
                        cat.name,
                        cat.color,
                        cat.role_id,
                        cat.active,
                        outlook_category_name=outlook_name,
                    )

        self.accept()
```

- [ ] **Step 2: Verify compilation**

```
python -m py_compile src/workload_analyzer/ui/import_outlook_dialog.py && echo OK
```

Expected: `OK`

- [ ] **Step 3: Run full test suite**

```
python -m pytest tests/ -q
```

Expected: 72 passed.

- [ ] **Step 4: Commit**

```
git add src/workload_analyzer/ui/import_outlook_dialog.py
git commit -m "feat(ui): ImportOutlookDialog reads Outlook categories via COM"
```

---

### Task 9: Final wiring check + smoke test update

**Files:**
- Modify: `tests/test_smoke.py` (add one assertion)
- Verify: all modules compile together

- [ ] **Step 1: Verify all new modules compile cleanly**

```
python -m py_compile src/workload_analyzer/services/outlook_monitor.py src/workload_analyzer/ui/suggestion_popup.py src/workload_analyzer/ui/import_outlook_dialog.py src/workload_analyzer/ui/settings_window.py src/workload_analyzer/app.py && echo ALL OK
```

Expected: `ALL OK`

- [ ] **Step 2: Run the full test suite one final time**

```
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: 72 passed, 0 failed.

- [ ] **Step 3: Add a repository smoke test for rejected_suggestions**

Open `tests/test_smoke.py` and append:

```python
def test_rejection_learning_flow(tmp_db_path):
    """Smoke: record 3 rejections → silenced, then reactivate."""
    from workload_analyzer.db.connection import connect
    from workload_analyzer.db.repository import Repository

    repo = Repository(connect(tmp_db_path))
    role_id = repo.create_role("Dev")
    cat_id = repo.create_category("Coding", "#ff0000", role_id, outlook_category_name="Coding")

    assert not repo.is_silenced("Coding", cat_id)
    for _ in range(3):
        repo.record_rejection("Coding", cat_id)
    assert repo.is_silenced("Coding", cat_id)

    s = repo.list_rejected_suggestions()[0]
    repo.set_silenced(s.id, False)
    assert not repo.is_silenced("Coding", cat_id)
```

- [ ] **Step 4: Run tests**

```
python -m pytest tests/ -q
```

Expected: 73 passed.

- [ ] **Step 5: Commit**

```
git add tests/test_smoke.py
git commit -m "test: add rejection learning flow to smoke test"
```

---

## Done

Phase 2 is complete when all 73 tests pass and the following manual checks work:
1. Open Outlook, click a mail with a category → suggestion popup appears
2. Click "Ja" → tracker switches to the mapped app category
3. Click "Nie mehr" three times → no more popups for that combination
4. Settings → Outlook tab → see the silenced entry, click "Reaktivieren"
5. Close Outlook → tray icon turns orange
6. Settings → Outlook → "Aus Outlook importieren" → categories appear in the dialog
