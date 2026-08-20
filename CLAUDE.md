# WorkloadAnalyzer — Claude Code Context

> Lies zuerst `STATUS.md` für den aktuellen Projektstatus und die Roadmap.

## Projekt-Überblick

Windows-Tray-App zur automatischen Zeiterfassung. Erfasst, welche Kategorie (Aufgabe/Rolle) gerade aktiv ist. Erkennt Outlook-Termine, Bildschirmsperren und Inaktivität automatisch.

**Stack:** Python 3.11+, PyQt6, SQLite (WAL), openpyxl, pytest  
**Entry Point:** `src/workload_analyzer/__main__.py` → `app.run()`  
**Installer:** PyInstaller + Inno Setup (`WorkloadAnalyzer.spec` + `installer/WorkloadAnalyzer.iss`)

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
  autostart.py          — Registry HKCU\...\Run
  backup.py             — Startup-Dateikopie
  export.py             — XLSX-Pivot (Tage × Kategorien)
ui/
  tray.py               — TrayIcon, Tray-Menü, Blink-Timer, invalidate_categories()
  floating_widget.py    — Always-on-top Widget, Drag, State-Cache, invalidate_categories()
  settings_window.py    — Tabs: Kategorien, Rollen, Outlook, System, Backup, Autostart
  suggestion_popup.py   — Auto-Close 10s Countdown, SUGGESTION_YES/NO/NEVER
  recovery_popup.py     — Nach Lock/Idle: Vorherige/Andere/Verwerfen
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

PyInstaller-Build **ausserhalb** von OneDrive laufen lassen (OneDrive hält Datei-Locks auf `build/`/`dist/`, und lange Pfade sprengen die 260-Zeichen-Grenze):

```bash
python -m PyInstaller WorkloadAnalyzer.spec --noconfirm --distpath "C:\Users\<user>\wab\dist" --workpath "C:\Users\<user>\wab\build"
```

Ergebnis zurück ins Projekt kopieren (Inno Setups `Source:` erwartet `..\dist\WorkloadAnalyzer\*` relativ zu `installer/`), dann kompilieren:

```bash
cp -r "C:\Users\<user>\wab\dist\WorkloadAnalyzer" dist/WorkloadAnalyzer
"C:\Users\<user>\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer/WorkloadAnalyzer.iss
# → installer/Output/WorkloadAnalyzer_Setup.exe
```

ISCC.exe-Pfad hängt vom Install-Modus ab: per-user (winget-Standard) liegt es unter `%LOCALAPPDATA%\Programs\Inno Setup 6`, ein systemweiter Install unter `C:\Program Files (x86)\Inno Setup 6`.

## Neue Phase starten

```
"Lass uns Phase N brainstormen"
→ Skill: superpowers:brainstorming → Design-Spec → superpowers:writing-plans → superpowers:subagent-driven-development
```
