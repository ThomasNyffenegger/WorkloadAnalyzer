# System Monitoring (Phase 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect screen lock/unlock and idle events on Windows, stop tracking on absence, and show a recovery popup letting the user back-fill, rebook, or discard the absent time.

**Architecture:** `SystemMonitor(QObject + QAbstractNativeEventFilter)` catches `WM_WTSSESSION_CHANGE` for screen lock events and polls `GetLastInputInfo` via `QTimer` for idle detection. Both absence types feed the same `RecoveryPopup` dialog (3 options: previous category / other category / discard). `tracker.stop_at(ts)` cleanly ends the open entry at the moment of absence.

**Tech Stack:** Python 3.11+, PyQt6, ctypes (Windows WTS API + GetLastInputInfo), SQLite via existing Repository/TimeTracker, pytest.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/workload_analyzer/core/tracker.py` | Modify | Add `stop_at(ts)` method |
| `src/workload_analyzer/services/system_monitor.py` | Create | WTS screen-lock events + idle polling |
| `src/workload_analyzer/ui/recovery_popup.py` | Create | Three-option recovery dialog |
| `src/workload_analyzer/ui/settings_window.py` | Modify | Add idle threshold spinner to General tab; accept `system_monitor` param |
| `src/workload_analyzer/app.py` | Modify | Wire SystemMonitor signals → recovery flow |
| `tests/test_tracker_stop_at.py` | Create | Unit tests for `stop_at` |
| `tests/test_system_monitor.py` | Create | Unit tests for SystemMonitor (no real Windows API) |
| `tests/test_recovery_popup.py` | Create | Unit tests for RecoveryPopup dialog |
| `tests/test_smoke.py` | Modify | Add recovery smoke test |

---

## Task 1: `tracker.stop_at(ts)` — stop tracking at a given timestamp

**Files:**
- Modify: `src/workload_analyzer/core/tracker.py`
- Create: `tests/test_tracker_stop_at.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tracker_stop_at.py`:

```python
"""Tests for TimeTracker.stop_at()."""
import pytest
from workload_analyzer.core.tracker import TimeTracker, TrackerState
from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource


def make_tracker(tmp_db_path):
    conn = connect(tmp_db_path)
    repo = Repository(conn)
    role_id = repo.create_role("Dev")
    cat_id = repo.create_category("Coding", "#ff0000", role_id)
    ts = [1_000_000]
    tracker = TimeTracker(repo=repo, clock=lambda: ts[0])
    return tracker, repo, cat_id, ts


def test_stop_at_returns_category_id(tmp_db_path):
    tracker, repo, cat_id, ts = make_tracker(tmp_db_path)
    tracker.start(cat_id, EntrySource.MANUAL)
    ts[0] = 1_000_600  # 10 minutes later
    result = tracker.stop_at(1_000_600)
    assert result == cat_id


def test_stop_at_closes_entry_at_given_timestamp(tmp_db_path):
    tracker, repo, cat_id, ts = make_tracker(tmp_db_path)
    tracker.start(cat_id, EntrySource.MANUAL)
    tracker.stop_at(1_000_600)
    entry = repo.list_entries_between(0, 9_999_999_999)[0]
    assert entry.end_ts == 1_000_600


def test_stop_at_transitions_to_paused(tmp_db_path):
    tracker, repo, cat_id, ts = make_tracker(tmp_db_path)
    tracker.start(cat_id, EntrySource.MANUAL)
    tracker.stop_at(1_000_600)
    assert tracker.current_state().kind == TrackerState.Kind.PAUSED


def test_stop_at_preserves_last_category_id(tmp_db_path):
    tracker, repo, cat_id, ts = make_tracker(tmp_db_path)
    tracker.start(cat_id, EntrySource.MANUAL)
    tracker.stop_at(1_000_600)
    assert tracker._last_category_id == cat_id


def test_stop_at_returns_none_when_not_tracking(tmp_db_path):
    tracker, repo, cat_id, ts = make_tracker(tmp_db_path)
    result = tracker.stop_at(1_000_600)
    assert result is None


def test_stop_at_leaves_no_open_entry(tmp_db_path):
    tracker, repo, cat_id, ts = make_tracker(tmp_db_path)
    tracker.start(cat_id, EntrySource.MANUAL)
    tracker.stop_at(1_000_600)
    assert repo.get_open_entry() is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_tracker_stop_at.py -v
