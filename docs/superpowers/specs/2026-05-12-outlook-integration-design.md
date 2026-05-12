# WorkloadAnalyzer Phase 2 — Outlook Integration Design Spec

**Datum:** 2026-05-12
**Status:** Approved (Design)

## 1. Ziel

Phase 2 ergänzt die manuelle Zeiterfassung um automatische Kategorie-Erkennung via klassisches Outlook (COM). Die App pollt Outlook alle 15 Sekunden, erkennt die aktive Mail/Aufgabe sowie laufende Kalendertermine und schlägt dem Benutzer einen Kategorie-Wechsel vor. Manuelle Kontrolle bleibt jederzeit möglich.

## 2. Neue Komponenten

```
src/workload_analyzer/
  services/
    outlook_monitor.py          # NEU — COM-Polling, Qt-Signals
  ui/
    suggestion_popup.py         # NEU — Vorschlags-Dialog
    import_outlook_dialog.py    # NEU — Kategorie-Import aus Outlook
  db/
    repository.py               # ERWEITERT — rejected_suggestions CRUD
  ui/
    settings_window.py          # ERWEITERT — Outlook-Tab
  app.py                        # ERWEITERT — Monitor starten, Signals verdrahten
```

## 3. OutlookMonitor

### 3.1 Klasse

`OutlookMonitor(QObject)` in `services/outlook_monitor.py`.

Läuft im **Main-Thread** via `QTimer` (alle 15s, konfigurierbar). Kein separater Thread — COM-Aufrufe dauern <50ms und blockieren die UI nicht spürbar.

### 3.2 Signals

| Signal | Parameter | Bedeutung |
|--------|-----------|-----------|
| `category_detected` | `str` | Outlook-Kategoriename des aktiven Inspectors |
| `meeting_started` | `str, Optional[str]` | Titel des Termins + Outlook-Kategorie (oder None) |
| `meeting_ended` | — | Laufender Termin ist beendet |
| `availability_changed` | `bool` | True = Outlook verfügbar, False = nicht erreichbar |

### 3.3 Polling-Logik

1. `win32com.client.GetActiveObject("Outlook.Application")` — schlägt fehl wenn Outlook zu → `availability_changed(False)`.
2. **Aktiver Inspector:** `app.ActiveInspector()` — falls offen, lies `inspector.CurrentItem.Categories` (erstes Element, Komma-getrennt).
3. **Laufender Termin:** Iteriere `app.GetNamespace("MAPI").GetDefaultFolder(9).Items` (Kalender-Ordner), prüfe ob `item.Start <= now <= item.End`. Erkenne Start und Ende separat.
4. **Debounce:** Signal `category_detected` wird nur gefeuert wenn sich die erkannte Kategorie gegenüber dem letzten Poll geändert hat. Gleiches gilt für `meeting_started`/`meeting_ended`.

### 3.4 Fehlerbehandlung

Jeder COM-Aufruf in `try/except Exception` (fängt `pywintypes.com_error` und alle anderen COM-Fehler). Bei Fehler: `availability_changed(False)` emittieren, interner State zurücksetzen, beim nächsten Poll automatisch retry.

### 3.5 Testbarkeit

`OutlookMonitor.__init__` akzeptiert einen optionalen `outlook_factory: callable` Parameter. Default: `lambda: win32com.client.GetActiveObject("Outlook.Application")`. Tests injizieren einen Fake.

### 3.6 Start/Stop

- `monitor.start()` → startet QTimer
- `monitor.stop()` → stoppt QTimer
- `app.py` ruft `start()` beim App-Start, `stop()` beim Beenden

## 4. Vorschlags-Popup

### 4.1 Klasse

`SuggestionPopup(QDialog)` in `ui/suggestion_popup.py`.

### 4.2 Verhalten

