# Phase 4: Berichte & Analysen — Design Spec

**Date:** 2026-05-14
**Status:** Approved

---

## Overview

Phase 4 improves the existing Reports window with two focused enhancements:

1. **XLSX Pivot Export** — a new export function producing a Tage × Kategorien pivot table, accessible via a new "Export Pivot XLSX" button
2. **Schnellauswahl-Buttons** — four date-range shortcuts (Heute / Diese Woche / Diesen Monat / Letzten Monat) to avoid manual date entry

No DB schema changes. No new models. No new windows.

---

## Architecture

### Modified Files

```
src/workload_analyzer/services/export.py      # Add export_xlsx_pivot()
src/workload_analyzer/ui/reports_window.py    # Add buttons
```

### New Files

```
tests/test_pivot_export.py                    # Unit tests for export_xlsx_pivot
```

---

## Feature 1: XLSX Pivot Export

### Function signature

```python
def export_xlsx_pivot(
    repo: Repository,
    from_ts: int,
    to_ts: int,
    rounding_minutes: int,
    out_path: Path,
) -> None:
```

### Table structure

```
         | Coding | Meetings | Design | … | Total
---------+--------+----------+--------+---+-------
12.05.26 |   4.5  |    1.5   |   0.0  |   |  6.0
13.05.26 |   3.0  |    2.0   |   1.0  |   |  6.0
  Total  |   7.5  |    3.5   |   1.0  |   | 12.0
```

**Rules:**
- **Rows:** one per calendar day in `[from_ts, to_ts)`, including days with no entries (0.0h)
- **Columns:** all categories that have at least one entry in the range, sorted alphabetically
- **Cells:** total hours for that day+category, rounded to 1 decimal place
- **Last column:** `Total` — sum of all category hours for that day
- **Last row:** `Total` — sum of each category column across all days
- **Values:** hours (float), not minutes — easier to read at a glance
- **rounding_minutes:** applied via existing `round_seconds()` before converting to hours
- **Sheet name:** `"Pivot"`
- **Header row:** category name as cell value; cell background = category color (openpyxl `PatternFill`) if color is a valid hex string
- **Date column header:** `"Datum"`
- **Date format:** `"dd.MM.yy"` (e.g. `12.05.26`)

### What it does NOT do

- No merged cells
- No Excel formulas (values are pre-computed in Python)
- No conditional formatting

### UI integration

New button in `ReportsWindow` toolbar:

```
[Heute] [Diese Woche] [Diesen Monat] [Letzten Monat]  Von: [__] Bis: [__]  [Aktualisieren]  …  [Export CSV]  [Export XLSX]  [Export Pivot XLSX]
```

The button calls the same file-save dialog pattern as the existing XLSX export, then calls `export_xlsx_pivot`.

---

## Feature 2: Schnellauswahl-Buttons

Four `QPushButton` items added to the toolbar before "Von:":

| Button | Von | Bis |
|--------|-----|-----|
| Heute | today | today |
| Diese Woche | last Monday (or today if Monday) | today |
| Diesen Monat | 1st of current month | today |
| Letzten Monat | 1st of previous month | last day of previous month |

**Behavior:** clicking a button sets `_from_edit` and `_to_edit` then calls `_refresh()` immediately. No new methods needed — implemented as inline lambdas or small private methods.

**"Diese Woche" definition:** ISO week — Monday is day 1. If today is Monday, "Diese Woche" = today only. Implemented with `date.weekday()` (0 = Monday).

---

## Out of Scope

- No bar chart (Balkendiagramm) — can be added in a follow-up
- No totals row in the existing table view
- No goals/budgets
- No week-comparison view

---

## Estimated Tasks

| # | Task |
|---|------|
| 1 | `export_xlsx_pivot()` function + unit tests |
| 2 | Reports UI: Schnellauswahl buttons + Export Pivot XLSX button |