```

Expected: FAIL — `AttributeError: 'TimeTracker' object has no attribute 'stop_at'`

- [ ] **Step 3: Implement `stop_at` in tracker.py**

Add after the `pause` method in `src/workload_analyzer/core/tracker.py`:

```python
    def stop_at(self, ts: int) -> Optional[int]:
        """Stop the running entry at the given timestamp.

        Returns the category_id of the stopped entry, or None if not tracking.
        Transitions tracker to PAUSED state.
        """
        if self._state.kind != TrackerState.Kind.TRACKING:
            return None
        open_entry = self.repo.get_open_entry()
        if open_entry is not None:
            self.repo.close_entry(open_entry.id, end_ts=ts)
        prev_cat = self._state.category_id
        self._last_category_id = prev_cat
        self._state = TrackerState(
            kind=TrackerState.Kind.PAUSED,
            category_id=None,
            started_at=None,
        )
        return prev_cat
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_tracker_stop_at.py -v
```

Expected: 6 passed

- [ ] **Step 5: Run full test suite to confirm no regressions**

```
python -m pytest --tb=short -q
```

Expected: all existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add src/workload_analyzer/core/tracker.py tests/test_tracker_stop_at.py
git commit -m "feat: add TimeTracker.stop_at() for absence detection"
```

---

## Task 2: `SystemMonitor` — screen lock detection

**Files:**
- Create: `src/workload_analyzer/services/system_monitor.py`
- Create: `tests/test_system_monitor.py` (screen-lock tests only)

- [ ] **Step 1: Write failing tests for screen-lock detection**

Create `tests/test_system_monitor.py`:

```python
"""Tests for SystemMonitor — screen lock and idle detection.

All tests bypass real Windows APIs via injectable dependencies.
WTS events are simulated by calling _handle_wts_event() directly.
Idle state is controlled via fake_get_last_input_fn.
"""
import pytest
from workload_analyzer.services.system_monitor import SystemMonitor

WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8


def make_monitor(idle_threshold_seconds=600):
    """Return a SystemMonitor with all Windows APIs replaced by fakes."""
    ts = [1_000_000]
    fake_idle_ms = [0]

    mon = SystemMonitor(
        wts_register_fn=lambda hwnd, flags: None,
        wts_unregister_fn=lambda hwnd: None,
        get_last_input_fn=lambda: fake_idle_ms[0],
        clock=lambda: ts[0],
        idle_threshold_seconds=idle_threshold_seconds,
    )
    mon._ts = ts
    mon._fake_idle_ms = fake_idle_ms
    return mon


def fire_lock(mon):
    mon._ts[0] += 1
    mon._handle_wts_event(WTS_SESSION_LOCK)


def fire_unlock(mon):
    mon._ts[0] += 1
    mon._handle_wts_event(WTS_SESSION_UNLOCK)


# --- Screen lock tests ---

def test_lock_emits_session_locked():
    mon = make_monitor()
    results = []
    mon.session_locked.connect(lambda ts: results.append(ts))
    mon._ts[0] = 1_000_100
    fire_lock(mon)
    assert results == [1_000_101]
    assert mon._locked is True


def test_unlock_emits_session_unlocked():
    mon = make_monitor()
    results = []
    mon.session_unlocked.connect(lambda lock, unlock: results.append((lock, unlock)))
    mon._ts[0] = 1_000_100
    fire_lock(mon)
    lock_ts = mon._lock_ts
    mon._ts[0] = 1_000_700
    fire_unlock(mon)
    assert len(results) == 1
    lock_emitted, unlock_emitted = results[0]
    assert lock_emitted == lock_ts
    assert unlock_emitted > lock_emitted
    assert mon._locked is False


def test_double_lock_ignored():
    mon = make_monitor()
    results = []
    mon.session_locked.connect(lambda ts: results.append(ts))
    fire_lock(mon)
    fire_lock(mon)  # second lock while already locked — ignored
    assert len(results) == 1


def test_unlock_without_prior_lock_ignored():
    mon = make_monitor()
    results = []
    mon.session_unlocked.connect(lambda l, u: results.append((l, u)))
    fire_unlock(mon)  # no prior lock
    assert results == []


def test_lock_ts_stored_correctly():
    mon = make_monitor()
    mon._ts[0] = 5_000_000
    fire_lock(mon)
    assert mon._lock_ts == 5_000_001
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_system_monitor.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'workload_analyzer.services.system_monitor'`

- [ ] **Step 3: Create `system_monitor.py` with screen-lock detection**

Create `src/workload_analyzer/services/system_monitor.py`:

```python
"""System monitor — detects screen lock/unlock and idle via Windows APIs."""
from __future__ import annotations

import ctypes
import ctypes.wintypes
from typing import Callable, Optional

from PyQt6.QtCore import QAbstractNativeEventFilter, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

# Windows constants
WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
NOTIFY_FOR_THIS_SESSION = 0


class _MSG(ctypes.Structure):
    """Win32 MSG structure layout (64-bit)."""
    _fields_ = [
        ("hwnd",    ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam",  ctypes.c_size_t),
        ("lParam",  ctypes.c_size_t),
        ("time",    ctypes.c_ulong),
        ("ptX",     ctypes.c_long),
        ("ptY",     ctypes.c_long),
    ]


class SystemMonitor(QObject, QAbstractNativeEventFilter):
    """Detects Windows screen-lock and idle events.

    All Windows API calls are injectable for testing.

    Signals
    -------
    session_locked(lock_ts)           — emitted when screen is locked
    session_unlocked(lock_ts, unlock_ts) — emitted when screen is unlocked
    idle_started(idle_begin_ts)       — emitted when idle threshold exceeded
    user_returned(idle_start_ts, return_ts) — emitted when activity resumes after idle
    """

    session_locked   = pyqtSignal(int)       # lock_ts
    session_unlocked = pyqtSignal(int, int)  # lock_ts, unlock_ts
    idle_started     = pyqtSignal(int)       # idle_begin_ts
    user_returned    = pyqtSignal(int, int)  # idle_start_ts, return_ts

    def __init__(
        self,
        wts_register_fn: Optional[Callable] = None,
        wts_unregister_fn: Optional[Callable] = None,
        get_last_input_fn: Optional[Callable[[], int]] = None,
        clock: Optional[Callable[[], int]] = None,
        idle_threshold_seconds: int = 600,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)

        self._wts_register = wts_register_fn or self._default_register
        self._wts_unregister = wts_unregister_fn or self._default_unregister
        self._get_last_input = get_last_input_fn or self._default_get_last_input
        self._clock = clock or (lambda: int(__import__("time").time()))

        self._idle_threshold_ms = idle_threshold_seconds * 1000

        # Internal state
        self._locked: bool = False
        self._idle: bool = False
        self._lock_ts: Optional[int] = None
        self._idle_start_ts: Optional[int] = None

        self._idle_timer = QTimer(self)
        self._idle_timer.timeout.connect(self._poll_idle)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Register for WTS notifications and start idle polling."""
        app = QApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self)
        hwnd = self._get_hwnd()
        if hwnd:
            self._wts_register(hwnd, NOTIFY_FOR_THIS_SESSION)
        self._idle_timer.start(30_000)

    def stop(self) -> None:
        """Unregister WTS notifications and stop idle polling."""
        self._idle_timer.stop()
        app = QApplication.instance()
        if app is not None:
            app.removeNativeEventFilter(self)
        hwnd = self._get_hwnd()
        if hwnd:
            self._wts_unregister(hwnd)

    def set_idle_threshold(self, seconds: int) -> None:
        """Change the idle threshold. Effective on next poll cycle."""
        self._idle_threshold_ms = seconds * 1000

    # ------------------------------------------------------------------
    # QAbstractNativeEventFilter
    # ------------------------------------------------------------------

    def nativeEventFilter(self, event_type: bytes, message) -> tuple[bool, int]:
        try:
            msg = _MSG.from_address(int(message))
            if msg.message == WM_WTSSESSION_CHANGE:
                self._handle_wts_event(msg.wParam)
        except Exception:
            pass
        return False, 0  # never consume the event

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _handle_wts_event(self, w_param: int) -> None:
        now = self._clock()
        if w_param == WTS_SESSION_LOCK and not self._locked:
            self._locked = True
            self._lock_ts = now
            # If idle was active, lock takes over — clear idle silently
            if self._idle:
                self._idle = False
                self._idle_start_ts = None
            self.session_locked.emit(now)

        elif w_param == WTS_SESSION_UNLOCK and self._locked:
            self._locked = False
            lock_ts = self._lock_ts or now
            self._lock_ts = None
            self.session_unlocked.emit(lock_ts, now)

    def _poll_idle(self) -> None:
        """Poll GetLastInputInfo and emit idle/return signals as needed."""
        if self._locked:
            return  # lock takes precedence
        idle_ms = self._get_last_input()
        now = self._clock()

        if not self._idle and idle_ms >= self._idle_threshold_ms:
            self._idle = True
            self._idle_start_ts = now - idle_ms // 1000
            self.idle_started.emit(self._idle_start_ts)

        elif self._idle and idle_ms < self._idle_threshold_ms:
            self._idle = False
            idle_start = self._idle_start_ts or now
            self._idle_start_ts = None
            self.user_returned.emit(idle_start, now)

    @staticmethod
    def _get_hwnd() -> Optional[int]:
        app = QApplication.instance()
        if app is None:
            return None
        for widget in app.topLevelWidgets():
            hwnd = int(widget.winId())
            if hwnd:
                return hwnd
        return None

    @staticmethod
    def _default_register(hwnd: int, flags: int) -> None:
        ctypes.windll.wtsapi32.WTSRegisterSessionNotification(hwnd, flags)  # type: ignore[attr-defined]

    @staticmethod
    def _default_unregister(hwnd: int) -> None:
        ctypes.windll.wtsapi32.WTSUnRegisterSessionNotification(hwnd)  # type: ignore[attr-defined]

    @staticmethod
    def _default_get_last_input() -> int:
        """Return milliseconds since last user input."""
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(lii)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))  # type: ignore[attr-defined]
        elapsed_ms = ctypes.windll.kernel32.GetTickCount() - lii.dwTime  # type: ignore[attr-defined]
        return int(elapsed_ms)
```

