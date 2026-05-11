# WorkloadAnalyzer — Design Spec

**Datum:** 2026-05-11
**Status:** Approved (Design)

## 1. Ziel & Kontext

Eine Windows-Desktop-App zur **automatisierten Zeiterfassung**, die während des Arbeitens minimale Interaktion erfordert. Hauptziel: Transparenz darüber, wie viel Zeit auf welche **Rolle** und auf welches **Projekt/Tätigkeit (Kategorie)** entfällt.

Die App nutzt Microsoft Outlook (klassische Desktop-Version) als primäre Signalquelle: Kategorien von offenen Mails, Aufgaben und Kalenderterminen werden gelesen, um Tätigkeitswechsel automatisch zu erkennen und vorzuschlagen. Manuelles Umschalten bleibt jederzeit möglich.

## 2. Technologie-Stack

| Bereich | Wahl |
|---|---|
| Sprache | Python 3.11+ |
| GUI | PyQt6 |
| Outlook COM | pywin32 |
| Persistenz | SQLite (lokal, kein Cloud-Sync) |
| Charts | PyQtGraph oder matplotlib (in PyQt eingebettet) |
| Export | openpyxl (Excel), Standard csv-Modul |
| Packaging | PyInstaller (One-File) + Inno Setup (Installer) |
| Plattform | Windows 10/11 (klassisches Outlook erforderlich) |

Begründung: `pywin32` ist die ausgereifteste Outlook-Automation-Bibliothek. Python erlaubt schnelle Entwicklung; PyQt6 liefert alle benötigten UI-Komponenten (Tray, Floating Window, Charts) ohne Zusatzaufwand.

## 3. Datenmodell

### 3.1 Tabellen (SQLite)

**`roles`**
- `id` (PK), `name` (unique), `created_at`

**`categories`**
- `id` (PK), `name` (unique), `color` (hex), `role_id` (FK → roles), `active` (bool), `outlook_category_name` (optional, für Mapping zu Outlook), `created_at`

**`time_entries`**
- `id` (PK), `category_id` (FK → categories)
- `start_ts`, `end_ts` (UTC, Sekundenauflösung)
- `source` (enum: `auto_outlook`, `auto_meeting`, `manual`, `manual_override`, `screen_lock_recovery`, `idle_recovery`)
- `comment` (optional, Freitext)
- `created_at`, `modified_at`

**`outlook_references`**
- `id` (PK), `time_entry_id` (FK → time_entries)
- `outlook_item_id`, `subject`, `item_type` (mail/task/appointment)
- Nur zur Nachvollziehbarkeit gespeichert (Audit Trail)

**`rejected_suggestions`** (Lernfunktion)
- `id` (PK), `outlook_category_name`, `app_category_id`, `rejection_count`, `silenced` (bool), `last_rejected_at`
- Wenn `rejection_count >= 3` → `silenced = true`; in Einstellungen einsehbar und reaktivierbar

**`settings`** (Key/Value)
- z.B. `idle_threshold_minutes`, `poll_interval_seconds`, `rounding_minutes`, `backup_path`, `autostart_enabled`, `floating_widget_enabled`

### 3.2 Invarianten

- Zeiteinträge dürfen sich **nicht überlappen**. Beim Anlegen oder Editieren wird das geprüft und Kollisionen werden abgelehnt oder angrenzende Einträge entsprechend angepasst (Rundungslogik).
- Jeder `time_entry` hat genau eine Kategorie. Die Rolle ergibt sich aus der Kategorie.
- Bei Rundung gilt: Zeit darf nicht **doppelt verbucht** werden — Rundung verschiebt Grenzen, erzeugt aber keine überlappenden oder erweiterten Intervalle.

## 4. Komponenten-Architektur

