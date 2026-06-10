# UX-Verbesserungen & Bugfixes (Phase 6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Fix real-usage pain points: Outlook UI blocking, suggestion popup improvements, import/editor UX, floating widget overhaul.

**Architecture:** Five independent tasks touching six files. Outlook polling moves to QThread worker. Suggestion popup gets countdown timer. Import dialog and category editor get table UX improvements. Floating widget gets title-bar drag, color strip, hide button. Tray gets double-click and widget visibility label.

**Tech Stack:** Python 3.11+, PyQt6, pythoncom (COM apartment threading), pytest-qt.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/workload_analyzer/services/outlook_monitor.py` | Modify | Extract `_OutlookWorker`, move COM polling to QThread |
| `src/workload_analyzer/ui/suggestion_popup.py` | Modify | Add 10s countdown auto-close |
| `src/workload_analyzer/app.py` | Modify | Suppress popup for same/unmapped category; wire floating widget hide signal; update toggle_widget |
| `src/workload_analyzer/ui/import_outlook_dialog.py` | Modify | Sortable cols, Select-All button, disable when no roles |
| `src/workload_analyzer/ui/settings_window.py` | Modify | cat_table read-only + sortable |
| `src/workload_analyzer/ui/floating_widget.py` | Modify | Title-bar drag, color strip, hide button, widget_hidden signal |
| `src/workload_analyzer/ui/tray.py` | Modify | Double-click show, dynamic menu label, set_widget_visible() |
| `tests/test_outlook_monitor.py` | Modify | Update `monitor._poll()` → `monitor._worker._poll()` |
| `tests/test_outlook_monitor_threading.py` | Create | Thread start/stop smoke tests |

---

## Task 1: Outlook-Threading

**Files:**
- Modify: `src/workload_analyzer/services/outlook_monitor.py`
- Modify: `tests/test_outlook_monitor.py`
- Create: `tests/test_outlook_monitor_threading.py`

### Background

Current `OutlookMonitor` uses a `QTimer` on the main thread. `_poll()` calls `GetActiveObject`, `ActiveInspector()`, and iterates calendar items — all of which can block for seconds, freezing the Qt event loop.

Fix: extract all COM logic into `_OutlookWorker(QObject)`, move it to a `QThread`. `OutlookMonitor`'s public API (signals + `start()`/`stop()`/`set_interval()`) stays identical so `app.py` needs no changes.

The existing tests call `monitor._poll()` directly — they'll be updated to call `monitor._worker._poll()` instead.

- [x] **Step 1: Update existing tests to use `_worker._poll()`**

In `tests/test_outlook_monitor.py`, replace every occurrence of `monitor._poll()` with `monitor._worker._poll()`. The `_make_monitor` helper stays the same.

Full updated file:

```python
import datetime

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
    monitor._worker._poll()

    assert detected == ["Coding"]


def test_category_detected_strips_first_only(qtbot):
    app_obj = FakeOutlookApp(inspector=FakeInspector(FakeItem(categories="Coding, Meetings")))
    monitor = _make_monitor(app_obj)

    detected = []
    monitor.category_detected.connect(detected.append)
    monitor._worker._poll()

    assert detected == ["Coding"]


def test_no_signal_when_category_unchanged(qtbot):
    app_obj = FakeOutlookApp(inspector=FakeInspector(FakeItem(categories="Coding")))
    monitor = _make_monitor(app_obj)
    monitor._worker._poll()

    detected = []
    monitor.category_detected.connect(detected.append)
    monitor._worker._poll()

    assert detected == []


def test_no_signal_when_no_inspector(qtbot):
    app_obj = FakeOutlookApp(inspector=None)
    monitor = _make_monitor(app_obj)

    detected = []
    monitor.category_detected.connect(detected.append)
    monitor._worker._poll()

    assert detected == []


def test_availability_false_on_error(qtbot):
    def failing_factory():
        raise RuntimeError("Outlook not running")

    monitor = OutlookMonitor(outlook_factory=failing_factory)

    availability = []
    monitor.availability_changed.connect(availability.append)
    monitor._worker._poll()

    assert availability == [False]


def test_availability_true_on_recovery(qtbot):
    calls = [0]

    def flaky_factory():
        calls[0] += 1
        if calls[0] == 1:
            raise RuntimeError("down")
        return FakeOutlookApp()

    monitor = OutlookMonitor(outlook_factory=flaky_factory)
    availability = []
    monitor.availability_changed.connect(availability.append)

    monitor._worker._poll()
    monitor._worker._poll()

    assert availability == [False, True]