- [ ] **Step 4: Run screen-lock tests**

```
python -m pytest tests/test_system_monitor.py -v -k "lock"
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/workload_analyzer/services/system_monitor.py tests/test_system_monitor.py
git commit -m "feat: add SystemMonitor with screen-lock detection via WTS native events"
```

---

## Task 3: `SystemMonitor` — idle detection tests

**Files:**
- Modify: `tests/test_system_monitor.py`

- [ ] **Step 1: Append idle detection tests to `tests/test_system_monitor.py`**

Add these test functions at the end of the file:

```python
# --- Idle detection tests ---

def test_idle_started_when_threshold_exceeded():
    mon = make_monitor(idle_threshold_seconds=600)
    results = []
    mon.idle_started.connect(lambda ts: results.append(ts))
    mon._fake_idle_ms[0] = 600_001  # just over 10 minutes
    mon._ts[0] = 1_000_700
    mon._poll_idle()
    assert len(results) == 1
    assert mon._idle is True


def test_idle_not_started_below_threshold():
    mon = make_monitor(idle_threshold_seconds=600)
    results = []
    mon.idle_started.connect(lambda ts: results.append(ts))
    mon._fake_idle_ms[0] = 599_999  # just under threshold
    mon._poll_idle()
    assert results == []
    assert mon._idle is False


def test_user_returned_after_idle():
    mon = make_monitor(idle_threshold_seconds=600)
    results = []
    mon.user_returned.connect(lambda s, e: results.append((s, e)))
    mon._fake_idle_ms[0] = 600_001
    mon._ts[0] = 1_000_700
    mon._poll_idle()   # becomes idle
    assert mon._idle is True
    mon._fake_idle_ms[0] = 0  # user moved mouse
    mon._ts[0] = 1_001_000
    mon._poll_idle()   # user returned
    assert len(results) == 1
    idle_start, return_ts = results[0]
    assert return_ts == 1_001_000
    assert mon._idle is False


def test_idle_suppressed_when_locked():
    mon = make_monitor(idle_threshold_seconds=600)
    results = []
    mon.idle_started.connect(lambda ts: results.append(ts))
    fire_lock(mon)
    mon._fake_idle_ms[0] = 600_001
    mon._poll_idle()
    assert results == []  # suppressed because locked


def test_lock_clears_idle_state():
    mon = make_monitor(idle_threshold_seconds=600)
    mon._fake_idle_ms[0] = 600_001
    mon._ts[0] = 1_000_700
    mon._poll_idle()
    assert mon._idle is True
    fire_lock(mon)   # lock fires while idle
    assert mon._idle is False


def test_set_idle_threshold_takes_effect():
    mon = make_monitor(idle_threshold_seconds=600)
    results = []
    mon.idle_started.connect(lambda ts: results.append(ts))
    mon.set_idle_threshold(300)  # change to 5 minutes
    mon._fake_idle_ms[0] = 300_001
    mon._poll_idle()
    assert len(results) == 1


def test_idle_start_ts_is_approximated_from_idle_duration():
    mon = make_monitor(idle_threshold_seconds=600)
    results = []
    mon.idle_started.connect(lambda ts: results.append(ts))
    mon._ts[0] = 1_001_000
    mon._fake_idle_ms[0] = 700_000  # 700 seconds of idle → started ~700s ago
    mon._poll_idle()
    assert results[0] == 1_001_000 - 700  # idle_start_ts = now - idle_seconds
```

- [ ] **Step 2: Run all system monitor tests**

```
python -m pytest tests/test_system_monitor.py -v
```

Expected: 12 passed

- [ ] **Step 3: Commit**

```bash
git add tests/test_system_monitor.py
git commit -m "test: add idle detection tests for SystemMonitor"
```

---

## Task 4: `RecoveryPopup` dialog

**Files:**
- Create: `src/workload_analyzer/ui/recovery_popup.py`
- Create: `tests/test_recovery_popup.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_recovery_popup.py`:

```python
"""Tests for RecoveryPopup dialog."""
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from workload_analyzer.models import Category
from workload_analyzer.ui.recovery_popup import (
    RecoveryPopup, RECOVERY_PREVIOUS, RECOVERY_OTHER, RECOVERY_DISCARD,
)


def make_cats():
    role_id = 1
    return [
        Category(id=10, name="Projektarbeit", color="#ff0000", role_id=role_id),
        Category(id=11, name="Meetings", color="#00ff00", role_id=role_id),
    ]


def make_prev_cat():
    return Category(id=10, name="Projektarbeit", color="#ff0000", role_id=1)


def test_popup_constructs_with_previous_category(qtbot):
    popup = RecoveryPopup(
        absent_seconds=600,
        reason="Bildschirm gesperrt",
        previous_category=make_prev_cat(),
        all_categories=make_cats(),
    )
    qtbot.addWidget(popup)
    assert popup is not None


def test_popup_constructs_without_previous_category(qtbot):
    popup = RecoveryPopup(
        absent_seconds=600,
        reason="Inaktivität",
        previous_category=None,
        all_categories=make_cats(),
    )
    qtbot.addWidget(popup)
    # No "Vorherige" radio — discard should be pre-selected
    assert popup._radio_prev is None


def test_recovery_previous_returns_correct_code(qtbot):
    popup = RecoveryPopup(
        absent_seconds=600,
        reason="Bildschirm gesperrt",
        previous_category=make_prev_cat(),
        all_categories=make_cats(),
    )
    qtbot.addWidget(popup)
    popup._radio_prev.setChecked(True)
    popup._on_confirm()
    assert popup.result() == RECOVERY_PREVIOUS


def test_recovery_discard_returns_correct_code(qtbot):
    popup = RecoveryPopup(
        absent_seconds=600,
        reason="Bildschirm gesperrt",
        previous_category=make_prev_cat(),
        all_categories=make_cats(),
    )
    qtbot.addWidget(popup)
    popup._radio_discard.setChecked(True)
    popup._on_confirm()
    assert popup.result() == RECOVERY_DISCARD


def test_recovery_other_returns_correct_code(qtbot):
    popup = RecoveryPopup(
        absent_seconds=600,
        reason="Bildschirm gesperrt",
        previous_category=make_prev_cat(),
        all_categories=make_cats(),
    )
    qtbot.addWidget(popup)
    popup._radio_other.setChecked(True)
    popup._on_confirm()
    assert popup.result() == RECOVERY_OTHER


def test_selected_category_id_returns_combo_value(qtbot):
    cats = make_cats()
    popup = RecoveryPopup(
        absent_seconds=600,
        reason="Bildschirm gesperrt",
        previous_category=make_prev_cat(),
        all_categories=cats,
    )
    qtbot.addWidget(popup)
    popup._other_combo.setCurrentIndex(1)  # select "Meetings" (id=11)
    assert popup.selected_category_id() == 11


def test_long_absence_preselects_discard(qtbot):
    popup = RecoveryPopup(
        absent_seconds=9 * 3600,  # 9 hours
        reason="Bildschirm gesperrt",
        previous_category=make_prev_cat(),
        all_categories=make_cats(),
    )
    qtbot.addWidget(popup)
    assert popup._radio_discard.isChecked()


def test_no_previous_category_preselects_discard(qtbot):
    popup = RecoveryPopup(
        absent_seconds=300,
        reason="Inaktivität",
        previous_category=None,
        all_categories=make_cats(),
    )
    qtbot.addWidget(popup)
    assert popup._radio_discard.isChecked()
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_recovery_popup.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'workload_analyzer.ui.recovery_popup'`

- [ ] **Step 3: Create `recovery_popup.py`**

Create `src/workload_analyzer/ui/recovery_popup.py`:

```python
"""Recovery popup shown after screen lock or idle absence."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QHBoxLayout, QLabel,
    QPushButton, QRadioButton, QVBoxLayout,
)

from workload_analyzer.models import Category

# Return codes from RecoveryPopup.exec()
RECOVERY_PREVIOUS = 1
RECOVERY_OTHER    = 2
RECOVERY_DISCARD  = 3


class RecoveryPopup(QDialog):
    """Asks the user what to do with absent time after screen lock or idle.

    Stays open until user clicks "Bestätigen" (no X-button close, no auto-close).

    Parameters
    ----------
    absent_seconds:
        Total time the user was absent.
    reason:
        Human-readable cause, e.g. "Bildschirm gesperrt" or "Inaktivität".
    previous_category:
        The category that was active before absence, or None if tracker was idle.
    all_categories:
        All active categories for the "other" picker.
    """

    def __init__(
        self,
        absent_seconds: int,
        reason: str,
        previous_category: Optional[Category],
        all_categories: list[Category],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Abwesenheit erkannt")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
        )
        self.setMinimumWidth(420)

        self._other_combo: Optional[QComboBox] = None
        self._radio_prev: Optional[QRadioButton] = None

        layout = QVBoxLayout(self)

        # Header label
        minutes = max(1, absent_seconds // 60)
        label = QLabel(
            f"Du warst <b>{minutes} Minuten</b> abwesend ({reason}).<br>"
            "Was möchtest du mit dieser Zeit machen?"
        )
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        layout.addWidget(label)

        # Warning for very long absences (>= 8 h)
        long_absence = absent_seconds >= 8 * 3600
        if long_absence:
            warn = QLabel("<i>⚠ Sehr lange Abwesenheit — Verwerfen empfohlen.</i>")
            warn.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(warn)

        self._group = QButtonGroup(self)

        # Option A: previous category (hidden when previous_category is None)
        if previous_category is not None:
            self._radio_prev = QRadioButton(
                f"Auf vorherige Kategorie buchen  ({previous_category.name})"
            )
            self._radio_prev.setChecked(not long_absence)
            self._group.addButton(self._radio_prev, RECOVERY_PREVIOUS)
            layout.addWidget(self._radio_prev)

        # Option B: other category
        other_row = QHBoxLayout()
        self._radio_other = QRadioButton("Andere Kategorie wählen")
        self._group.addButton(self._radio_other, RECOVERY_OTHER)
        other_row.addWidget(self._radio_other)
        self._other_combo = QComboBox()
        for cat in all_categories:
            self._other_combo.addItem(cat.name, userData=cat.id)
        other_row.addWidget(self._other_combo, 1)
        layout.addLayout(other_row)

        # Option C: discard
        self._radio_discard = QRadioButton("Verwerfen (Zeit nicht buchen)")
        if long_absence or previous_category is None:
            self._radio_discard.setChecked(True)
        self._group.addButton(self._radio_discard, RECOVERY_DISCARD)
        layout.addWidget(self._radio_discard)

        # Confirm button — only way to close
        confirm = QPushButton("Bestätigen")
        confirm.setDefault(True)
        confirm.clicked.connect(self._on_confirm)
        layout.addWidget(confirm)

    def _on_confirm(self) -> None:
        choice = self._group.checkedId()
        if choice == -1:
            choice = RECOVERY_DISCARD
        self.done(choice)

    def selected_category_id(self) -> Optional[int]:
        """Return the chosen 'other' category id. Meaningful only when result == RECOVERY_OTHER."""
        if self._other_combo is None:
            return None
        return self._other_combo.currentData()
```

- [ ] **Step 4: Run tests**

```
python -m pytest tests/test_recovery_popup.py -v
```

Expected: 8 passed

- [ ] **Step 5: Run full test suite**

```
python -m pytest --tb=short -q
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add src/workload_analyzer/ui/recovery_popup.py tests/test_recovery_popup.py
git commit -m "feat: add RecoveryPopup dialog with previous/other/discard options"
```

---

## Task 5: Settings — idle threshold

**Files:**
- Modify: `src/workload_analyzer/ui/settings_window.py`

- [ ] **Step 1: Add `system_monitor` parameter and idle threshold spinner**

In `src/workload_analyzer/ui/settings_window.py`, make these changes:

**1a. Update `__init__` signature** (add `system_monitor=None`):

```python
    def __init__(self, repo: Repository, monitor=None, system_monitor=None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.repo = repo
        self._monitor = monitor          # Optional[OutlookMonitor]
        self._system_monitor = system_monitor  # Optional[SystemMonitor]
        self.setWindowTitle("WorkloadAnalyzer — Einstellungen")
        self.resize(720, 520)
```

**1b. Replace the body of `_build_general_tab`** with:

```python
    def _build_general_tab(self) -> QWidget:
        w = QWidget(self)
        form = QFormLayout(w)

        # Rounding
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

        # Idle threshold
        self._idle_spin = QSpinBox()
        self._idle_spin.setRange(5, 60)
        self._idle_spin.setSuffix(" Min")
        current_idle = int(self.repo.get_setting("idle_threshold_minutes", "10") or "10")
        self._idle_spin.setValue(current_idle)
        self._idle_spin.valueChanged.connect(self._save_idle_threshold)
        form.addRow("Idle-Schwellwert:", self._idle_spin)

        return w
```

**1c. Add `_save_idle_threshold` method** after `_save_rounding`:

```python
    def _save_idle_threshold(self, value: int) -> None:
        self.repo.set_setting("idle_threshold_minutes", str(value))
        if self._system_monitor is not None:
            self._system_monitor.set_idle_threshold(value * 60)
```

- [ ] **Step 2: Verify the settings window still builds**

```
python -m py_compile src/workload_analyzer/ui/settings_window.py
```

Expected: no output (success)

- [ ] **Step 3: Run full test suite**