```
┌────────────────────────────────────────────────────────┐
│                    WorkloadAnalyzer                    │
│                                                        │
│  ┌─────────────┐    ┌──────────────────────┐           │
│  │   Outlook   │───▶│    Time Tracker      │           │
│  │   Monitor   │    │  (Core State + DB)   │           │
│  └─────────────┘    └──────────────────────┘           │
│  ┌─────────────┐            │                          │
│  │   System    │────────────┤                          │
│  │   Monitor   │            │                          │
│  │ (Idle/Lock) │            │                          │
│  └─────────────┘            ▼                          │
│  ┌──────────────────────────────────────────┐          │
│  │     UI Layer (PyQt6)                     │          │
│  │  • Tray Icon  • Floating Widget          │          │
│  │  • Popups     • Settings  • Reports      │          │
│  └──────────────────────────────────────────┘          │
└────────────────────────────────────────────────────────┘
```

### 4.1 Outlook Monitor (Background-Thread)

- Pollt alle **15 Sekunden** (konfigurierbar) die Outlook-COM-Schnittstelle via pywin32.
- Erkennt:
  - **Aktiver Inspector**: welches Outlook-Element ist gerade im Vordergrund geöffnet (Mail, Aufgabe)? Liest dessen Kategorie.
  - **Laufender Kalendertermin**: aktuelle Uhrzeit liegt in Start/Ende eines Termins.
- Emittiert Signale: `category_detected`, `meeting_started`, `meeting_ended`, `outlook_unavailable`.

Wenn Outlook nicht läuft: Signal `outlook_unavailable` — Tracker läuft auf zuletzt aktiver Kategorie weiter, UI signalisiert das (Tray-Icon wechselt auf orange).

### 4.2 System Monitor

- Überwacht Windows-Events: Screen-Lock/Unlock via `WTS_SESSION_LOCK`/`WTS_SESSION_UNLOCK`.
- Überwacht Idle-Zeit (keine Maus/Tastatur) via `GetLastInputInfo`. Schwelle konfigurierbar (Default 10 Minuten).
- Emittiert Signale: `screen_locked`, `screen_unlocked`, `idle_detected`, `idle_ended`.

### 4.3 Time Tracker (Core)

Zentrale Zustandsmaschine. Hält:
- `current_category_id`
- `current_entry_start_ts`
- `is_paused`, `is_locked` (Meeting-Lock), `pause_reason`

Verarbeitet Events aus Outlook-Monitor, System-Monitor und UI. Schreibt `time_entries` in die DB beim Wechsel der Kategorie.

### 4.4 UI-Komponenten (PyQt6)

**Tray-Icon** (immer präsent):
- Tooltip zeigt aktuelle Kategorie + Rolle + Laufzeit
- Rechtsklick-Menü:
  - Aktuelle Kategorie + Laufzeit (Header)
  - Schnellwechsel zu definierten Kategorien (max. 10 zuletzt verwendete)
  - Lock ein/aus
  - Pause ein/aus
  - Floating Widget ein/ausblenden
  - Auswertungen öffnen
  - Einstellungen
  - Beenden
- Icon-States: grün (tracking), gelb (paused/idle), orange (Outlook unavailable), blau (locked), pulsierend (Reminder nach 2h)

**Floating Widget** (optional, immer im Vordergrund):
- Kleines, positionierbares Fenster
- Zeigt aktuelle Kategorie (mit Kategoriefarbe), Rolle, Stoppuhr
- Buttons: Lock-Toggle, Pause-Toggle, Kategorie-Dropdown für Schnellwechsel

**Erkennungs-Popup**:
- Erscheint bei erkannter neuer Kategorie via Outlook
- Inhalt: "Erkannt: <Kategorie> — übernehmen?" (Buttons: Ja / Nein / Nie mehr für diese Erkennung)
- Auto-Schließung nach 10 Sekunden = Nein
- "Nie mehr" → Eintrag in `rejected_suggestions`

**Screen-Unlock-Rückfrage**:
- Erscheint nach Entsperren des Bildschirms
- "Du warst X Minuten weg. Auf welche Kategorie buchen?"
- Optionen: vorherige Kategorie, andere wählen, verwerfen
- 15s Timeout → vorherige Kategorie wird verbucht

