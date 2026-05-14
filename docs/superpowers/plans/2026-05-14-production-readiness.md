# Phase 5: Produktionsreife — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Autostart, Backup, global Hotkeys, Tray-Reminder and PyInstaller/Inno Setup packaging to produce a deployable Windows installer.

**Architecture:** Five independent features are layered on top of the existing PyQt6/SQLite app. Three new services (`autostart.py`, `backup.py`, `hotkey_manager.py`) each have a single responsibility. The UI (settings_window.py, tray.py) and wiring (app.py) are updated last. Packaging is the final step.

**Tech Stack:** Python 3.11+, PyQt6, SQLite, `winreg` (stdlib), `ctypes` (stdlib), `shutil` (stdlib), PyInstaller, Inno Setup 6.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/workload_analyzer/services/autostart.py` | Create | `enable/disable/is_enabled` via `winreg` |
| `src/workload_analyzer/services/backup.py` | Create | `backup(db_path, backup_dir) → Path` via `shutil.copy2` |
| `src/workload_analyzer/services/hotkey_manager.py` | Create | `GlobalHotkeyManager` — `RegisterHotKey` + `QAbstractNativeEventFilter` |
| `src/workload_analyzer/ui/settings_window.py` | Modify | Add Autostart checkbox + Backup-Pfad row to Allgemein-Tab |
| `src/workload_analyzer/app.py` | Modify | Run backup on startup; wire hotkeys; unregister on quit |
| `src/workload_analyzer/ui/tray.py` | Modify | Blink timer + `_apply_icon()` for Tray-Reminder |
| `WorkloadAnalyzer.spec` | Create | PyInstaller onedir spec |
| `installer/WorkloadAnalyzer.iss` | Create | Inno Setup script |
| `build.bat` | Create | Two-step build script |
| `tests/test_autostart.py` | Create | Unit tests with mocked `winreg` |
| `tests/test_backup.py` | Create | Tests with `tmp_path` fixture |
| `tests/test_hotkey_manager.py` | Create | Tests with mocked `ctypes.windll` + `qtbot` |

---

## Task 1: Autostart Service

**Files:**
- Create: `src/workload_analyzer/services/autostart.py`
- Create: `tests/test_autostart.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_autostart.py`:

```python
from unittest.mock import MagicMock, patch


def test_enable_writes_registry_entry():
    mock_key = MagicMock()
    with patch("workload_analyzer.services.autostart.winreg.OpenKey", return_value=mock_key), \
         patch("workload_analyzer.services.autostart.winreg.SetValueEx") as mock_set, \
         patch("workload_analyzer.services.autostart.winreg.CloseKey"):
        from workload_analyzer.services.autostart import enable
        enable("C:\\WorkloadAnalyzer.exe")
    args = mock_set.call_args[0]
    assert args[1] == "WorkloadAnalyzer"
    assert args[4] == "C:\\WorkloadAnalyzer.exe"


def test_disable_removes_registry_entry():
    mock_key = MagicMock()
    with patch("workload_analyzer.services.autostart.winreg.OpenKey", return_value=mock_key), \
         patch("workload_analyzer.services.autostart.winreg.DeleteValue") as mock_del, \
         patch("workload_analyzer.services.autostart.winreg.CloseKey"):
        from workload_analyzer.services.autostart import disable
        disable()
    mock_del.assert_called_once_with(mock_key, "WorkloadAnalyzer")


def test_disable_is_silent_when_not_enabled():
    with patch("workload_analyzer.services.autostart.winreg.OpenKey", return_value=MagicMock()), \
         patch("workload_analyzer.services.autostart.winreg.DeleteValue", side_effect=FileNotFoundError), \
         patch("workload_analyzer.services.autostart.winreg.CloseKey"):
        from workload_analyzer.services.autostart import disable
        disable()  # must not raise


def test_is_enabled_returns_true_when_entry_exists():
    with patch("workload_analyzer.services.autostart.winreg.OpenKey", return_value=MagicMock()), \
         patch("workload_analyzer.services.autostart.winreg.QueryValueEx", return_value=("C:\\exe", 1)), \
         patch("workload_analyzer.services.autostart.winreg.CloseKey"):
        from workload_analyzer.services.autostart import is_enabled
        assert is_enabled() is True