def test_no_duplicate_availability_signals(qtbot):
    def failing_factory():
        raise RuntimeError("down")

    monitor = OutlookMonitor(outlook_factory=failing_factory)
    availability = []
    monitor.availability_changed.connect(availability.append)

    monitor._worker._poll()
    monitor._worker._poll()
    monitor._worker._poll()

    assert availability == [False]


# ---------------------------------------------------------------------------
# Tests: meeting detection
# ---------------------------------------------------------------------------

def test_meeting_started_signal(qtbot):
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
    monitor._worker._poll()

    assert started == [("Team Sync", "Meetings")]


def test_meeting_ended_signal(qtbot):
    now = datetime.datetime.now()
    appt = FakeItem(
        subject="Team Sync",
        start=now - datetime.timedelta(minutes=5),
        end=now + datetime.timedelta(minutes=25),
    )
    app_obj = FakeOutlookApp(appointments=[appt])
    monitor = _make_monitor(app_obj)
    monitor._worker._poll()

    app_obj._ns = FakeNamespace(appointments=[])
    ended = []
    monitor.meeting_ended.connect(lambda: ended.append(True))
    monitor._worker._poll()

    assert ended == [True]


def test_no_duplicate_meeting_started(qtbot):
    now = datetime.datetime.now()
    appt = FakeItem(
        subject="Team Sync",
        start=now - datetime.timedelta(minutes=5),
        end=now + datetime.timedelta(minutes=25),
    )
    app_obj = FakeOutlookApp(appointments=[appt])
    monitor = _make_monitor(app_obj)
    monitor._worker._poll()

    started = []
    monitor.meeting_started.connect(lambda t, c: started.append(t))
    monitor._worker._poll()

    assert started == []


def test_meeting_no_category(qtbot):
    now = datetime.datetime.now()
    appt = FakeItem(
        subject="1:1",
        categories="",
        start=now - datetime.timedelta(minutes=1),
        end=now + datetime.timedelta(minutes=30),
    )
    app_obj = FakeOutlookApp(appointments=[appt])
    monitor = _make_monitor(app_obj)

    started = []
    monitor.meeting_started.connect(lambda t, c: started.append((t, c)))
    monitor._worker._poll()

    assert started == [("1:1", None)]


def test_meeting_ended_emitted_on_availability_loss(qtbot):
    now = datetime.datetime.now()
    appt = FakeItem(
        subject="Team Sync",
        start=now - datetime.timedelta(minutes=5),
        end=now + datetime.timedelta(minutes=25),
    )
    calls = [0]

    def flaky_factory():
        calls[0] += 1
        if calls[0] == 1:
            return FakeOutlookApp(appointments=[appt])
        raise RuntimeError("Outlook crashed")

    monitor = OutlookMonitor(outlook_factory=flaky_factory)
    monitor._worker._poll()

    ended = []
    monitor.meeting_ended.connect(lambda: ended.append(True))
    monitor._worker._poll()

    assert ended == [True]
```

- [x] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_outlook_monitor.py -v
```

Expected: FAIL — `AttributeError: 'OutlookMonitor' object has no attribute '_worker'`

- [x] **Step 3: Rewrite `outlook_monitor.py`**

Replace the entire file with:

```python
"""Outlook COM monitor — polls Outlook every N seconds and emits Qt signals.

COM polling runs in a background QThread (_OutlookWorker) to avoid blocking
the main thread during calendar iteration.
"""
from __future__ import annotations

import datetime
from typing import Callable, Optional

from PyQt6.QtCore import QMetaObject, QObject, QThread, QTimer, Qt, pyqtSignal, pyqtSlot


class _OutlookWorker(QObject):
    """Runs inside a QThread. All COM calls happen here."""

    category_detected = pyqtSignal(str)
    meeting_started = pyqtSignal(str, object)
    meeting_ended = pyqtSignal()
    availability_changed = pyqtSignal(bool)

    def __init__(self, outlook_factory: Callable, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._factory = outlook_factory
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._last_category: Optional[str] = None
        self._in_meeting: bool = False
        self._available: Optional[bool] = None
        self._interval_ms: int = 15_000

    @pyqtSlot()
    def start_polling(self) -> None:
        """Called in worker thread when QThread starts."""
        try:
            import pythoncom  # noqa: PLC0415
            pythoncom.CoInitialize()
        except Exception:
            pass  # Not on Windows or pythoncom unavailable — tests run without it
        self._timer.start(self._interval_ms)

    @pyqtSlot()
    def stop_polling(self) -> None:
        """Stop timer and uninitialize COM. Called before thread quits."""
        self._timer.stop()
        try:
            import pythoncom  # noqa: PLC0415
            pythoncom.CoUninitialize()
        except Exception:
            pass

    @pyqtSlot(int)
    def update_interval(self, ms: int) -> None:
        self._interval_ms = ms
        if self._timer.isActive():
            self._timer.start(ms)

    def _poll(self) -> None:
        try:
            app = self._factory()
        except Exception:
            if self._available is not False:
                self._available = False
                self.availability_changed.emit(False)
            if self._in_meeting:
                self._in_meeting = False
                self.meeting_ended.emit()
            return

        if self._available is not True:
            self._available = True
            self.availability_changed.emit(True)

        self._check_inspector(app)
        self._check_meeting(app)

    def _check_inspector(self, app) -> None:
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
        now = datetime.datetime.now()
        title: Optional[str] = None
        outlook_cat: Optional[str] = None

        try:
            ns = app.GetNamespace("MAPI")
            folder = ns.GetDefaultFolder(9)
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


class OutlookMonitor(QObject):
    """Public API — same signals and methods as before. COM runs in background thread."""

    category_detected = pyqtSignal(str)
    meeting_started = pyqtSignal(str, object)
    meeting_ended = pyqtSignal()
    availability_changed = pyqtSignal(bool)

    _request_interval = pyqtSignal(int)  # internal: route set_interval to worker

    def __init__(
        self,
        outlook_factory: Optional[Callable] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        factory = outlook_factory if outlook_factory is not None else self._default_factory

        self._worker = _OutlookWorker(factory)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)

        # Wire lifecycle
        self._thread.started.connect(self._worker.start_polling)

        # Forward worker signals to OutlookMonitor signals (queued across threads)
        self._worker.category_detected.connect(self.category_detected)
        self._worker.meeting_started.connect(self.meeting_started)
        self._worker.meeting_ended.connect(self.meeting_ended)
        self._worker.availability_changed.connect(self.availability_changed)

        # Route interval changes to worker thread
        self._request_interval.connect(self._worker.update_interval)

    def start(self, interval_seconds: int = 15) -> None:
        self._worker._interval_ms = interval_seconds * 1000
        self._thread.start()

    def stop(self) -> None:
        if self._thread.isRunning():
            QMetaObject.invokeMethod(
                self._worker, "stop_polling",
                Qt.ConnectionType.BlockingQueuedConnection,
            )
            self._thread.quit()
            self._thread.wait()

    def set_interval(self, seconds: int) -> None:
        self._request_interval.emit(seconds * 1000)

    @staticmethod
    def _default_factory():
        import win32com.client  # noqa: PLC0415
        return win32com.client.GetActiveObject("Outlook.Application")
```

- [x] **Step 4: Run the updated tests**

```
python -m pytest tests/test_outlook_monitor.py -v
```

Expected: 14 passed

- [x] **Step 5: Write threading smoke tests**

Create `tests/test_outlook_monitor_threading.py`:

```python
"""Smoke tests: OutlookMonitor thread starts and stops cleanly."""
import pytest
from workload_analyzer.services.outlook_monitor import OutlookMonitor


def _make_monitor():
    def failing_factory():
        raise RuntimeError("Outlook not available in tests")
    return OutlookMonitor(outlook_factory=failing_factory)


def test_thread_starts_on_start(qtbot):
    monitor = _make_monitor()
    assert not monitor._thread.isRunning()
    monitor.start(interval_seconds=60)
    assert monitor._thread.isRunning()
    monitor.stop()


def test_thread_stops_on_stop(qtbot):
    monitor = _make_monitor()
    monitor.start(interval_seconds=60)
    monitor.stop()
    assert not monitor._thread.isRunning()


def test_stop_when_not_started_is_safe(qtbot):
    monitor = _make_monitor()
    monitor.stop()  # must not raise


def test_set_interval_does_not_crash_when_running(qtbot):
    monitor = _make_monitor()
    monitor.start(interval_seconds=60)
    monitor.set_interval(30)  # must not raise
    monitor.stop()
```

- [x] **Step 6: Run all tests**