**Idle-Rückfrage**:
- Analog zur Screen-Unlock-Rückfrage, ausgelöst wenn `idle_threshold` überschritten

**Meeting-Start-Popup** (nur wenn Termin keine Kategorie hat):
- "Meeting '<Titel>' gestartet. Welche Kategorie?"
- Dropdown mit Kategorien
- Kein Timeout — bleibt offen bis beantwortet

**Settings-Fenster**:
- Rollen verwalten (anlegen, umbenennen, löschen)
- Kategorien verwalten (inkl. Zuweisung Rolle, Farbe, Outlook-Mapping)
- "Aus Outlook importieren" — liest Outlook-Kategorien (inkl. Farben), Auswahl welche übernommen werden
- Hotkey-Konfiguration (global, Ctrl+Shift+1..9 für 9 Schnellzugriffs-Kategorien)
- Idle-Schwelle, Poll-Intervall, Rundung (off/5/10/15 Min)
- Backup-Pfad und -Aktivierung
- Autostart mit Windows
- Liste der "nie mehr"-Erkennungen mit Reaktivierungs-Button

**Reports-Fenster**:
- Tagesansicht (Timeline mit farbigen Blöcken)
- Wochen-/Monatsansicht (gestapelte Balken oder Donut nach Rolle/Kategorie)
- Detailtabelle: alle Einträge, filterbar nach Zeitraum / Rolle / Kategorie / Quelle
- Inline-Editieren (Kategorie ändern, Zeiten anpassen, löschen) — mit Invarianten-Prüfung
- Export-Buttons: Excel, CSV

## 5. Verhalten in Schlüsselszenarien

### 5.1 App-Start

1. Tray-Icon erscheint, Outlook-Monitor wird gestartet.
2. Wenn keine Kategorie aus Outlook erkannt: Popup *"Womit beginnst du?"* mit Kategorie-Dropdown — keine Auto-Buchung bis Antwort.
3. Wenn Outlook nicht läuft: Tray-Icon orange, Popup mit Frage.

### 5.2 Automatische Kategorie-Erkennung

1. Outlook-Monitor erkennt neue/andere Kategorie im aktiven Inspector.
2. Wenn die Kombination (outlook_category → app_category) in `rejected_suggestions` mit `silenced=true` ist: stillschweigend ignorieren.
3. Sonst: Popup zeigen. Bei Bestätigung wechselt Tracker die Kategorie (vorheriger Eintrag wird geschlossen, neuer geöffnet, `source = auto_outlook`).
4. Bei Ablehnung: `rejection_count` für diese Kombination hochzählen.

### 5.3 Meeting

1. Outlook-Monitor erkennt aktiven Kalendertermin.
2. Tracker geht in **Lock-Modus** (`is_locked = true`).
3. Wenn Termin Kategorie hat: direkter Wechsel auf diese Kategorie (`source = auto_meeting`).
4. Wenn keine Kategorie: Popup, blockierend bis Antwort.
5. Termin endet → Lock aufgehoben, Outlook-Monitor übernimmt wieder.
6. **Manueller Override**: jederzeit per Tray/Widget — wechselt Kategorie und setzt `source = manual_override`, Lock bleibt aktiv (übersteuerter Eintrag).

### 5.4 Screen Lock

1. `screen_locked` empfangen → laufender Eintrag wird geschlossen, Tracker pausiert.
2. `screen_unlocked` empfangen → Popup mit 15s-Timeout:
   - Antwort "vorherige Kategorie" oder Timeout → ein Eintrag für die Lock-Dauer wird mit vorheriger Kategorie und `source = screen_lock_recovery` angelegt.
   - Antwort "andere Kategorie" → Eintrag mit gewählter Kategorie, `source = manual`.
   - Antwort "verwerfen" → keine Buchung, nur Lücke.
3. Tracking läuft auf gewählter Kategorie weiter.

### 5.5 Idle

