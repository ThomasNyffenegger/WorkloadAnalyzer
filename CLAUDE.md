# WorkloadAnalyzer — Claude Code Context

> Lies zuerst `STATUS.md` für den aktuellen Projektstatus und die Roadmap.

## Projekt-Überblick

Windows-Tray-App zur automatischen Zeiterfassung. Erfasst, welche Kategorie (Aufgabe/Rolle) gerade aktiv ist. Erkennt Outlook-Termine, Bildschirmsperren und Inaktivität automatisch.

**Stack:** Python 3.11+, PyQt6, SQLite (WAL), openpyxl, pytest  
**Entry Point:** `src/workload_analyzer/__main__.py` → `app.run()`  
**Installer:** Nuitka + Inno Setup (`installer/WorkloadAnalyzer.iss`) — switched from PyInstaller after Windows Defender flagged its self-extracting bootloader as `Trojan:Win32/Bearfoos.B!ml` / `Trojan:Script/Wacatac.H!ml` (ML heuristic false positives); Nuitka compiles to native code and doesn't trigger them.

## Architektur

```
app.py              — Startup, alle Komponenten verkabeln, Event-Handler
core/tracker.py     — TimeTracker: start/stop/pause/resume/switch_to, Status-State-Machine
db/
  connection.py     — SQLite-Connect (WAL + synchronous=NORMAL aktiviert)
  repository.py     — Alle DB-Zugriffe (kein SQL in anderen Modulen)
  schema.sql        — CREATE TABLE / INDEX (inkl. Partial-Index WHERE end_ts IS NULL)
models.py           — Datenklassen: Category, Role, TimeEntry, EntrySource (Enum)
paths.py            — db_path() → AppData-Pfad
services/
  outlook_monitor.py    — COM-Polling in QThread (_OutlookWorker), Signale: category_detected, meeting_started/ended, availability_changed
  system_monitor.py     — WTS-Events (Lock/Unlock) + GetLastInputInfo (Idle), QAbstractNativeEventFilter
  hotkey_manager.py     — GlobalHotkeyManager, Ctrl+Shift+1..9
  autostart.py          — Scheduled Task ("At log on") via Task Scheduler COM API — NOT the registry Run key (silently ignored on this managed machine) and NOT schtasks.exe (blocked by policy); see STATUS.md/memory for why
  backup.py             — Startup-Dateikopie
  export.py             — XLSX-Pivot (Tage × Kategorien)
ui/
  tray.py               — TrayIcon, Tray-Menü, Blink-Timer, invalidate_categories()
  floating_widget.py    — Always-on-top Widget, Drag, State-Cache, invalidate_categories()
  settings_window.py    — Tabs: Kategorien, Rollen, Outlook, System, Backup, Autostart
  suggestion_popup.py   — Auto-Close 10s Countdown, SUGGESTION_YES/NO/NEVER
  recovery_popup.py     — Nach Lock/Idle: Kategorie-Dropdown (vorherige vorgewählt) + Buchen/Verwerfen-Buttons
  import_outlook_dialog.py — Outlook-Kategorien importieren → neue Kategorien anlegen
  reports_window.py     — Berichte mit Datumsfilter + XLSX-Export
```

## Wichtige Invarianten

- **Kein SQL außerhalb von `repository.py`** — alle DB-Zugriffe laufen durch `Repository`
- **COM-Calls nur im `_OutlookWorker`-Thread** — nie im Main-Thread (blockiert UI)
- **`_switch_menu_dirty` nur via `tray.invalidate_categories()`** — nie direkt von außen setzen
- **`floating_widget.invalidate_categories()`** nach `open_settings()` aufrufen — damit Kategorie-Cache aktualisiert wird
- **`repo.insert_closed_entry()` kann `OverlapError` werfen** — immer in try/except wrappen
- **Tracker-State** ist die einzige Source of Truth für die laufende Erfassung — nie direkt DB abfragen

## Tests ausführen

```bash
python -m pytest tests/ -x -q
```

132 Tests, alle in < 10s. Keine externen Abhängigkeiten (COM/Windows-APIs werden gemockt).

## Installer bauen

**Build braucht ein venv ausserhalb von OneDrive** — nicht nur `--output-dir`. Nuitkas eigener Compiler-Cache (`clcache`) bricht reihenweise mit "preprocessor failed" ab, wenn Nuitka/das venv selbst innerhalb des OneDrive-synchronisierten Ordners liegt (OneDrive-Datei-Locks, gleiche Ursache wie beim alten PyInstaller-Problem, trifft hier aber die venv-Include-Pfade, nicht nur `dist/`/`build/`).

Einmalig einrichten:

```bash
python -m venv "C:\Users\<user>\wab\venv"
"C:\Users\<user>\wab\venv\Scripts\pip" install nuitka "PyQt6>=6.6" "openpyxl>=3.1" "matplotlib>=3.8" "pywin32>=306"
"C:\Users\<user>\wab\venv\Scripts\pip" install --no-deps -e .
```

Build (aus dem Projektverzeichnis heraus, aber mit dem externen venv):

```bash
"C:\Users\<user>\wab\venv\Scripts\python" -m nuitka \
  --mode=standalone \
  --windows-console-mode=disable \
  --enable-plugin=pyqt6 \
  --disable-cache=ccache \
  --include-data-files=src/workload_analyzer/db/schema.sql=workload_analyzer/db/schema.sql \
  --output-dir="C:\Users\<user>\wab\nuitka" \
  --output-filename=WorkloadAnalyzer.exe \
  --company-name=WorkloadAnalyzer --product-name=WorkloadAnalyzer \
  --file-version=1.0.0.0 --product-version=1.0.0.0 \
  --assume-yes-for-downloads \
  src/workload_analyzer/__main__.py
```

**PIL nicht ausschliessen** — `--nofollow-import-to=PIL` sieht nach sinnvoller Verschlankung aus (Pillow wird nirgends direkt importiert), bricht aber matplotlib komplett (`matplotlib.colors` importiert PIL fest beim Modul-Load). Erst getestet mit einem Mini-Repro-Skript, bevor der volle Build läuft, spart Zeit.

Ergebnis zurück ins Projekt kopieren (Inno Setups `Source:` erwartet `..\dist\WorkloadAnalyzer\*` relativ zu `installer/`), dann kompilieren:

```bash
cp -r "C:\Users\<user>\wab\nuitka\__main__.dist" dist/WorkloadAnalyzer
"C:\Users\<user>\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer/WorkloadAnalyzer.iss
# → installer/Output/WorkloadAnalyzer_Setup.exe
```

ISCC.exe-Pfad hängt vom Install-Modus ab: per-user (winget-Standard) liegt es unter `%LOCALAPPDATA%\Programs\Inno Setup 6`, ein systemweiter Install unter `C:\Program Files (x86)\Inno Setup 6`.

Vor dem Verteilen empfiehlt sich ein gezielter Defender-Scan gegen die frisch gebaute Setup.exe (`Start-MpScan -ScanType CustomScan -ScanPath ...`), um False Positives früh zu erkennen statt erst beim Nutzer.

## Neue Phase starten

```
"Lass uns Phase N brainstormen"
→ Skill: superpowers:brainstorming → Design-Spec → superpowers:writing-plans → superpowers:subagent-driven-development
```
