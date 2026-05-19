# Phase 6: UX-Verbesserungen & Bugfixes — Design Spec

**Date:** 2026-05-19
**Status:** Approved

---

## Overview

Phase 6 adressiert echtes Nutzungs-Feedback nach dem ersten produktiven Einsatz. Sieben Bereiche werden verbessert:

1. **Outlook-Threading** — COM-Poll in Background-Thread, kein UI-Blocking mehr
2. **Suggestion-Popup** — Auto-Close nach 10s (→ Ja) + gleiche Kategorie unterdrücken
3. **Import-Dialog** — Sortierbare Spalten, „Alle auswählen", Buttons bei fehlender Rolle disablen
4. **Kategorien-Editor** — Tabelle read-only, Rolle als Dropdown, sortierbare Spalten
5. **Floating Widget** — Drag-Fix, Kategorienfarbe als Hintergrundstreifen, Ausblenden-Button
6. **Tray** — Widget einblenden via Rechtsklick-Menü und Doppelklick

Keine DB-Schema-Änderungen. Keine neuen Fenster.

---

## Architecture

### Modified Files

```
src/workload_analyzer/services/outlook_monitor.py   # QThread worker
src/workload_analyzer/ui/suggestion_popup.py        # Auto-close countdown
src/workload_analyzer/app.py                        # Same-category check
src/workload_analyzer/ui/import_outlook_dialog.py   # Sortable, select-all, disable
src/workload_analyzer/ui/settings_window.py         # Category editor fixes
src/workload_analyzer/ui/floating_widget.py         # Drag fix, color strip, hide button
src/workload_analyzer/ui/tray.py                    # Show widget from tray
```

### New Files

```
tests/test_outlook_monitor_threading.py             # Threading smoke tests
```

---

## Feature 1: Outlook-Threading

### Problem
`OutlookMonitor._poll()` läuft auf dem Haupt-Thread via `QTimer`. Die Kalender-Iteration (`for item in folder.Items`) blockiert die Qt-Eventloop und friert die UI ein.

### Design
`OutlookMonitor` bekommt einen internen `_OutlookWorker(QObject)` der in einem `QThread` lebt. Alle COM-Calls finden im Worker-Thread statt. Qt's `AutoConnection` transportiert Signale automatisch thread-safe zurück an den Haupt-Thread.

```
Haupt-Thread:
  OutlookMonitor (QObject)
    start() / stop() / set_interval()   ← öffentliche API unverändert
    category_detected, meeting_started,
    meeting_ended, availability_changed  ← Signale unverändert

Worker-Thread (QThread):
  _OutlookWorker (QObject)
    QTimer → _poll() → COM-Calls
    pythoncom.CoInitialize() bei thread.started
    pythoncom.CoUninitialize() bei thread.finished
```

`OutlookMonitor.start()` startet den Thread und schickt dem Worker via Signal den Startbefehl. `stop()` stoppt den Worker-Timer und beendet den Thread (`quit()` + `wait()`). `set_interval()` schickt den neuen Wert per Signal an den Worker.

`app.py` muss nicht geändert werden — die öffentliche API von `OutlookMonitor` bleibt identisch.

### Injectable Dependencies
`OutlookMonitor(outlook_factory=None)` bleibt erhalten. Der Worker übernimmt die Factory.

---

## Feature 2: Suggestion Popup

### 2a) Popup unterdrücken
In `app.py`, im Handler für `category_detected`: vor dem Öffnen des Popups werden zwei Fälle geprüft — beide führen zu stillem Verwerfen ohne Popup:

1. **Kein Mapping vorhanden:** Die erkannte Outlook-Kategorie hat keine zugeordnete App-Kategorie (`suggested_category_id is None`) → kein Popup.
2. **Gleiche Kategorie:** `suggested_category_id == tracker.current_state().category_id` → kein Popup.

### 2b) Auto-Close nach 10s → Ja
`SuggestionPopup` bekommt einen `QTimer` (1s-Intervall, 10 Ticks). Der „Ja"-Button zeigt einen Countdown: `"Ja (10)"` → `"Ja (9)"` → … → `"Ja (1)"`. Nach dem 10. Tick: `self.done(SUGGESTION_YES)`. Der Countdown wird gestoppt sobald der Nutzer eine Taste drückt oder einen Button klickt.

```python
# Pseudocode
self._countdown = 10
self._timer = QTimer(self)
self._timer.timeout.connect(self._tick)
self._timer.start(1000)

def _tick(self):
    self._countdown -= 1
    yes_btn.setText(f"Ja ({self._countdown})")
    if self._countdown <= 0:
        self.done(SUGGESTION_YES)
```

---

## Feature 3: Import-Dialog

### 3a) Sortierbare Spalten
`self._table.setSortingEnabled(True)`. Sinnvoll sortierbar ist Spalte 0 (Outlook-Name, Text). Spalten 1–3 haben Widgets — Qt sortiert nach `QTableWidgetItem`-Text, diese Spalten bleiben leer (kein `QTableWidgetItem`), also kein Effekt beim Klick.