def test_is_enabled_returns_false_when_entry_missing():
    with patch("workload_analyzer.services.autostart.winreg.OpenKey", return_value=MagicMock()), \
         patch("workload_analyzer.services.autostart.winreg.QueryValueEx", side_effect=FileNotFoundError), \
         patch("workload_analyzer.services.autostart.winreg.CloseKey"):
        from workload_analyzer.services.autostart import is_enabled
        assert is_enabled() is False
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_autostart.py -v
```
Expected: `ModuleNotFoundError: No module named 'workload_analyzer.services.autostart'`

- [ ] **Step 3: Implement `autostart.py`**

Create `src/workload_analyzer/services/autostart.py`:

```python
import logging
import winreg

_REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "WorkloadAnalyzer"
_log = logging.getLogger(__name__)


def enable(exe_path: str) -> None:
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REGISTRY_KEY, 0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)
    except OSError as e:
        _log.warning("Autostart enable failed: %s", e)


def disable() -> None:
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REGISTRY_KEY, 0, winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, _APP_NAME)
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass
    except OSError as e:
        _log.warning("Autostart disable failed: %s", e)


def is_enabled() -> bool:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REGISTRY_KEY)
        winreg.QueryValueEx(key, _APP_NAME)
        winreg.CloseKey(key)
        return True
    except (FileNotFoundError, OSError):
        return False
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_autostart.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```
git add src/workload_analyzer/services/autostart.py tests/test_autostart.py
git commit -m "feat: add autostart service (Registry HKCU Run entry)"
```

---

## Task 2: Backup Service

**Files:**
- Create: `src/workload_analyzer/services/backup.py`
- Create: `tests/test_backup.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_backup.py`:

```python
from pathlib import Path
from workload_analyzer.services.backup import backup


def test_backup_creates_timestamped_file(tmp_path: Path):
    db = tmp_path / "workload.db"
    db.write_bytes(b"test database content")
    backup_dir = tmp_path / "backups"

    result = backup(db, backup_dir)

    assert result.exists()
    assert result.parent == backup_dir
    assert result.name.startswith("workload_")
    assert result.suffix == ".db"
    assert result.read_bytes() == b"test database content"


def test_backup_creates_directory_if_missing(tmp_path: Path):
    db = tmp_path / "workload.db"
    db.write_bytes(b"data")
    backup_dir = tmp_path / "a" / "b" / "c"

    backup(db, backup_dir)

    assert backup_dir.exists()


def test_backup_filename_contains_timestamp(tmp_path: Path):
    db = tmp_path / "workload.db"
    db.write_bytes(b"x")
    backup_dir = tmp_path / "backups"

    result = backup(db, backup_dir)

    # Format: workload_YYYYMMDD_HHMMSS.db — 8+1+6 chars between underscores
    parts = result.stem.split("_")   # ["workload", "20260514", "123456"]
    assert len(parts) == 3
    assert parts[0] == "workload"
    assert len(parts[1]) == 8   # YYYYMMDD
    assert len(parts[2]) == 6   # HHMMSS


def test_backup_returns_path_to_new_file(tmp_path: Path):
    db = tmp_path / "workload.db"
    db.write_bytes(b"data")

    result = backup(db, tmp_path / "backups")

    assert isinstance(result, Path)
    assert result.exists()
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_backup.py -v
```
Expected: `ModuleNotFoundError: No module named 'workload_analyzer.services.backup'`

- [ ] **Step 3: Implement `backup.py`**

Create `src/workload_analyzer/services/backup.py`:

```python
import shutil
from datetime import datetime
from pathlib import Path


def backup(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"workload_{ts}.db"
    shutil.copy2(db_path, dest)
    return dest
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_backup.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```
git add src/workload_analyzer/services/backup.py tests/test_backup.py
git commit -m "feat: add backup service (timestamped SQLite copy on startup)"
```

---

## Task 3: Global Hotkey Manager

**Files:**
- Create: `src/workload_analyzer/services/hotkey_manager.py`
- Create: `tests/test_hotkey_manager.py`

Background: `RegisterHotKey(NULL, id, mods, vk)` with `hwnd=NULL` posts `WM_HOTKEY` (0x0312) to the calling thread's message queue. PyQt6's `QAbstractNativeEventFilter` installed on `QApplication` intercepts these messages before they reach any window.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_hotkey_manager.py`:

```python
from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture(autouse=True)
def mock_ctypes(monkeypatch):
    """Prevent real RegisterHotKey calls during tests."""
    mock_user32 = MagicMock()
    mock_user32.RegisterHotKey.return_value = 1   # success
    mock_user32.UnregisterHotKey.return_value = 1
    with patch("workload_analyzer.services.hotkey_manager.ctypes") as mock_ctypes:
        mock_ctypes.windll.user32 = mock_user32
        yield mock_ctypes


def test_register_calls_RegisterHotKey(qtbot, mock_ctypes):
    from workload_analyzer.services.hotkey_manager import GlobalHotkeyManager
    manager = GlobalHotkeyManager()
    qtbot.addWidget(manager._sink)

    manager.register(1)

    mock_ctypes.windll.user32.RegisterHotKey.assert_called_once()
    args = mock_ctypes.windll.user32.RegisterHotKey.call_args[0]
    assert args[1] == 1           # hotkey id = n
    assert args[2] == 0x0006      # MOD_CONTROL | MOD_SHIFT
    assert args[3] == 0x31        # VK_1


def test_register_all_nine_hotkeys(qtbot, mock_ctypes):
    from workload_analyzer.services.hotkey_manager import GlobalHotkeyManager
    manager = GlobalHotkeyManager()
    qtbot.addWidget(manager._sink)

    for i in range(1, 10):
        manager.register(i)

    assert mock_ctypes.windll.user32.RegisterHotKey.call_count == 9


def test_register_ignores_out_of_range(qtbot, mock_ctypes):
    from workload_analyzer.services.hotkey_manager import GlobalHotkeyManager
    manager = GlobalHotkeyManager()
    qtbot.addWidget(manager._sink)

    manager.register(0)
    manager.register(10)

    mock_ctypes.windll.user32.RegisterHotKey.assert_not_called()


def test_unregister_all_calls_UnregisterHotKey(qtbot, mock_ctypes):
    from workload_analyzer.services.hotkey_manager import GlobalHotkeyManager
    manager = GlobalHotkeyManager()
    qtbot.addWidget(manager._sink)
    manager.register(1)
    manager.register(2)

    manager.unregister_all()

    assert mock_ctypes.windll.user32.UnregisterHotKey.call_count == 2


def test_triggered_signal_emits_n(qtbot, mock_ctypes):
    from workload_analyzer.services.hotkey_manager import GlobalHotkeyManager
    manager = GlobalHotkeyManager()
    qtbot.addWidget(manager._sink)
    manager.register(3)

    received = []
    manager.triggered.connect(received.append)

    # Simulate WM_HOTKEY by calling internal handler directly
    manager._on_hotkey(3)

    assert received == [3]
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_hotkey_manager.py -v
```
Expected: `ModuleNotFoundError: No module named 'workload_analyzer.services.hotkey_manager'`

- [ ] **Step 3: Implement `hotkey_manager.py`**

Create `src/workload_analyzer/services/hotkey_manager.py`:

```python
import ctypes
import ctypes.wintypes
import logging
from typing import Optional

from PyQt6.QtCore import QAbstractNativeEventFilter, QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget

_log = logging.getLogger(__name__)

MOD_CONTROL = 0x0002
MOD_SHIFT   = 0x0004
WM_HOTKEY   = 0x0312
_VK = {i: 0x30 + i for i in range(1, 10)}  # 0x31=VK_1 … 0x39=VK_9


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, event_type, message):
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                self._callback(int(msg.wParam))
                return True, 0
        except Exception:
            pass
        return False, 0


class GlobalHotkeyManager(QObject):
    triggered = pyqtSignal(int)  # emits 1..9

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._registered: list[int] = []
        # Invisible sink widget — keeps a reference alive and provides winId if needed
        self._sink = QWidget()
        self._sink.setFixedSize(0, 0)
        self._sink.hide()
        self._filter = _HotkeyFilter(self._on_hotkey)
        QApplication.instance().installNativeEventFilter(self._filter)

    def _on_hotkey(self, n: int) -> None:
        self.triggered.emit(n)

    def register(self, n: int) -> None:
        if n not in range(1, 10):
            return
        ok = ctypes.windll.user32.RegisterHotKey(None, n, MOD_CONTROL | MOD_SHIFT, _VK[n])
        if ok:
            self._registered.append(n)
        else:
            _log.warning("Could not register Ctrl+Shift+%d (already in use?)", n)

    def unregister_all(self) -> None:
        for n in self._registered:
            ctypes.windll.user32.UnregisterHotKey(None, n)
        self._registered.clear()
        app = QApplication.instance()
        if app:
            app.removeNativeEventFilter(self._filter)
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_hotkey_manager.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```
git add src/workload_analyzer/services/hotkey_manager.py tests/test_hotkey_manager.py
git commit -m "feat: add GlobalHotkeyManager (Ctrl+Shift+1..9 via RegisterHotKey)"
```

---

## Task 4: Settings UI — Allgemein-Tab Extensions

**Files:**
- Modify: `src/workload_analyzer/ui/settings_window.py`

Adds Autostart checkbox and Backup-Pfad row to the existing Allgemein-Tab.

- [ ] **Step 1: Add missing imports to `settings_window.py`**

At the top of the file, extend the existing import blocks:

```python
# Add to stdlib imports (new line after existing imports):
import sys
from pathlib import Path

