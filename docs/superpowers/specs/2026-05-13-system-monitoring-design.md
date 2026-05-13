# Phase 3: System Monitoring — Design Spec

**Date:** 2026-05-13
**Status:** Approved

---

## Overview

Phase 3 adds automatic absence detection to WorkloadAnalyzer. Two triggers are supported:

1. **Screen lock / unlock** — detected via Windows session events (`WM_WTSSESSION_CHANGE`)
2. **Idle detection** — detected by polling `GetLastInputInfo()` against a configurable threshold

Both triggers follow the same recovery flow: tracking is stopped at the moment of absence, and when the user returns a popup asks what to do with the absent time.

---

## Architecture

### New Files

```
src/workload_analyzer/services/system_monitor.py   # Core detector
src/workload_analyzer/ui/recovery_popup.py         # Recovery dialog
tests/test_system_monitor.py
tests/test_recovery_popup.py
```

### Modified Files

```
src/workload_analyzer/core/tracker.py              # Add stop_at(timestamp)
src/workload_analyzer/ui/settings_window.py        # Add idle threshold setting
src/workload_analyzer/app.py                       # Wire SystemMonitor
```

---

## SystemMonitor

`SystemMonitor(QObject)` mirrors the `OutlookMonitor` pattern: signals emitted from the main Qt thread, injectable dependencies for testability.

### Signals

```python
session_locked   = pyqtSignal(int)       # unix timestamp of lock
session_unlocked = pyqtSignal(int, int)  # lock_ts, unlock_ts
idle_started     = pyqtSignal(int)       # unix timestamp idle began
user_returned    = pyqtSignal(int, int)  # idle_start_ts, return_ts
```

### Implementation

**Screen lock detection** — `QAbstractNativeEventFilter`:
- On `start()`, call `WTSRegisterSessionNotification(hwnd, NOTIFY_FOR_THIS_SESSION)`
- Filter intercepts `WM_WTSSESSION_CHANGE` messages
- `WTS_SESSION_LOCK` → emit `session_locked(now)`; set `_locked = True`
- `WTS_SESSION_UNLOCK` → emit `session_unlocked(lock_ts, now)`; set `_locked = False`
- Lock takes precedence: if idle is active when lock fires, emit `idle_started` is suppressed; lock event governs

**Idle detection** — `QTimer` (30s interval):
- Poll `GetLastInputInfo()` to get milliseconds since last input
- If idle_ms ≥ threshold and not already idle and not locked → emit `idle_started(idle_begin_ts)`; set `_idle = True`
- If idle and input activity detected → emit `user_returned(idle_start_ts, now)`; set `_idle = False`

### Injectable Dependencies (for testing)

```python
SystemMonitor(
    wts_register_fn=None,   # default: ctypes WTSRegisterSessionNotification
    get_last_input_fn=None, # default: ctypes GetLastInputInfo
    clock=None,             # default: int(time.time())
    idle_threshold_seconds=600,
)
```

Tests invoke `nativeEventFilter()` directly with crafted byte payloads and control `get_last_input_fn` return values.

### Methods

```python
def start(self) -> None: ...   # register WTS, start idle timer
def stop(self) -> None: ...    # unregister WTS, stop idle timer
def set_idle_threshold(self, seconds: int) -> None: ...
```

---

## Recovery Flow

### Trigger → Absence Start

When `session_locked` or `idle_started` fires in `app.py`:

1. Call `tracker.stop_at(absence_start_ts)` — ends the running entry at the absence timestamp; returns the `category_id` of the stopped entry (or `None` if nothing was running).
2. Store `(absence_start_ts, previous_category_id)` in memory.

### Return → RecoveryPopup

When `session_unlocked` or `user_returned` fires:

1. Compute `absent_seconds = return_ts - absence_start_ts`.
2. Show `RecoveryPopup(absent_seconds, previous_category, all_categories)`.
3. Popup stays open until user responds (no auto-close).

### User Choices

| Choice | Action |
|--------|--------|
| **Vorherige Kategorie** | Create `TimeEntry[absence_start → now]` with `previous_category_id`, `source = SCREEN_LOCK_RECOVERY` / `IDLE_RECOVERY`; then `tracker.start(previous_category_id)` |
| **Andere Kategorie wählen** | Dropdown with active categories; create `TimeEntry[absence_start → now]` with chosen category; then `tracker.start(chosen_id)` |
| **Verwerfen** | No entry created for absent time; `tracker.start(previous_category_id)` from now |

### Edge Cases

- **Tracker was not running at lock time** → `stop_at` returns `None`; popup shows only „Tracking starten?" with category picker; „Vorherige Kategorie" option is hidden.
- **Absence > 8 hours** → Popup adds warning text; „Verwerfen" is pre-selected.
- **Multiple locks without answering** → Only one popup per return, covering the full cumulative absence.
- **Idle triggers while popup is open** → Suppressed; lock/idle state is already active.

---

## RecoveryPopup

`RecoveryPopup(QDialog)`:

```
┌─────────────────────────────────────────────────────┐
│  Du warst 23 Minuten abwesend (Bildschirm gesperrt) │
│                                                     │
│  ○ Auf vorherige Kategorie buchen  [Projektarbeit]  │
│  ○ Andere Kategorie wählen         [──────────▼]    │
│  ○ Verwerfen                                        │
│                                                     │
│                              [Bestätigen]           │
└─────────────────────────────────────────────────────┘
```

Return codes:
```python
RECOVERY_PREVIOUS = 1
RECOVERY_OTHER    = 2
RECOVERY_DISCARD  = 3
```

`WindowStaysOnTopHint` flag set (consistent with `SuggestionPopup`).

---

## TimeTracker — New Method

```python
def stop_at(self, ts: int) -> int | None:
    """Stop the running entry at the given timestamp.
    Returns the category_id of the stopped entry, or None if not tracking."""
```

Internally: sets `end_time = ts` on the current entry, persists via `repo.end_entry(entry_id, ts)`, clears tracker state.

---

## Settings Integration

Idle threshold is added to the existing **General** tab (no new tab — too small):

```
Idle-Erkennung
  Schwellwert: [10] ↕  Minuten  (range: 5–60)
```

- Stored as `settings` key: `idle_threshold_minutes`, default `"10"`
- On save: calls `system_monitor.set_idle_threshold(minutes * 60)` if monitor is running

---

## EntrySource Values

Already present in `models.py`:
- `SCREEN_LOCK_RECOVERY` — entries back-filled after screen lock
- `IDLE_RECOVERY` — entries back-filled after idle

---

## Out of Scope

- No automatic booking without user confirmation
- No midnight-crossing repair
- No multi-monitor / Remote Desktop special handling
- No Linux / macOS support

---

## Estimated Tasks

| # | Task |
|---|------|
| 1 | `tracker.stop_at()` + DB method `end_entry()` |
| 2 | `SystemMonitor` — WTS screen lock detection + tests |
| 3 | `SystemMonitor` — idle detection + tests |
| 4 | `RecoveryPopup` dialog + tests |
| 5 | Settings: idle threshold UI + persistence |
| 6 | `app.py` wiring: SystemMonitor → RecoveryPopup → tracker |
| 7 | Smoke test + integration |