```
python -m pytest --tb=short -q
```

Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add src/workload_analyzer/ui/settings_window.py
git commit -m "feat: add idle threshold setting to Settings General tab"
```

---

## Task 6: Wire SystemMonitor in `app.py`

**Files:**
- Modify: `src/workload_analyzer/app.py`

- [ ] **Step 1: Add SystemMonitor import and setup after OutlookMonitor block**

Open `src/workload_analyzer/app.py`. After the OutlookMonitor block (after `monitor.start(poll_seconds)`), add the following SystemMonitor wiring. Also update the `open_settings` function and `_quit` function.

Replace the full `run()` function body with the version below (changes highlighted in comments):

```python
def run() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    conn = connect(db_path())
    repo = Repository(conn)
    tracker = TimeTracker(repo=repo, clock=lambda: int(time.time()))
    tracker.load_state()

    # First-run: if there are no categories, force settings.
    if not repo.list_categories(active_only=True):
        from workload_analyzer.ui.settings_window import SettingsWindow
        win = SettingsWindow(repo)
        win.exec()

    cats = repo.list_categories(active_only=True)
    if not cats:
        return 0

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
    _active_popup = [None]

    def _on_category_detected(outlook_name: str) -> None:
        from workload_analyzer.ui.suggestion_popup import (
            SuggestionPopup, SUGGESTION_YES, SUGGESTION_NO, SUGGESTION_NEVER,
        )
        cat = repo.find_category_by_outlook_name(outlook_name)
        if cat is None:
            return
        if repo.is_silenced(outlook_name, cat.id):
            return
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
        dlg = MeetingCategoryDialog(title, active_cats)
        if dlg.exec():
            cat_id = dlg.selected_category_id()
            if cat_id is not None:
                tracker.switch_to(cat_id, EntrySource.AUTO_MEETING)

    def _on_meeting_ended() -> None:
        pass

    monitor.category_detected.connect(_on_category_detected)
    monitor.meeting_started.connect(_on_meeting_started)
    monitor.meeting_ended.connect(_on_meeting_ended)
    monitor.availability_changed.connect(tray.set_outlook_available)
    monitor.start(poll_seconds)

    # ------------------------------------------------------------------
    # System Monitor (screen lock + idle)
    # ------------------------------------------------------------------
    from workload_analyzer.services.system_monitor import SystemMonitor
    from workload_analyzer.ui.recovery_popup import (
        RecoveryPopup, RECOVERY_PREVIOUS, RECOVERY_OTHER, RECOVERY_DISCARD,
    )

    idle_threshold_minutes = int(
        repo.get_setting("idle_threshold_minutes", "10") or "10"
    )
    sys_monitor = SystemMonitor(idle_threshold_seconds=idle_threshold_minutes * 60)

    # Absence state shared between on_absence_started and on_return handlers
    _absence = [None]  # Optional[(absence_start_ts: int, prev_cat_id: Optional[int])]

    def _on_absence_started(absence_start_ts: int) -> None:
        prev_cat_id = tracker.stop_at(absence_start_ts)
        _absence[0] = (absence_start_ts, prev_cat_id)

    def _show_recovery(absence_end_ts: int, reason: str, source: "EntrySource") -> None:
        info = _absence[0]
        if info is None:
            return
        _absence[0] = None
        absence_start_ts, prev_cat_id = info
        absent_seconds = absence_end_ts - absence_start_ts

        active_cats = repo.list_categories(active_only=True)
        prev_cat = next((c for c in active_cats if c.id == prev_cat_id), None)

        popup = RecoveryPopup(absent_seconds, reason, prev_cat, active_cats)
        result = popup.exec()

        if result == RECOVERY_PREVIOUS and prev_cat_id is not None:
            try:
                repo.insert_closed_entry(prev_cat_id, absence_start_ts, absence_end_ts, source)
            except Exception:
                pass  # overlap guard — don't crash if DB has unexpected state
            tracker.start(prev_cat_id, EntrySource.MANUAL)

        elif result == RECOVERY_OTHER:
            chosen_id = popup.selected_category_id()
            if chosen_id is not None:
                try:
                    repo.insert_closed_entry(chosen_id, absence_start_ts, absence_end_ts, source)
                except Exception:
                    pass
                tracker.start(chosen_id, EntrySource.MANUAL)

        else:  # RECOVERY_DISCARD (or no previous category)
            if prev_cat_id is not None:
                tracker.start(prev_cat_id, EntrySource.MANUAL)

        tray.refresh()

    def _on_session_locked(lock_ts: int) -> None:
        _on_absence_started(lock_ts)

    def _on_session_unlocked(lock_ts: int, unlock_ts: int) -> None:
        _show_recovery(unlock_ts, "Bildschirm gesperrt", EntrySource.SCREEN_LOCK_RECOVERY)

    def _on_idle_started(idle_start_ts: int) -> None:
        _on_absence_started(idle_start_ts)

    def _on_user_returned(idle_start_ts: int, return_ts: int) -> None:
        _show_recovery(return_ts, "Inaktivität", EntrySource.IDLE_RECOVERY)

    sys_monitor.session_locked.connect(_on_session_locked)
    sys_monitor.session_unlocked.connect(_on_session_unlocked)
    sys_monitor.idle_started.connect(_on_idle_started)
    sys_monitor.user_returned.connect(_on_user_returned)
    sys_monitor.start()

    # ------------------------------------------------------------------
    # Settings / Reports / Widget
    # ------------------------------------------------------------------
    def open_settings():
        from workload_analyzer.ui.settings_window import SettingsWindow
        win = SettingsWindow(repo, monitor=monitor, system_monitor=sys_monitor)
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
        sys_monitor.stop()
        monitor.stop()
        app.quit()

    tray.quit_requested.connect(_quit)

    return app.exec()