# Add QFileDialog to the existing PyQt6.QtWidgets import:
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
```

- [ ] **Step 2: Replace `_build_general_tab` with extended version**

Replace the entire `_build_general_tab` method (lines 186–209 in the current file):

```python
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

    self._idle_spin = QSpinBox()
    self._idle_spin.setRange(5, 60)
    self._idle_spin.setSuffix(" Min")
    current_idle = int(self.repo.get_setting("idle_threshold_minutes", "10") or "10")
    self._idle_spin.setValue(current_idle)
    self._idle_spin.valueChanged.connect(self._save_idle_threshold)
    form.addRow("Idle-Schwellwert:", self._idle_spin)

    # Autostart
    from workload_analyzer.services import autostart as _autostart
    self._autostart_checkbox = QCheckBox()
    is_frozen = getattr(sys, "frozen", False)
    if is_frozen:
        self._autostart_checkbox.setChecked(_autostart.is_enabled())
    else:
        self._autostart_checkbox.setEnabled(False)
        self._autostart_checkbox.setToolTip("Nur im installierten Paket verfügbar")
    self._autostart_checkbox.toggled.connect(self._save_autostart)
    form.addRow("Mit Windows starten:", self._autostart_checkbox)

    # Backup path
    backup_row = QHBoxLayout()
    self._backup_path_edit = QLineEdit()
    default_backup = str(Path.home() / "Documents" / "WorkloadAnalyzer" / "backups")
    self._backup_path_edit.setPlaceholderText(default_backup)
    self._backup_path_edit.setText(self.repo.get_setting("backup_path", ""))
    self._backup_path_edit.editingFinished.connect(self._save_backup_path)
    browse_btn = QPushButton("Durchsuchen…")
    browse_btn.clicked.connect(self._browse_backup_path)
    backup_row.addWidget(self._backup_path_edit)
    backup_row.addWidget(browse_btn)
    form.addRow("Backup-Pfad:", backup_row)

    return w
```

- [ ] **Step 3: Add the three new helper methods**

Add after `_save_idle_threshold` (after line ~218 in the current file):

```python
def _save_autostart(self, checked: bool) -> None:
    from workload_analyzer.services import autostart as _autostart
    if checked:
        _autostart.enable(sys.executable)
    else:
        _autostart.disable()

def _save_backup_path(self) -> None:
    self.repo.set_setting("backup_path", self._backup_path_edit.text().strip())

def _browse_backup_path(self) -> None:
    path = QFileDialog.getExistingDirectory(self, "Backup-Ordner wählen")
    if path:
        self._backup_path_edit.setText(path)
        self._save_backup_path()
```

- [ ] **Step 4: Run the full test suite to confirm no regressions**

```
pytest tests/ -v
```
Expected: all previously passing tests still pass (109+)

- [ ] **Step 5: Commit**

```
git add src/workload_analyzer/ui/settings_window.py
git commit -m "feat: add autostart checkbox and backup-path field to settings"
```

---

## Task 5: Wire Backup and Hotkeys in `app.py`

**Files:**
- Modify: `src/workload_analyzer/app.py`

- [ ] **Step 1: Add missing imports to `app.py`**

Add to the existing imports at the top of `app.py`:

```python
import logging
from pathlib import Path
```

- [ ] **Step 2: Add backup-on-startup call**

In `run()`, directly after the line `repo = Repository(conn)` (line 21), insert:

```python
_backup_path = repo.get_setting("backup_path", "")
if _backup_path:
    try:
        from workload_analyzer.services.backup import backup
        backup(db_path(), Path(_backup_path))
    except Exception as exc:
        logging.getLogger(__name__).warning("Startup backup failed: %s", exc)
```

- [ ] **Step 3: Register global hotkeys after tray creation**

In `run()`, after `tray = TrayIcon(repo=repo, tracker=tracker)` (currently line 43), insert:

```python
from workload_analyzer.services.hotkey_manager import GlobalHotkeyManager
hotkeys = GlobalHotkeyManager()
for i in range(1, 10):
    hotkeys.register(i)