Analog zu Screen Lock, ausgelöst durch Maus/Tastatur-Inaktivität. `source = idle_recovery`.

### 5.6 Manuelle Pause

Tracker schließt aktuellen Eintrag und stoppt — keine neuen Einträge bis Pause beendet wird.

### 5.7 Hotkeys

Globale Hotkeys (registriert via Win32 API): `Ctrl+Shift+1` bis `Ctrl+Shift+9` für die in den Einstellungen zugewiesenen 9 Schnellzugriffs-Kategorien. Sofortiger Wechsel mit `source = manual`.

### 5.8 Reminder

Wenn dieselbe Kategorie länger als 2 Stunden ununterbrochen aktiv ist: Tray-Icon pulsiert sanft (kein Popup, keine Frage). Pulsieren stoppt bei nächstem Kategorie-Wechsel.

### 5.9 Backup

Täglich um 02:00 Uhr (oder beim App-Start falls verpasst) wird die SQLite-DB in den konfigurierten Backup-Pfad kopiert. Dateiname mit Datum. Konfigurierbare Aufbewahrung (Default: letzte 30 Backups).

### 5.10 Autostart

Über Windows-Registry-Eintrag in `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`. In Einstellungen aktivierbar/deaktivierbar.

## 6. Rundung

- In Einstellungen wählbar: aus / 5 / 10 / 15 Minuten.
- Wird **nur beim Export und in Reports** angewendet — Rohdaten in der DB bleiben sekundengenau.
- Algorithmus garantiert: Summe pro Tag bleibt erhalten, keine Zeit wird doppelt gezählt. Bei Konflikten wird die letzte gerundete Grenze beibehalten und die nächste angepasst.

## 7. Audit Trail & Editierbarkeit

- Jeder Eintrag speichert `source` und `modified_at`.
- Outlook-Referenzen werden mitgeschrieben, wenn die Quelle Outlook war.
- Einträge können in der Detailtabelle editiert oder gelöscht werden — mit Invarianten-Prüfung (keine Überlappung).
- Bei Edit wird `modified_at` aktualisiert; eine vollständige Edit-Historie wird nicht geführt (entschieden gegen).

## 8. Packaging & Installation

- **PyInstaller**: One-File-Build, alle Abhängigkeiten gebündelt.
- **Inno Setup**: Installer mit Start-Menü-Eintrag, optional Autostart-Eintrag.
- DB-Speicherort: `%APPDATA%\WorkloadAnalyzer\workload.db`
- Settings-Speicherort: gleiche Stelle.
- Backup-Ordner: vom Nutzer wählbar, Default `%USERPROFILE%\Documents\WorkloadAnalyzer\Backups`.

## 9. Bewusste Nicht-Ziele (Out-of-Scope)

- Cloud-Sync, Multi-Device.
- Multi-User pro Installation.
- Hierarchische Unterkategorien (Struktur bleibt flach, analog zu Outlook).
- Custom-Regeln (z.B. nach Betreff oder Absender) — nur Outlook-Kategorien als Signal.
- Tagesziele / Soll-Ist-Vergleiche.
- Vollständige Edit-Historie (Audit über Änderungen an Einträgen).
- Mitternachts-Splitting von Einträgen.
- Lokalisierung (App auf Deutsch).
- macOS / Linux (Outlook-COM nur Windows).

## 10. Offene Risiken

- **Outlook-COM-Performance**: Polling alle 15s sollte unkritisch sein, muss aber im Worst-Case (sehr viele Termine) gemessen werden.
- **Global Hotkeys**: Konflikte mit anderen Apps möglich — daher konfigurierbar.
- **Idle-Detection**: `GetLastInputInfo` erfasst keine Fern-Sessions / RDP zuverlässig. Akzeptiert.
- **Rundung + Editieren**: Komplexität bei nachträglichen Edits gerundeter Daten — Rohdaten bleiben Quelle der Wahrheit, Rundung wird nur on-the-fly angewendet.