```

- [ ] **Step 2: Verify `app.py` compiles**

```
python -m py_compile src/workload_analyzer/app.py
```

Expected: no output

- [ ] **Step 3: Run full test suite**

```
python -m pytest --tb=short -q
```

Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add src/workload_analyzer/app.py
git commit -m "feat: wire SystemMonitor into app — screen lock and idle recovery flow"
```

---

## Task 7: Smoke test for recovery flow

**Files:**
- Modify: `tests/test_smoke.py`

- [ ] **Step 1: Add recovery smoke test to `tests/test_smoke.py`**

Append this function at the end of the file:

```python
def test_screen_lock_recovery_flow(tmp_db_path):
    """Smoke: tracker stops at lock time; back-fill entry can be inserted."""
    conn = connect(tmp_db_path)
    repo = Repository(conn)

    role_id = repo.create_role("Dev")
    cat_id = repo.create_category("Coding", "#ff0000", role_id)

    clock = FakeClock(ts=1_000_000)
    tracker = TimeTracker(repo=repo, clock=clock)

    # Start tracking
    tracker.start(cat_id, EntrySource.MANUAL)
    clock.advance(30 * 60)  # 30 minutes of work

    # Simulate screen lock — tracker stops at lock time
    lock_ts = clock.ts
    returned_cat = tracker.stop_at(lock_ts)
    assert returned_cat == cat_id
    assert repo.get_open_entry() is None

    # Simulate 20 minutes away
    clock.advance(20 * 60)
    unlock_ts = clock.ts

    # Back-fill the absent time to the previous category
    repo.insert_closed_entry(
        cat_id, lock_ts, unlock_ts, EntrySource.SCREEN_LOCK_RECOVERY
    )

    # Resume tracking
    tracker.start(cat_id, EntrySource.MANUAL)
    clock.advance(10 * 60)
    tracker.pause()

    # Should have 3 entries: work before lock, lock recovery, work after unlock
    all_entries = repo.list_entries_between(0, 9_999_999_999)
    closed = [e for e in all_entries if not e.is_active()]
    assert len(closed) == 3

    sources = {e.source for e in closed}
    assert EntrySource.SCREEN_LOCK_RECOVERY in sources

    conn.close()


def test_idle_recovery_discard_flow(tmp_db_path):
    """Smoke: tracker stops at idle time; discard means no back-fill entry."""
    conn = connect(tmp_db_path)
    repo = Repository(conn)

    role_id = repo.create_role("Dev")
    cat_id = repo.create_category("Coding", "#ff0000", role_id)

    clock = FakeClock(ts=2_000_000)
    tracker = TimeTracker(repo=repo, clock=clock)

    tracker.start(cat_id, EntrySource.MANUAL)
    clock.advance(60 * 60)  # 1 hour of work

    # Idle detected
    idle_ts = clock.ts
    tracker.stop_at(idle_ts)

    # User returns 15 minutes later — chooses "Verwerfen"
    clock.advance(15 * 60)
    # No insert_closed_entry (discard)
    tracker.start(cat_id, EntrySource.MANUAL)
    clock.advance(5 * 60)
    tracker.pause()

    all_entries = repo.list_entries_between(0, 9_999_999_999)
    closed = [e for e in all_entries if not e.is_active()]
    # Only 2 entries: before idle and after return (no idle_recovery entry)
    assert len(closed) == 2
    sources = {e.source for e in closed}
    assert EntrySource.IDLE_RECOVERY not in sources

    conn.close()
```

- [ ] **Step 2: Run only the new smoke tests**

```
python -m pytest tests/test_smoke.py -v -k "recovery"
```

Expected: 2 passed

- [ ] **Step 3: Run full test suite**

```
python -m pytest --tb=short -q
```

Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_smoke.py
git commit -m "test: add screen-lock and idle recovery smoke tests"
```

---

## Done

After Task 7, Phase 3 is complete. The app will:
1. Detect screen locks via Windows session events
2. Detect idle after 10 minutes (configurable 5–60 min in Settings → Allgemein)
3. Stop tracking at the moment of absence
4. Show `RecoveryPopup` on return — user chooses back-fill, rebook, or discard
5. Resume tracking based on the user's choice