```
python -m pytest --tb=short -q
```

Expected: 127 passed (123 existing + 4 new)

- [x] **Step 7: Commit**

```bash
git add src/workload_analyzer/services/outlook_monitor.py tests/test_outlook_monitor.py tests/test_outlook_monitor_threading.py
git commit -m "feat: move Outlook COM polling to background QThread"
```

---

## Task 2: Suggestion Popup — Auto-Close + Popup Suppression

**Files:**
- Modify: `src/workload_analyzer/ui/suggestion_popup.py`
- Modify: `src/workload_analyzer/app.py`

### Background

Two fixes:
1. `SuggestionPopup` auto-closes after 10s accepting the suggestion. The "Ja" button shows a countdown.
2. In `app.py`, `_on_category_detected` must suppress the popup if the detected category has no app mapping OR maps to the currently tracked category.

- [x] **Step 1: Write failing tests for auto-close**

Create `tests/test_suggestion_popup.py`:

```python
"""Tests for SuggestionPopup auto-close countdown."""
import pytest
from PyQt6.QtCore import QTimer
from workload_analyzer.ui.suggestion_popup import SuggestionPopup, SUGGESTION_YES


def test_yes_button_shows_countdown(qtbot):
    popup = SuggestionPopup("Meetings", "Besprechungen")
    qtbot.addWidget(popup)
    popup.show()
    # Initially shows countdown start value
    assert "10" in popup._yes_btn.text()


def test_auto_close_accepts_after_timeout(qtbot):
    popup = SuggestionPopup("Meetings", "Besprechungen")
    qtbot.addWidget(popup)
    results = []

    def on_finished(code):
        results.append(code)

    popup.finished.connect(on_finished)
    popup.show()

    # Fast-forward: set countdown to 1 and trigger one tick
    popup._countdown = 1
    popup._tick()

    assert results == [SUGGESTION_YES]


def test_countdown_decrements(qtbot):
    popup = SuggestionPopup("Meetings", "Besprechungen")
    qtbot.addWidget(popup)
    popup.show()
    popup._tick()
    assert popup._countdown == 9
    assert "9" in popup._yes_btn.text()


def test_timer_stops_on_manual_close(qtbot):
    popup = SuggestionPopup("Meetings", "Besprechungen")
    qtbot.addWidget(popup)
    popup.show()
    assert popup._auto_timer.isActive()
    popup.done(SUGGESTION_YES)
    assert not popup._auto_timer.isActive()
```

- [x] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_suggestion_popup.py -v
```

Expected: FAIL — `AttributeError: 'SuggestionPopup' object has no attribute '_yes_btn'`

- [x] **Step 3: Rewrite `suggestion_popup.py` with countdown**

Replace the `SuggestionPopup` class (keep `MeetingCategoryDialog` unchanged):

```python
"""Popups for Outlook-driven suggestions and meeting category selection."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from workload_analyzer.models import Category

# Return codes from SuggestionPopup.exec()
SUGGESTION_YES = 1
SUGGESTION_NO = 2
SUGGESTION_NEVER = 3

_COUNTDOWN_SECONDS = 10


class SuggestionPopup(QDialog):
    """Popup asking whether to accept an Outlook category suggestion.

    Auto-closes after 10 seconds accepting the suggestion (SUGGESTION_YES).
    The "Ja" button shows a live countdown.
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
        self._yes_btn = QPushButton(f"Ja ({_COUNTDOWN_SECONDS})")
        no_btn = QPushButton("Nein")
        never_btn = QPushButton("Nie mehr")

        self._yes_btn.setDefault(True)
        self._yes_btn.clicked.connect(lambda: self.done(SUGGESTION_YES))
        no_btn.clicked.connect(lambda: self.done(SUGGESTION_NO))
        never_btn.clicked.connect(lambda: self.done(SUGGESTION_NEVER))

        btns.addWidget(self._yes_btn)
        btns.addWidget(no_btn)
        btns.addWidget(never_btn)
        layout.addLayout(btns)

        self._countdown = _COUNTDOWN_SECONDS
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(1000)
        self._auto_timer.timeout.connect(self._tick)
        self._auto_timer.start()

    def _tick(self) -> None:
        self._countdown -= 1
        self._yes_btn.setText(f"Ja ({self._countdown})")
        if self._countdown <= 0:
            self.done(SUGGESTION_YES)

    def done(self, result: int) -> None:
        self._auto_timer.stop()
        super().done(result)


