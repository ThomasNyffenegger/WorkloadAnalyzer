# WorkloadAnalyzer — Projektstatus & Roadmap

> **Für neue Sessions:** Lies diese Datei als erstes. Sie beschreibt was fertig ist und was als nächstes kommt.

---

## Fertig (Phase 1–5)

| Phase | Feature | Plan | Spec |
|-------|---------|------|------|
| 1 | **MVP** — Zeiterfassung, Kategorien/Rollen, Floating Widget, System Tray, Einstellungen, einfache Berichte | `plans/2026-05-11-workload-analyzer-mvp.md` | `specs/2026-05-11-workload-analyzer-design.md` |
| 2 | **Outlook-Integration** — COM-basierter OutlookMonitor, Vorschlag-Popup (SuggestionPopup), Kalender-Import-Dialog, Outlook-Tab in Einstellungen | `plans/2026-05-12-outlook-integration.md` | `specs/2026-05-12-outlook-integration-design.md` |
| 3 | **System Monitoring** — Bildschirmsperre (WTS-Events), Idle-Erkennung (GetLastInputInfo), RecoveryPopup (vorherige/andere/verwerfen), `stop_at()` im Tracker, Idle-Schwellwert in Einstellungen | `plans/2026-05-13-system-monitoring.md` | `specs/2026-05-13-system-monitoring-design.md` |
| 4 | **Berichte & Analysen** — `export_xlsx_pivot()` (Tage × Kategorien XLSX), 4 Schnellauswahl-Buttons (Heute/Diese Woche/Diesen Monat/Letzten Monat), Export-Pivot-XLSX-Button | `plans/2026-05-14-reports-analytics.md` | `specs/2026-05-14-reports-analytics-design.md` |
| 5 | **Produktionsreife** — Autostart (Registry), Backup (startup copy), Globale Hotkeys (Ctrl+Shift+1..9), Tray-Reminder (blink nach 2h), PyInstaller+Inno Setup Installer | `plans/2026-05-14-production-readiness.md` | `specs/2026-05-14-production-readiness-design.md` |

**Tests:** 123 passing. Stack: Python 3.11+, PyQt6, SQLite, openpyxl, pytest.

---

## Spec-Schulden (aus Phase-1-Spec, nie implementiert)

Features die in `specs/2026-05-11-workload-analyzer-design.md` beschrieben sind, aber in keinem Plan standen und fehlen:

| Feature | Spec-Abschnitt | Status |
|---------|---------------|--------|
| **Packaging** — PyInstaller + Inno Setup Windows-Installer | §2 Tech Stack | ❌ fehlt |
| **Hotkeys** — `Ctrl+Shift+1..9` für Schnellkategorien (Kategorie 1–9 direkt wechseln) | §4.4 Settings | ❌ fehlt |
| **Backup** — konfigurierbarer Backup-Pfad + automatisches Backup beim Start | §4.4 Settings | ❌ fehlt |
| **Autostart** — App mit Windows starten (Registry `HKCU\...\Run`) | §4.4 Settings | ❌ fehlt |
| **Tray-Reminder** — pulsierendes Icon nach 2h ohne Kategoriewechsel | §4.4 Tray | ❌ fehlt (orange bei Outlook-Verlust ist ✅) |

Bereits implementiert (fälschlicherweise als fehlend gemeldet):
- ✅ „Aus Outlook importieren" in Settings — Phase 2 (`ImportOutlookDialog`)
- ✅ `rejected_suggestions` reaktivierbar — Phase 2 (Reaktivieren-Button in Settings)