- Erscheint wenn `category_detected` gefeuert wird **und** die Kombination nicht silenced ist.
- Inhalt: *"Outlook erkennt: \<Outlook-Kategorie\> → \<App-Kategorie\>. Übernehmen?"*
- Falls keine App-Kategorie für den Outlook-Namen gemappt ist: kein Popup (stillschweigend ignorieren).
- Buttons: **Ja** / **Nein** / **Nie mehr**
- Kein Auto-Close — bleibt offen bis Benutzer antwortet.
- Wenn ein Popup bereits offen ist und eine neue Erkennung kommt → altes ohne Reaktion schliessen, neues öffnen.

### 4.3 Reaktion auf Buttons

| Button | Aktion |
|--------|--------|
| Ja | `tracker.switch_to(category_id)` mit `source=AUTO_OUTLOOK`, Popup schliessen |
| Nein | `repo.record_rejection(outlook_name, app_category_id)`, Popup schliessen |
| Nie mehr | `repo.record_rejection(outlook_name, app_category_id, immediate_silence=True)`, Popup schliessen |

## 5. Meeting-Lock

### 5.1 Ablauf

1. `meeting_started(title, outlook_category)` empfangen.
2. Wenn `outlook_category` vorhanden und gemappt → `tracker.switch_to()` mit `source=AUTO_MEETING`, kein Popup.
3. Wenn keine Kategorie → `MeetingCategoryDialog` öffnen (blockierender Dialog, Dropdown mit allen aktiven Kategorien, kein Timeout).
4. `meeting_ended` → Lock aufgehoben, Monitor übernimmt normal weiter.

### 5.2 Manueller Override

Während Meeting-Lock: Benutzer kann jederzeit per Tray-Menü oder Floating Widget die Kategorie wechseln (`source=MANUAL_OVERRIDE`). Der Lock bleibt aktiv (d.h. `meeting_ended` wird weiterhin verarbeitet).

### 5.3 MeetingCategoryDialog

Einfacher `QDialog` mit Titel *"Meeting '\<Titel\>' gestartet. Welche Kategorie?"*, `QComboBox` mit aktiven Kategorien, OK-Button. Kein Abbrechen (Pflichtfeld). Gehört direkt in `suggestion_popup.py`.

## 6. Lernfunktion (rejected_suggestions)

### 6.1 Repository-Erweiterungen

Neue Methoden in `Repository`:

| Methode | Signatur | Beschreibung |
|---------|----------|--------------|
| `record_rejection` | `(outlook_name: str, app_category_id: int, immediate_silence: bool = False) -> None` | Zählt Ablehnung hoch. Bei `immediate_silence=True` oder `rejection_count >= 3`: setzt `silenced=True`. |
| `is_silenced` | `(outlook_name: str, app_category_id: int) -> bool` | Gibt True zurück wenn silenced. |
| `list_rejected_suggestions` | `() -> list[RejectedSuggestion]` | Alle Einträge. |
| `set_silenced` | `(suggestion_id: int, silenced: bool) -> None` | Reaktivierung oder manuelles Stummschalten. |

### 6.2 Model

`RejectedSuggestion(id, outlook_category_name, app_category_id, rejection_count, silenced, last_rejected_at)` in `models.py`.

### 6.3 Prüfung vor Popup

`_on_category_detected(outlook_name)`:
1. `cat = repo.find_category_by_outlook_name(outlook_name)` — kein Match → ignorieren
2. `repo.is_silenced(outlook_name, cat.id)` → True → ignorieren
3. Sonst → `SuggestionPopup` öffnen

## 7. Settings-Erweiterungen

### 7.1 Neuer Tab "Outlook"

Im `SettingsWindow` wird ein dritter Tab *"Outlook"* ergänzt mit:

- **Poll-Intervall:** `QSpinBox` (5–60s, Default 15), gespeichert als `outlook_poll_seconds` in `settings`-Tabelle. Änderung → `monitor.set_interval(seconds)`.
- **Button "Aus Outlook importieren"** → öffnet `ImportOutlookDialog`.
- **Tabelle der stummgeschalteten Erkennungen:** Spalten: Outlook-Name, App-Kategorie, Anzahl Ablehnungen, Status (Aktiv/Stumm). Pro Zeile: Button "Reaktivieren" / "Stumm schalten".