def _on_hotkey(n: int) -> None:
    cats = repo.list_categories(active_only=True)
    if n <= len(cats):
        tracker.switch_to(cats[n - 1].id, EntrySource.MANUAL)
        tray.refresh()

hotkeys.triggered.connect(_on_hotkey)
```

- [ ] **Step 4: Add `hotkeys.unregister_all()` to `_quit`**

Find the `_quit` function near the bottom of `run()`. Replace it with:

```python
def _quit():
    hotkeys.unregister_all()
    sys_monitor.stop()
    monitor.stop()
    app.quit()
```

- [ ] **Step 5: Run the full test suite**

```
pytest tests/ -v
```
Expected: all tests pass

- [ ] **Step 6: Commit**

```
git add src/workload_analyzer/app.py
git commit -m "feat: run backup on startup; wire Ctrl+Shift+1..9 hotkeys"
```

---

## Task 6: Tray-Reminder

**Files:**
- Modify: `src/workload_analyzer/ui/tray.py`

After 2 hours without a category switch, the tray icon alternates every 2 seconds between the category color and `#888888`.

- [ ] **Step 1: Add `import time` to tray.py**

At the top of `tray.py`, add after the existing stdlib imports:

```python
import time
```

- [ ] **Step 2: Add reminder state to `TrayIcon.__init__`**

In `__init__`, after the line `self._outlook_available: bool = True`, add:

```python
self._last_cat_id: Optional[int] = None
self._last_cat_change_ts: float = time.time()
self._reminder_active: bool = False
self._blink_state: bool = False

self._blink_timer = QTimer(self)
self._blink_timer.setInterval(2000)
self._blink_timer.timeout.connect(self._on_blink)
```

- [ ] **Step 3: Add `_on_blink` and `_apply_icon` methods**

Add these two new methods to `TrayIcon` (before `_on_pause`):

```python
def _on_blink(self) -> None:
    self._blink_state = not self._blink_state
    self._apply_icon(self.tracker.current_state())

def _apply_icon(self, state) -> None:
    if not self._outlook_available:
        self.icon.setIcon(_make_color_icon("#ff8800"))
        return
    if state.kind == TrackerState.Kind.TRACKING and state.category_id is not None:
        cat = self.repo.get_category(state.category_id)
        if cat:
            color = "#888888" if (self._reminder_active and self._blink_state) else cat.color
            self.icon.setIcon(_make_color_icon(color))
        else:
            self.icon.setIcon(_make_color_icon("#888888"))
    elif state.kind == TrackerState.Kind.PAUSED:
        self.icon.setIcon(_make_color_icon("#cccc44"))
    else:
        self.icon.setIcon(_make_color_icon("#888888"))
```

- [ ] **Step 4: Rewrite `refresh()` to use `_apply_icon` and track reminder state**

Replace the entire `refresh` method with:

```python
def refresh(self) -> None:
    self._refresh_switch_menu()
    state = self.tracker.current_state()

    # Reminder state tracking
    current_cat_id = state.category_id if state.kind == TrackerState.Kind.TRACKING else None
    if current_cat_id != self._last_cat_id:
        self._last_cat_id = current_cat_id
        self._last_cat_change_ts = time.time()
        self._reminder_active = False
        self._blink_state = False
        self._blink_timer.stop()
    elif not self._reminder_active and time.time() - self._last_cat_change_ts > 7200:
        self._reminder_active = True
        self._blink_timer.start()

    if state.kind == TrackerState.Kind.TRACKING and state.category_id is not None:
        cat = self.repo.get_category(state.category_id)
        if cat:
            role = self.repo.get_role(cat.role_id)
            role_name = role.name if role else ""
            self._header_action.setText(f"{cat.name} ({role_name})")
            self.icon.setToolTip(f"Tracking: {cat.name}")
        self._pause_action.setEnabled(True)
        self._resume_action.setEnabled(False)
    elif state.kind == TrackerState.Kind.PAUSED:
        self._header_action.setText("Paused")
        self.icon.setToolTip("WorkloadAnalyzer (paused)")
        self._pause_action.setEnabled(False)
        self._resume_action.setEnabled(True)
    else:
        self._header_action.setText("Not tracking")
        self.icon.setToolTip("WorkloadAnalyzer")
        self._pause_action.setEnabled(False)
        self._resume_action.setEnabled(False)

    if not self._outlook_available:
        self.icon.setToolTip(self.icon.toolTip() + " ⚠ Outlook nicht verfügbar")

    self._apply_icon(state)
```