**Empfehlung:** Spec-Schulden als eigene kompakte Phase (z.B. „Phase 5: Produktionsreife") bündeln — passt gut zusammen (Hotkeys + Autostart + Backup + Packaging sind alle Einstellungs-/Infrastruktur-Themen).

---

## Vorgeschlagene nächste Phasen

### Phase 5 — Produktionsreife (Spec-Schulden)
**Aufwand:** Gering–Mittel | **Wert:** Hoch (Nutzbarkeit im Alltag)

Bündelt alle offenen Spec-Schulden aus Phase 1 zu einer deployable App:

- **Autostart:** Registry-Eintrag `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` → Checkbox in Einstellungen
- **Backup:** Einstellbarer Backup-Pfad + automatisches Kopieren der SQLite-DB beim Start (mit Zeitstempel)
- **Hotkeys:** `Ctrl+Shift+1..9` wechseln direkt zur n-ten Kategorie — via `QShortcut` (kein externer Hook nötig)
- **Tray-Reminder:** Pulsierendes Icon (Timer-basierter Icon-Wechsel) wenn > 2h keine Kategorieänderung
- **Packaging:** PyInstaller → `.exe`, Inno Setup → Windows-Installer `.exe`

Keine DB-Änderungen, keine neuen Fenster.

---

### Phase 6 — Tagesansicht (Timeline)
**Aufwand:** Mittel | **Wert:** Hoch

Visuelle Tages-Timeline im Berichte-Fenster (neuer Tab). Zeigt Zeitblöcke als horizontales Gantt-Diagramm über 24h, farblich nach Kategorie. Ideal um auf einen Blick zu sehen, wie der Tag verteilt war — und wo Lücken (unerfasste Zeit) sind.

- Neuer Tab "Timeline" in `ReportsWindow`
- Matplotlib-basiert (bereits vorhanden) oder QPainter
- Keine DB-Änderungen

---

### Phase 7 — Ziele & Budgets
**Aufwand:** Mittel | **Wert:** Hoch

Wöchentliche Stundenbudgets pro Kategorie oder Rolle definieren. Fortschritt wird in Berichte und optional im Floating Widget angezeigt (z.B. "Coding: 12/20h").

- Neue DB-Tabelle `budgets` (category_id / role_id, hours_per_week)
- Budget-Tab in Einstellungen
- Fortschrittsbalken im Bericht
- Optional: Warnung wenn Budget überschritten

---

### Phase 8 — Aktives-Fenster-Tracking
**Aufwand:** Mittel | **Wert:** Hoch

Überwacht den Titel des aktiven Fensters (`GetForegroundWindow` / `GetWindowText`) und schlägt automatisch eine Kategorie vor, basierend auf konfigurierbaren Regeln (z.B. "Visual Studio Code" → Coding, "Zoom" → Meetings).

- Neuer Service `window_monitor.py` (ähnlich `outlook_monitor.py`)
- Regeleditor in Einstellungen (App-Titel → Kategorie)
- Nutzt bestehenden `SuggestionPopup` wieder
- Keine DB-Änderungen

---

### Phase 9 — Datenpflege & Portabilität
**Aufwand:** Gering–Mittel | **Wert:** Mittel

Werkzeuge für langfristige Datenhygiene:
- Kategorien zusammenführen (merge) oder umbenennen ohne Datenverlust
- Einträge bulk-bearbeiten (Kategorie ändern für einen Zeitraum)
- Datenbank-Backup/Restore (Datei kopieren mit Zeitstempel)
- JSON-Export aller Daten (für externe Auswertung)

---

### Phase 10 — Schnelleingabe & Globaler Hotkey
**Aufwand:** Gering | **Wert:** Mittel

Globaler Hotkey (z.B. `Ctrl+Shift+T`) öffnet ein minimales Overlay zum Kategorienwechsel, ohne das Hauptfenster zu öffnen. Ergänzt das Floating Widget für Power-User.

- `keyboard`-Library oder Windows-Hook
- Mini-Dialog (ähnlich Spotlight/Alfred)
- Konfigurierbare Tastenkombination in Einstellungen

---

## Empfohlene Reihenfolge

```
Phase 5  (Produktionsreife)  ← Spec-Schulden abbauen, App deploybar machen
Phase 6  (Timeline)          ← visueller Impact, baut auf Reports auf
Phase 8  (Window Tracking)   ← reduziert Erfassungsaufwand am stärksten
Phase 7  (Ziele/Budgets)     ← macht Daten actionable
Phase 9  (Datenpflege)       ← wichtig für Langzeitnutzung
Phase 10 (Hotkey/Quick)      ← Quality of Life
```

---

## Wie man eine neue Phase startet

```
1. In Claude Code / Desktop: "Lass uns Phase N brainstormen"
2. Skill: brainstorming → Design-Spec → Plan
3. Skill: subagent-driven-development → Umsetzung
```