### 3b) „Alle auswählen"-Button
Button `"Alle auswählen"` neben dem Beschriftungs-Label. Erster Klick: alle Checkboxen checked. Zweiter Klick: alle unchecked (Toggle via `_all_selected: bool`).

```python
def _toggle_all(self):
    self._all_selected = not self._all_selected
    for row in range(self._table.rowCount()):
        cb = self._table.cellWidget(row, 2).findChild(QCheckBox)
        cb.setChecked(self._all_selected)
    self._select_all_btn.setText(
        "Alle abwählen" if self._all_selected else "Alle auswählen"
    )
```

### 3c) Buttons disablen ohne Rolle
Beim Aufbau der UI wird geprüft: `if not self._roles`. Falls wahr:
- OK-Button (`btns.button(QDialogButtonBox.StandardButton.Ok)`) → `setEnabled(False)`
- Hinweistext `"⚠ Bitte zuerst eine Rolle anlegen."` unter der Tabelle, in orange

---

## Feature 4: Kategorien-Editor

### 4a) Tabelle read-only
`self.cat_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)`

Dies verhindert Inline-Editierung per Doppelklick. Alle Änderungen laufen über den „Bearbeiten"-Button.

### 4b) Rolle als Dropdown im Bearbeiten-Dialog
Im `_CategoryEditDialog` (der Dialog der beim „Bearbeiten"-Button öffnet): Das Rollen-Feld wird von `QLineEdit` auf `QComboBox` umgestellt. Die Combo enthält alle vorhandenen Rollen (`repo.list_roles()`). Beim Öffnen wird die aktuelle Rolle vorausgewählt.

### 4c) Sortierbare Spalten
`self.cat_table.setSortingEnabled(True)` — Klick auf Spaltenheader sortiert die Kategorientabelle.

---

## Feature 5: Floating Widget

### 5a) Drag-Fix
Eine schmale Titelzeile (`QLabel`, Text `"≡"`) ganz oben im Widget übernimmt `mousePressEvent` / `mouseMoveEvent` / `mouseReleaseEvent`. Die bestehenden Drag-Methoden auf dem Hauptwidget werden entfernt — nur die Titelzeile ist der Drag-Anker. Combo und Button konsumieren keine Drag-Events mehr.

### 5b) Kategorienfarbe als Hintergrundstreifen
Die mittlere Zeile (Kategoriename + Rollenname) wird in einem `QWidget` (`self._color_strip`) eingebettet, dessen `styleSheet` beim Tracking auf `background-color: <cat.color>` gesetzt wird. Bei „Not tracking": `background-color: #444`. Übergang erfolgt sofort beim `refresh()`.

```python
self._color_strip.setStyleSheet(f"background-color: {cat.color}; border-radius: 4px;")
```

### 5c) Ausblenden-Button
Kleiner `QPushButton("✕")` rechts in der Titelzeile (neben dem Drag-Label). `setFixedWidth(20)`. Klick: `self.hide()`. Zustand wird nicht persistiert — nach App-Neustart ist das Widget wieder sichtbar.

---

## Feature 6: Tray — Widget einblenden

### Rechtsklick-Menü
`tray.py`: Neuer Eintrag `"Widget anzeigen"` im Kontextmenü. Aktion: `floating_widget.show()` + `floating_widget.raise_()`. Der Eintrag ist nur sichtbar wenn `not floating_widget.isVisible()`.

Alternativ: immer sichtbar, aber Text wechselt zwischen `"Widget ausblenden"` / `"Widget anzeigen"`.

→ **Gewählt: immer sichtbar, Text wechselt** — einfacher, keine Menü-Neukonstruktion nötig.

### Doppelklick
`QSystemTrayIcon.activated` Signal: bei `ActivationReason.DoubleClick` → `floating_widget.show()` + `raise_()`.

---

## Out of Scope

- Keine anderen Popup-Typen (RecoveryPopup, MeetingCategoryDialog) erhalten Auto-Close
- Keine Animation beim Ein-/Ausblenden des Floating Widget
- Kein persistierter Hide-Zustand (Widget startet immer sichtbar)

---

## Estimated Tasks

| # | Task | Files |
|---|------|-------|
| 1 | Outlook-Threading: `_OutlookWorker` + `QThread` | `outlook_monitor.py`, `test_outlook_monitor_threading.py` |
| 2 | Suggestion Popup: Auto-Close + gleiche Kategorie unterdrücken | `suggestion_popup.py`, `app.py` |
| 3 | Import-Dialog: Sortierbar + Select-All + Disable | `import_outlook_dialog.py` |
| 4 | Kategorien-Editor: Read-only + Dropdown + Sortierbar | `settings_window.py` |
| 5 | Floating Widget: Drag-Fix + Farbstreifen + Ausblenden | `floating_widget.py`, `tray.py` |