class MeetingCategoryDialog(QDialog):
    """Blocking dialog asking which category to assign to a meeting with no Outlook category."""

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

- [x] **Step 4: Run suggestion popup tests**

```
python -m pytest tests/test_suggestion_popup.py -v
```

Expected: 4 passed

- [x] **Step 5: Update `app.py` — suppress popup for same/unmapped category**

In `app.py`, find `_on_category_detected` (around line 74). Add two suppression checks after the `cat is None` check:

Replace:
```python
    def _on_category_detected(outlook_name: str) -> None:
        from workload_analyzer.ui.suggestion_popup import (
            SuggestionPopup, SUGGESTION_YES, SUGGESTION_NO, SUGGESTION_NEVER,
        )
        cat = repo.find_category_by_outlook_name(outlook_name)
        if cat is None:
            return
        if repo.is_silenced(outlook_name, cat.id):
            return
```

With:
```python
    def _on_category_detected(outlook_name: str) -> None:
        from workload_analyzer.ui.suggestion_popup import (
            SuggestionPopup, SUGGESTION_YES, SUGGESTION_NO, SUGGESTION_NEVER,
        )
        cat = repo.find_category_by_outlook_name(outlook_name)
        if cat is None:
            return  # No mapping — suppress
        if cat.id == tracker.current_state().category_id:
            return  # Already on this category — suppress
        if repo.is_silenced(outlook_name, cat.id):
            return
```

- [x] **Step 6: Run full test suite**

```
python -m pytest --tb=short -q
```

Expected: 131 passed

- [x] **Step 7: Commit**

```bash
git add src/workload_analyzer/ui/suggestion_popup.py src/workload_analyzer/app.py tests/test_suggestion_popup.py
git commit -m "feat: suggestion popup auto-close (10s→Ja) + suppress same/unmapped category"
```

---

## Task 3: Import Dialog — UX

**Files:**
- Modify: `src/workload_analyzer/ui/import_outlook_dialog.py`

### Background

Current state of `ImportOutlookDialog._build_ui()`:
- Table with 4 columns: Outlook-Name, Farbe, Importieren, App-Kategorie
- `setEditTriggers(NoEditTriggers)` — already read-only
- No sorting, no select-all, no role-check on load

Add: `setSortingEnabled(True)` on column 0, "Alle auswählen" toggle button, disable OK + show warning when no roles.

- [x] **Step 1: Rewrite `_build_ui` in `ImportOutlookDialog`**

Replace the `_build_ui` method:

```python
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Wähle Outlook-Kategorien zum Importieren aus:"))
        self._select_all_btn = QPushButton("Alle auswählen")
        self._select_all_btn.clicked.connect(self._toggle_all)
        self._all_selected = False
        top_row.addWidget(self._select_all_btn)
        layout.addLayout(top_row)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Outlook-Name", "Farbe", "Importieren", "App-Kategorie"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(True)
        layout.addWidget(self._table)

        # Warning label — only visible when no roles exist
        self._no_role_label = QLabel("⚠ Bitte zuerst eine Rolle anlegen.")
        self._no_role_label.setStyleSheet("color: #cc6600;")
        self._no_role_label.setVisible(not self._roles)
        layout.addWidget(self._no_role_label)

        self._btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._btns.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self._roles))
        self._btns.accepted.connect(self._save)
        self._btns.rejected.connect(self.reject)
        layout.addWidget(self._btns)
```

- [x] **Step 2: Add `_toggle_all` method**

Add after `_build_ui`:

```python
    def _toggle_all(self) -> None:
        self._all_selected = not self._all_selected
        for row in range(self._table.rowCount()):
            cb_cell = self._table.cellWidget(row, 2)
            if cb_cell:
                cb = cb_cell.findChild(QCheckBox)
                if cb:
                    cb.setChecked(self._all_selected)
        self._select_all_btn.setText(
            "Alle abwählen" if self._all_selected else "Alle auswählen"
        )
```

- [x] **Step 3: Verify it compiles**

```
python -m py_compile src/workload_analyzer/ui/import_outlook_dialog.py
```

Expected: no output

- [x] **Step 4: Run full test suite**

```
python -m pytest --tb=short -q
```

Expected: 131 passed (no change — UI changes not unit-tested)

- [x] **Step 5: Commit**

```bash
git add src/workload_analyzer/ui/import_outlook_dialog.py
git commit -m "feat: import dialog — sortable, select-all, disable when no roles"
```

