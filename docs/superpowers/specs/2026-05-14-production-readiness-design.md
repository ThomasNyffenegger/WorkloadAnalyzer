# Phase 5: Produktionsreife — Design Spec

**Date:** 2026-05-14
**Status:** Approved

---

## Overview

Phase 5 bündelt alle offenen Spec-Schulden aus Phase 1 zu einer deployable App. Fünf unabhängige Features werden in einem Plan implementiert:

1. **Autostart** — Windows-Registry-Eintrag, Checkbox in Einstellungen
2. **Backup** — Automatische DB-Sicherung beim Start, konfigurierbarer Pfad
3. **Hotkeys** — Globale `Ctrl+Shift+1..9` via Windows-API (`RegisterHotKey`)
4. **Tray-Reminder** — Pulsierendes Icon nach 2h ohne Kategoriewechsel
5. **Packaging** — PyInstaller (onedir) + Inno Setup Windows-Installer

Keine DB-Änderungen. Keine neuen Modelle. Keine neuen Fenster.

---

## Architecture

### New Files

```
src/workload_analyzer/services/autostart.py      # Registry-Helper (enable/disable/is_enabled)
src/workload_analyzer/services/backup.py         # DB-Backup-Funktion
src/workload_analyzer/services/hotkey_manager.py # GlobalHotkeyManager (ctypes + QAbstractNativeEventFilter)
installer/WorkloadAnalyzer.iss                   # Inno Setup Script
WorkloadAnalyzer.spec                            # PyInstaller Spec
build.bat                                        # Build-Skript (pyinstaller → iscc)
```

### Modified Files

```
src/workload_analyzer/ui/settings_window.py      # Allgemein-Tab: Autostart-Checkbox + Backup-Pfad
src/workload_analyzer/ui/tray.py                 # Tray-Reminder: Blink-Timer + Icon-Logik
src/workload_analyzer/app.py                     # Backup beim Start + Hotkeys verdrahten
```

### New Tests

```
tests/test_autostart.py
tests/test_backup.py
tests/test_hotkey_manager.py
```

---

## Feature 1: Autostart

### Service (`services/autostart.py`)

Drei reine Funktionen, kein State:

```python
REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "WorkloadAnalyzer"

def enable(exe_path: str) -> None:
    # Schreibt HKCU\...\Run\WorkloadAnalyzer = exe_path

def disable() -> None:
    # Löscht HKCU\...\Run\WorkloadAnalyzer (silent wenn nicht vorhanden)

def is_enabled() -> bool:
    # Prüft ob Eintrag existiert und auf exe_path zeigt
```

Implementierung via `winreg` (stdlib, kein Zusatzpaket).

### Settings UI

Im **Allgemein-Tab** (`_build_general_tab()`):

- Neue `QCheckBox("Mit Windows starten")`
- Checked → `autostart.enable(sys.executable)`
- Unchecked → `autostart.disable()`
- Wenn `not getattr(sys, 'frozen', False)`: Checkbox deaktiviert + Tooltip "Nur im installierten Paket verfügbar"
- Initialer Zustand: `autostart.is_enabled()`

### Dev vs. Packaged

`sys.frozen` ist `True` wenn unter PyInstaller gepackt, sonst undefiniert. Beim Entwickeln ist die Checkbox ausgegraut — kein Registry-Schreiben in die Entwicklungsumgebung.

---

## Feature 2: Backup

### Service (`services/backup.py`)

```python
def backup(db_path: Path, backup_dir: Path) -> Path:
    """Kopiert db_path → backup_dir/workload_YYYYMMDD_HHMMSS.db.
    Erstellt backup_dir wenn nötig. Gibt den neuen Pfad zurück."""
```

Implementierung: `shutil.copy2`. Keine Rotation — alte Backups bleiben erhalten.

### Aufruf in `app.py`

Direkt nach `repo = Repository(conn)`, vor dem ersten-Start-Dialog:

```python
backup_path_str = repo.get_setting("backup_path", "")
if backup_path_str:
    from workload_analyzer.services.backup import backup
    backup(db_path(), Path(backup_path_str))
```

Fehler beim Backup (z.B. Pfad nicht erreichbar) werden geloggt aber nicht abgebrochen — App startet trotzdem.

### Settings UI

Im **Allgemein-Tab**:

- Label "Backup-Pfad:"
- `QLineEdit` + `QPushButton("Durchsuchen…")` (öffnet `QFileDialog.getExistingDirectory`)
- Default wenn Einstellung leer: `%USERPROFILE%\Documents\WorkloadAnalyzer\backups\` wird als Placeholder angezeigt
- Leer lassen = kein Backup
- Gespeichert via `repo.set_setting("backup_path", pfad)` beim Verlassen des Feldes (oder bei Dialog-Schließen)

---

## Feature 3: Globale Hotkeys

### Service (`services/hotkey_manager.py`)

```python
class GlobalHotkeyManager(QObject):
    triggered = pyqtSignal(int)   # emittiert 1..9

    def __init__(self, parent=None): ...
    def register(self, n: int) -> None: ...   # RegisterHotKey für Ctrl+Shift+n
    def unregister_all(self) -> None: ...      # UnregisterHotKey für alle