### 7.2 Tray-Icon Farbe

`TrayIcon.refresh()` bekommt einen zusätzlichen Parameter `outlook_available: bool`. Wenn `False` → Icon-Farbe orange (statt der Kategoriefarbe). Bereits vorbereitet in Phase 1 (refresh-Methode existiert).

## 8. ImportOutlookDialog

`ImportOutlookDialog(QDialog)` in `ui/import_outlook_dialog.py`:

1. Öffnen: liest `namespace.Categories` via COM → Liste aller Outlook-Kategorien (Name + Farbe).
2. Tabelle: Outlook-Name, Farbpunkt, Checkbox "importieren", Dropdown "App-Kategorie zuweisen" (Einträge: "Neu anlegen" + alle bestehenden App-Kategorien).
3. OK:
   - Für jede gecheckte Zeile mit "Neu anlegen": `repo.create_category(name=outlook_name, color=outlook_color, role_id=<erste Rolle>, outlook_category_name=outlook_name)`.
   - Für jede gecheckte Zeile mit bestehender Kategorie: `repo.update_category(..., outlook_category_name=outlook_name)`.
4. Fehler (Outlook nicht verfügbar): Fehlermeldung, Dialog nicht öffnen.

## 9. Verdrahtung in app.py

```python
monitor = OutlookMonitor(repo)
monitor.category_detected.connect(_on_category_detected)
monitor.meeting_started.connect(_on_meeting_started)
monitor.meeting_ended.connect(_on_meeting_ended)
monitor.availability_changed.connect(tray.set_outlook_available)
monitor.start()
```

`_on_category_detected(outlook_name)`:
- Prüft silenced, öffnet SuggestionPopup, schließt vorheriges Popup falls nötig.

`_on_meeting_started(title, outlook_category)`:
- Wechselt Kategorie direkt oder öffnet MeetingCategoryDialog.

`_on_meeting_ended()`:
- Hebt Meeting-Lock auf.

## 10. Teststrategie

### 10.1 Fake-Outlook-Objekte

```python
class FakeItem:
    def __init__(self, categories="", start=None, end=None):
        self.Categories = categories
        self.Start = start
        self.End = end

class FakeInspector:
    def __init__(self, item): self.CurrentItem = item

class FakeNamespace:
    def __init__(self, appointments): self._appts = appointments
    def GetDefaultFolder(self, _): return FakeFolder(self._appts)

class FakeFolder:
    def __init__(self, items): self.Items = items

class FakeOutlookApp:
    def __init__(self, inspector=None, appointments=None):
        self._inspector = inspector
        self._appointments = appointments or []
    def ActiveInspector(self): return self._inspector
    def GetNamespace(self, _): return FakeNamespace(self._appointments)
```

### 10.2 Testfälle

| Test | Was wird geprüft |
|------|-----------------|
| `test_category_detected_on_inspector` | Signal `category_detected` wird emittiert wenn Inspector Kategorie hat |
| `test_no_duplicate_signal` | Signal wird nicht nochmal emittiert wenn Kategorie unverändert |
| `test_availability_false_on_error` | `availability_changed(False)` bei COM-Fehler |
| `test_meeting_started_signal` | `meeting_started` wenn jetzt in Termin-Zeitraum |
| `test_meeting_ended_signal` | `meeting_ended` wenn Termin abgelaufen |
| `test_record_rejection_silences_after_3` | Nach 3 `record_rejection`-Calls: `is_silenced=True` |
| `test_immediate_silence` | `record_rejection(immediate_silence=True)` → sofort silenced |
| `test_on_category_detected_ignores_silenced` | Kein Popup bei silenced Kombination |
| `test_on_category_detected_ignores_no_mapping` | Kein Popup wenn kein Outlook→App-Mapping |

## 11. Abhängigkeiten

`pywin32` zur `pyproject.toml` dependencies hinzufügen. Nur auf Windows verfügbar — Tests mit Fakes laufen auf allen Plattformen.