- [ ] **Step 5: Run the full test suite**

```
pytest tests/ -v
```
Expected: all tests pass

- [ ] **Step 6: Commit**

```
git add src/workload_analyzer/ui/tray.py
git commit -m "feat: add tray reminder — blink icon gray after 2h without category switch"
```

---

## Task 7: Packaging (PyInstaller + Inno Setup)

**Files:**
- Create: `WorkloadAnalyzer.spec`
- Create: `installer/WorkloadAnalyzer.iss`
- Create: `build.bat`

No automated tests for packaging — manual verification described below.

- [ ] **Step 1: Create `WorkloadAnalyzer.spec`**

Create at the project root (`D:\Claude\Projekte\WorkloadAnalyzer\WorkloadAnalyzer.spec`):

```python
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['src/workload_analyzer/__main__.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'win32com',
        'win32com.client',
        'pythoncom',
        'pywintypes',
        'PyQt6.sip',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WorkloadAnalyzer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WorkloadAnalyzer',
)
```

- [ ] **Step 2: Create `installer/` directory and `WorkloadAnalyzer.iss`**

Create `installer/WorkloadAnalyzer.iss`:

```ini
[Setup]
AppName=WorkloadAnalyzer
AppVersion=1.0.0
AppPublisher=WorkloadAnalyzer
DefaultDirName={autopf}\WorkloadAnalyzer
DefaultGroupName=WorkloadAnalyzer
OutputDir=Output
OutputBaseFilename=WorkloadAnalyzer_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\WorkloadAnalyzer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\WorkloadAnalyzer"; Filename: "{app}\WorkloadAnalyzer.exe"
Name: "{group}\{cm:UninstallProgram,WorkloadAnalyzer}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\WorkloadAnalyzer"; Filename: "{app}\WorkloadAnalyzer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\WorkloadAnalyzer.exe"; Description: "{cm:LaunchProgram,WorkloadAnalyzer}"; Flags: nowait postinstall skipifsilent
```

- [ ] **Step 3: Create `build.bat`**

Create at the project root:

```bat
@echo off
echo Building WorkloadAnalyzer...
echo.

echo [1/2] PyInstaller...
pyinstaller WorkloadAnalyzer.spec --clean
if errorlevel 1 (
    echo PyInstaller failed.
    exit /b 1
)

echo.
echo [2/2] Inno Setup...
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\WorkloadAnalyzer.iss
if errorlevel 1 (
    echo Inno Setup failed.
    exit /b 1
)

echo.
echo Done: installer\Output\WorkloadAnalyzer_Setup.exe
```

- [ ] **Step 4: Verify PyInstaller build (manual)**

Run in the project directory:
```
pip install pyinstaller
pyinstaller WorkloadAnalyzer.spec --clean
```

Expected: `dist\WorkloadAnalyzer\WorkloadAnalyzer.exe` exists.

Start it and verify:
- System tray icon appears
- Settings window opens (right-click tray → Settings…)
- Autostart checkbox is enabled (because `sys.frozen` is True)

- [ ] **Step 5: Verify Inno Setup build (manual, requires Inno Setup 6 installed)**

```
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\WorkloadAnalyzer.iss
```

Expected: `installer\Output\WorkloadAnalyzer_Setup.exe` exists.

Run the installer and verify:
- App installs to `%ProgramFiles%\WorkloadAnalyzer\`
- Start menu entry created
- App launches after installation

- [ ] **Step 6: Commit**

```
git add WorkloadAnalyzer.spec installer/WorkloadAnalyzer.iss build.bat
git commit -m "feat: add PyInstaller spec and Inno Setup installer"
```

---

## Task 8: Final Verification

- [ ] **Step 1: Run complete test suite**

```
pytest tests/ -v --tb=short
```
Expected: all 109+ tests pass, no failures.

- [ ] **Step 2: Update STATUS.md**

In `STATUS.md`, add Phase 5 to the "Fertig" table:

```markdown
| 5 | **Produktionsreife** — Autostart (Registry), Backup (startup copy), Globale Hotkeys (Ctrl+Shift+1..9), Tray-Reminder (blink nach 2h), PyInstaller+Inno Setup Installer | `plans/2026-05-14-production-readiness.md` | `specs/2026-05-14-production-readiness-design.md` |
```

Update the test count to reflect the new tests.

- [ ] **Step 3: Commit STATUS.md**

```
git add STATUS.md
git commit -m "docs: mark Phase 5 as complete in STATUS.md"
```