---

## Task 4: Kategorien-Editor — UX

**Files:**
- Modify: `src/workload_analyzer/ui/settings_window.py`

### Background

`_build_categories_tab` creates `self.cat_table` but does not set `NoEditTriggers` or `setSortingEnabled`. The `_CategoryDialog` already uses `QComboBox` for roles (line 337) — no change needed there.

Two lines to add in `_build_categories_tab` after creating `self.cat_table`.

- [x] **Step 1: Make cat_table read-only and sortable**

In `_build_categories_tab`, after these lines:
```python
        self.cat_table = QTableWidget(0, 5)
        self.cat_table.setHorizontalHeaderLabels(["Name", "Rolle", "Farbe", "Aktiv", "Outlook-Name"])
        self.cat_table.horizontalHeader().setStretchLastSection(True)
```

Add:
```python
        self.cat_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cat_table.setSortingEnabled(True)
```

- [x] **Step 2: Verify it compiles**

```
python -m py_compile src/workload_analyzer/ui/settings_window.py
```

Expected: no output

- [x] **Step 3: Run full test suite**

```
python -m pytest --tb=short -q
```

Expected: 131 passed

- [x] **Step 4: Commit**

```bash
git add src/workload_analyzer/ui/settings_window.py
git commit -m "feat: category table read-only and sortable in settings"
```

---

## Task 5: Floating Widget + Tray

**Files:**
- Modify: `src/workload_analyzer/ui/floating_widget.py`
- Modify: `src/workload_analyzer/ui/tray.py`
- Modify: `src/workload_analyzer/app.py`

### Background

**FloatingWidget changes:**
- Remove old `dot` + `label` row
- Add title bar (`_DragHandle` label + hide button) at top
- Add `_color_strip` widget (QWidget with background-color) containing category + role label
- Emit `widget_hidden` signal when hide button clicked
- Drag lives only on `_DragHandle`

**TrayIcon changes:**
- `_widget_action` text is dynamic: "Widget ausblenden" / "Widget anzeigen"
- `set_widget_visible(visible: bool)` method updates action text
- Double-click on tray icon emits `toggle_widget`

**app.py changes:**
- `toggle_widget()` connects `widget_hidden` signal and calls `tray.set_widget_visible()`

- [x] **Step 1: Rewrite `floating_widget.py`**

Replace the entire file:

```python
from typing import Optional

import time

from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QColor
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from workload_analyzer.core.tracker import TimeTracker, TrackerState
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource


class _DragHandle(QLabel):
    """A label that drags the parent FloatingWidget when clicked and moved."""

    def __init__(self, text: str, parent_widget: "FloatingWidget"):
        super().__init__(text)
        self._fw = parent_widget
        self._drag_pos: Optional[QPoint] = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._fw.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self._fw.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None
        self._fw._save_position()


class FloatingWidget(QWidget):
    widget_hidden = pyqtSignal()  # emitted when user clicks the hide button

    def __init__(self, repo: Repository, tracker: TimeTracker, parent: Optional[QWidget] = None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.repo = repo
        self.tracker = tracker
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet("QWidget { background: #222; color: #eee; border-radius: 6px; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 6)
        layout.setSpacing(3)

        # --- Title bar (drag area + hide button) ---
        title_bar = QWidget()
        title_bar.setStyleSheet("QWidget { background: #333; border-radius: 4px; }")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(6, 2, 4, 2)
        self._drag_handle = _DragHandle("≡ WorkloadAnalyzer", self)
        self._drag_handle.setStyleSheet("color: #aaa; font-size: 11px; background: transparent;")
        title_layout.addWidget(self._drag_handle, 1)
        hide_btn = QPushButton("✕")
        hide_btn.setFixedWidth(20)
        hide_btn.setFlat(True)
        hide_btn.setStyleSheet("color: #aaa; background: transparent; border: none;")
        hide_btn.clicked.connect(self._on_hide)
        title_layout.addWidget(hide_btn)
        layout.addWidget(title_bar)

        # --- Color strip (category + role name) ---
        self._color_strip = QWidget()
        self._color_strip.setStyleSheet("background-color: #444; border-radius: 4px;")
        strip_layout = QHBoxLayout(self._color_strip)
        strip_layout.setContentsMargins(6, 4, 6, 4)
        self._cat_label = QLabel("Not tracking")
        self._cat_label.setStyleSheet("font-weight: bold; background: transparent;")
        strip_layout.addWidget(self._cat_label, 1)
        layout.addWidget(self._color_strip)

        # --- Elapsed time ---
        self.elapsed = QLabel("00:00:00")
        self.elapsed.setStyleSheet("font-family: monospace; font-size: 14px;")
        layout.addWidget(self.elapsed)

        # --- Controls ---
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

    def _on_hide(self) -> None:
        self.hide()
        self.widget_hidden.emit()

    def _restore_position(self) -> None:
        x = self.repo.get_setting("floating_widget_x")
        y = self.repo.get_setting("floating_widget_y")
        if x is not None and y is not None:
            self.move(int(x), int(y))

    def _save_position(self) -> None:
        self.repo.set_setting("floating_widget_x", str(self.x()))
        self.repo.set_setting("floating_widget_y", str(self.y()))

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
            cat_color = cat.color if cat else "#444"
            cat_name = cat.name if cat else "?"
            role_name = role.name if role else ""
            self._cat_label.setText(f"{cat_name}  ·  {role_name}")
            self._color_strip.setStyleSheet(
                f"background-color: {cat_color}; border-radius: 4px;"
            )
            elapsed = int(time.time()) - (state.started_at or int(time.time()))
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            self.elapsed.setText(f"{h:02d}:{m:02d}:{s:02d}")
            self.pause_btn.setText("⏸")
        elif state.kind == TrackerState.Kind.PAUSED:
            self._cat_label.setText("Paused")
            self._color_strip.setStyleSheet("background-color: #555; border-radius: 4px;")
            self.elapsed.setText("--:--:--")
            self.pause_btn.setText("▶")
        else:
            self._cat_label.setText("Not tracking")
            self._color_strip.setStyleSheet("background-color: #444; border-radius: 4px;")
            self.elapsed.setText("00:00:00")
            self.pause_btn.setText("⏸")
```