```

**Implementierung:**
- Internes unsichtbares `QWidget` als HWND-Quelle
- `ctypes.windll.user32.RegisterHotKey(hwnd, id=n, MOD_CONTROL|MOD_SHIFT, VK_1..VK_9)`
- `QAbstractNativeEventFilter` auf der `QApplication` fängt `WM_HOTKEY` (0x0312) ab
- Bei Konflikt (Hotkey bereits belegt): `register()` loggt Warning, überspringt diesen Slot

**Modifiers:** `MOD_CONTROL = 0x0002`, `MOD_SHIFT = 0x0004`
**VK-Codes:** `0x31`–`0x39` für `1`–`9`

### Verdrahtung in `app.py`

```python
hotkeys = GlobalHotkeyManager()
for i in range(1, 10):
    hotkeys.register(i)

def _on_hotkey(n: int):
    cats = repo.list_categories(active_only=True)
    if n <= len(cats):
        tracker.switch_to(cats[n - 1].id, EntrySource.MANUAL)
        tray.refresh()

hotkeys.triggered.connect(_on_hotkey)
```

Reihenfolge der Kategorien = `list_categories(active_only=True)` (DB-Reihenfolge). Kein separater Thread.

### Cleanup

`hotkeys.unregister_all()` wird in `_quit()` aufgerufen, bevor `app.quit()`.

---

## Feature 4: Tray-Reminder

Änderungen ausschließlich in `tray.py`.

### Neuer State in `TrayIcon.__init__`

```python
self._last_cat_id: Optional[int] = None
self._last_cat_change_ts: float = time.time()
self._reminder_active: bool = False
self._blink_state: bool = False

self._blink_timer = QTimer(self)
self._blink_timer.setInterval(2000)
self._blink_timer.timeout.connect(self._on_blink)
```

### `refresh()` — Kategoriewechsel-Erkennung

```python
current_cat_id = state.category_id if state.kind == TRACKING else None
if current_cat_id != self._last_cat_id:
    self._last_cat_id = current_cat_id
    self._last_cat_change_ts = time.time()
    self._reminder_active = False
    self._blink_state = False
    self._blink_timer.stop()
elif time.time() - self._last_cat_change_ts > 7200:
    if not self._reminder_active:
        self._reminder_active = True
        self._blink_timer.start()
```

### `_on_blink()`

```python
def _on_blink(self):
    self._blink_state = not self._blink_state
    self._apply_icon()
```

### `_apply_icon()` — Prioritäten

```
1. Outlook unavailable          → Orange (#ff8800)  [wie bisher]
2. reminder_active + blink=True → Grau (#888888)
3. reminder_active + blink=False→ Kategorie-Farbe
4. Normal (TRACKING)            → Kategorie-Farbe
5. Paused                       → Gelb (#cccc44)
6. Not tracking                 → Grau (#888888)
```

`refresh()` ruft `_apply_icon()` am Ende auf (statt direkt `self.icon.setIcon(...)` zu setzen).

---

## Feature 5: Packaging

### PyInstaller (`WorkloadAnalyzer.spec`)

```python
a = Analysis(
    ['src/workload_analyzer/__main__.py'],
    pathex=['.'],
    hiddenimports=[
        'win32com', 'win32com.client', 'pythoncom', 'pywintypes',
        'PyQt6.sip',
    ],
    ...
)
exe = EXE(a.pure, ..., name='WorkloadAnalyzer', console=False, ...)
coll = COLLECT(exe, ..., name='WorkloadAnalyzer')
```

- Modus: `--onedir` (COLLECT) — schneller Start, DLLs im Ordner
- `console=False` — kein Konsolenfenster
- Output: `dist/WorkloadAnalyzer/WorkloadAnalyzer.exe`

### Inno Setup (`installer/WorkloadAnalyzer.iss`)

```ini
[Setup]
AppName=WorkloadAnalyzer
AppVersion=1.0.0
DefaultDirName={autopf}\WorkloadAnalyzer
DefaultGroupName=WorkloadAnalyzer
OutputDir=installer\Output
OutputBaseFilename=WorkloadAnalyzer_Setup

[Files]
Source: "dist\WorkloadAnalyzer\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\WorkloadAnalyzer"; Filename: "{app}\WorkloadAnalyzer.exe"
Name: "{group}\Deinstallieren";  Filename: "{uninstallexe}"

[Run]
Filename: "{app}\WorkloadAnalyzer.exe"; Description: "WorkloadAnalyzer starten"; Flags: postinstall nowait
```

### Build-Skript (`build.bat`)

```bat
@echo off
pyinstaller WorkloadAnalyzer.spec --clean
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\WorkloadAnalyzer.iss
echo Fertig: installer\Output\WorkloadAnalyzer_Setup.exe
```

---

## Testing

### `test_autostart.py`
- `enable()` + `is_enabled()` → `True`
- `disable()` + `is_enabled()` → `False`
- `disable()` wenn nicht aktiviert → kein Fehler
- Mock `winreg` für CI-Umgebungen ohne Windows-Registry

### `test_backup.py`
- `backup()` erstellt Datei mit korrektem Zeitstempel-Namen
- `backup()` erstellt `backup_dir` wenn nicht vorhanden
- Backup-Datei ist eine gültige Kopie (Byte-identisch)

### `test_hotkey_manager.py`
- `register()` + `unregister_all()` ohne Fehler (mock `ctypes.windll`)
- `triggered`-Signal wird bei simuliertem `WM_HOTKEY`-Event emittiert
- Kein Crash wenn Hotkey bereits belegt (n > verfügbare Kategorien)

---

## Constraints & Non-Goals

- Kein automatisches Löschen alter Backups
- Packaging ist ein manueller Build-Schritt (kein CI)
- Autostart zeigt keine Fehlermeldung wenn Registry-Schreiben fehlschlägt (nur logging)
- Hotkeys funktionieren nicht auf Remote-Desktop-Sessions (Windows-Einschränkung)