- [x] **Step 2: Update `tray.py`**

In `TrayIcon.__init__`, after `self.icon.show()`, add:

```python
        self.icon.activated.connect(self._on_tray_activated)
        self._widget_visible: bool = True
```

In `_build_menu`, replace:
```python
        widget_action = QAction("Toggle floating widget", self.menu)
        widget_action.triggered.connect(self.toggle_widget.emit)
        self.menu.addAction(widget_action)
```

With:
```python
        self._widget_action = QAction("Widget ausblenden", self.menu)
        self._widget_action.triggered.connect(self.toggle_widget.emit)
        self.menu.addAction(self._widget_action)
```

Add these two methods to `TrayIcon`:

```python
    def set_widget_visible(self, visible: bool) -> None:
        """Update menu label to reflect floating widget visibility."""
        self._widget_visible = visible
        self._widget_action.setText(
            "Widget ausblenden" if visible else "Widget anzeigen"
        )

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_widget.emit()
```

- [x] **Step 3: Update `app.py` — wire widget_hidden + tray visibility**

Replace the `toggle_widget` function in `app.py`:

```python
    def toggle_widget():
        nonlocal floating_widget
        from workload_analyzer.ui.floating_widget import FloatingWidget
        if floating_widget is None:
            floating_widget = FloatingWidget(repo=repo, tracker=tracker)
            floating_widget.widget_hidden.connect(
                lambda: tray.set_widget_visible(False)
            )
            floating_widget.show()
            tray.set_widget_visible(True)
        elif floating_widget.isVisible():
            floating_widget.hide()
            tray.set_widget_visible(False)
        else:
            floating_widget.show()
            tray.set_widget_visible(True)
```

- [x] **Step 4: Verify all three files compile**

```
python -m py_compile src/workload_analyzer/ui/floating_widget.py src/workload_analyzer/ui/tray.py src/workload_analyzer/app.py
```

Expected: no output

- [x] **Step 5: Run full test suite**

```
python -m pytest --tb=short -q
```

Expected: 131 passed

- [x] **Step 6: Commit**

```bash
git add src/workload_analyzer/ui/floating_widget.py src/workload_analyzer/ui/tray.py src/workload_analyzer/app.py
git commit -m "feat: floating widget drag-fix, color strip, hide button; tray double-click + dynamic label"
```

---

## Done

After Task 5, Phase 6 is complete. Update `STATUS.md`:
- Mark Phase 6 as done in the "Fertig" table
- Update test count
- Remove Phase 6 from "Vorgeschlagene nächste Phasen"
