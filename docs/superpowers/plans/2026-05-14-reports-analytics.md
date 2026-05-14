# Reports & Analytics (Phase 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Tage × Kategorien XLSX pivot export and four date-range shortcut buttons to the Reports window.

**Architecture:** New `export_xlsx_pivot()` function in the existing `export.py` service; UI-only changes to `reports_window.py` (toolbar buttons + one new export button). No DB or model changes.

**Tech Stack:** Python 3.11+, PyQt6, openpyxl (already used for XLSX export), pytest.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/workload_analyzer/services/export.py` | Modify | Add `export_xlsx_pivot()` |
| `src/workload_analyzer/ui/reports_window.py` | Modify | Add Schnellauswahl buttons + Export Pivot button |
| `tests/test_pivot_export.py` | Create | Unit tests for `export_xlsx_pivot` |

---

## Task 1: `export_xlsx_pivot()` — Pivot XLSX export

**Files:**
- Modify: `src/workload_analyzer/services/export.py`
- Create: `tests/test_pivot_export.py`

### Background

`src/workload_analyzer/services/export.py` already contains `export_xlsx()` (detail + summary sheets) and uses `openpyxl`. The new function is independent — it produces a separate file with only a "Pivot" sheet.

Existing helpers you can reuse:
- `round_seconds(seconds, rounding_minutes)` from `workload_analyzer.core.rounding`
- `repo.list_entries_between(from_ts, to_ts)` — returns `TimeEntry` objects
- `repo.list_categories()` — returns `Category` objects with `.id`, `.name`, `.color` (hex `#rrggbb`)

- [ ] **Step 1: Create `tests/test_pivot_export.py` with 7 failing tests**

```python
"""Tests for export_xlsx_pivot()."""
import datetime
from pathlib import Path

import pytest
from openpyxl import load_workbook

from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource
from workload_analyzer.services.export import export_xlsx_pivot


def make_repo(tmp_db_path):
    conn = connect(tmp_db_path)
    repo = Repository(conn)
    role_id = repo.create_role("Dev")
    cat1 = repo.create_category("Coding", "#3388cc", role_id)
    cat2 = repo.create_category("Meetings", "#ff8800", role_id)
    return repo, cat1, cat2


def day_ts(date_str: str) -> int:
    """Return unix timestamp for midnight local time of the given date."""
    d = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    return int(d.astimezone(datetime.timezone.utc).timestamp())


def test_pivot_creates_xlsx_file(tmp_db_path, tmp_path):
    repo, cat1, cat2 = make_repo(tmp_db_path)
    out = tmp_path / "pivot.xlsx"
    export_xlsx_pivot(repo, day_ts("2026-05-01"), day_ts("2026-05-02"), 0, out)
    assert out.exists()


def test_pivot_sheet_named_pivot(tmp_db_path, tmp_path):
    repo, cat1, cat2 = make_repo(tmp_db_path)
    out = tmp_path / "pivot.xlsx"
    export_xlsx_pivot(repo, day_ts("2026-05-01"), day_ts("2026-05-02"), 0, out)
    wb = load_workbook(out)
    assert "Pivot" in wb.sheetnames


def test_pivot_header_contains_datum_category_total(tmp_db_path, tmp_path):
    repo, cat1, cat2 = make_repo(tmp_db_path)
    start = day_ts("2026-05-01") + 3600
    repo.start_entry(cat1, start, EntrySource.MANUAL)
    repo.close_entry(repo.get_open_entry().id, start + 3600)
    out = tmp_path / "pivot.xlsx"
    export_xlsx_pivot(repo, day_ts("2026-05-01"), day_ts("2026-05-02"), 0, out)
    ws = load_workbook(out)["Pivot"]
    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    assert headers[0] == "Datum"
    assert "Coding" in headers
    assert headers[-1] == "Total"


def test_pivot_hours_computed_correctly(tmp_db_path, tmp_path):
    repo, cat1, cat2 = make_repo(tmp_db_path)
    start = day_ts("2026-05-01") + 3600
    repo.start_entry(cat1, start, EntrySource.MANUAL)
    repo.close_entry(repo.get_open_entry().id, start + 5400)  # 1.5 hours
    out = tmp_path / "pivot.xlsx"
    export_xlsx_pivot(repo, day_ts("2026-05-01"), day_ts("2026-05-02"), 0, out)
    ws = load_workbook(out)["Pivot"]
    coding_col = next(
        c for c in range(1, ws.max_column + 1)
        if ws.cell(row=1, column=c).value == "Coding"
    )
    assert ws.cell(row=2, column=coding_col).value == 1.5


def test_pivot_totals_row_is_last_and_labelled(tmp_db_path, tmp_path):
    repo, cat1, cat2 = make_repo(tmp_db_path)
    start = day_ts("2026-05-01") + 3600
    repo.start_entry(cat1, start, EntrySource.MANUAL)
    repo.close_entry(repo.get_open_entry().id, start + 3600)  # 1.0 hour
    out = tmp_path / "pivot.xlsx"
    export_xlsx_pivot(repo, day_ts("2026-05-01"), day_ts("2026-05-02"), 0, out)
    ws = load_workbook(out)["Pivot"]
    assert ws.cell(row=ws.max_row, column=1).value == "Total"


def test_pivot_days_with_no_entries_show_zero(tmp_db_path, tmp_path):
    repo, cat1, cat2 = make_repo(tmp_db_path)
    # Entry only on day 1 of a 2-day range
    start = day_ts("2026-05-01") + 3600
    repo.start_entry(cat1, start, EntrySource.MANUAL)
    repo.close_entry(repo.get_open_entry().id, start + 3600)
    out = tmp_path / "pivot.xlsx"
    export_xlsx_pivot(repo, day_ts("2026-05-01"), day_ts("2026-05-03"), 0, out)
    ws = load_workbook(out)["Pivot"]
    coding_col = next(
        c for c in range(1, ws.max_column + 1)
        if ws.cell(row=1, column=c).value == "Coding"
    )
    # Row 3 = second day (01.05, 02.05 → row2=01.05, row3=02.05)
    assert ws.cell(row=3, column=coding_col).value == 0.0


def test_pivot_empty_range_produces_valid_file(tmp_db_path, tmp_path):
    repo, cat1, cat2 = make_repo(tmp_db_path)
    # No entries at all — should produce a file with just header + totals row
    out = tmp_path / "pivot.xlsx"
    export_xlsx_pivot(repo, day_ts("2026-05-01"), day_ts("2026-05-02"), 0, out)
    assert out.exists()
    wb = load_workbook(out)
    assert "Pivot" in wb.sheetnames
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_pivot_export.py -v
```

Expected: FAIL — `ImportError: cannot import name 'export_xlsx_pivot'`

- [ ] **Step 3: Implement `export_xlsx_pivot` in `export.py`**

Add this function at the end of `src/workload_analyzer/services/export.py`:

```python
def export_xlsx_pivot(
    repo: Repository,
    from_ts: int,
    to_ts: int,
    rounding_minutes: int,
    out_path: Path,
) -> None:
    """Export a Tage × Kategorien pivot table to a single-sheet XLSX file.

    Rows = calendar days in [from_ts, to_ts).
    Columns = categories that have at least one entry in the range (alphabetical).
    Cells = total hours (float, 1 decimal).
    Last column = daily total. Last row = column totals.
    """
    from datetime import date, timedelta
    from openpyxl.styles import Font, PatternFill

    cats = {c.id: c for c in repo.list_categories()}
    entries = [e for e in repo.list_entries_between(from_ts, to_ts) if e.end_ts is not None]

    # Date range: one row per calendar day
    from_date = datetime.fromtimestamp(from_ts, tz=timezone.utc).astimezone().date()
    to_date = datetime.fromtimestamp(max(from_ts, to_ts - 1), tz=timezone.utc).astimezone().date()
    days: list[date] = []
    d = from_date
    while d <= to_date:
        days.append(d)
        d += timedelta(days=1)

    # Categories that appear in entries, sorted alphabetically
    used_cat_ids = sorted(
        {e.category_id for e in entries if e.category_id in cats},
        key=lambda cid: cats[cid].name,
    )

    # Aggregate: (date, cat_id) -> hours
    totals: dict[tuple[date, int], float] = {}
    for entry in entries:
        cat = cats.get(entry.category_id)
        if cat is None:
            continue
        dur_s = round_seconds(entry.duration_seconds(), rounding_minutes)
        entry_date = datetime.fromtimestamp(entry.start_ts, tz=timezone.utc).astimezone().date()
        key = (entry_date, entry.category_id)
        totals[key] = totals.get(key, 0.0) + dur_s / 3600.0

    wb = Workbook()
    ws = wb.active
    ws.title = "Pivot"

    total_col = len(used_cat_ids) + 2  # 1=Datum, 2..N=categories, N+1=Total

    # Header row
    ws.cell(row=1, column=1, value="Datum").font = Font(bold=True)
    for col_idx, cat_id in enumerate(used_cat_ids, start=2):
        cat = cats[cat_id]
        cell = ws.cell(row=1, column=col_idx, value=cat.name)
        cell.font = Font(bold=True)
        try:
            hex_color = cat.color.lstrip("#")
            if len(hex_color) == 6:
                cell.fill = PatternFill(fill_type="solid", fgColor=hex_color)
        except Exception:
            pass
    ws.cell(row=1, column=total_col, value="Total").font = Font(bold=True)

    # Data rows (one per day)
    for row_idx, day in enumerate(days, start=2):
        ws.cell(row=row_idx, column=1, value=day.strftime("%d.%m.%y"))
        row_total = 0.0
        for col_idx, cat_id in enumerate(used_cat_ids, start=2):
            hours = round(totals.get((day, cat_id), 0.0), 1)
            ws.cell(row=row_idx, column=col_idx, value=hours)
            row_total += hours
        ws.cell(row=row_idx, column=total_col, value=round(row_total, 1))

    # Totals row
    total_row = len(days) + 2
    ws.cell(row=total_row, column=1, value="Total").font = Font(bold=True)
    grand_total = 0.0
    for col_idx, cat_id in enumerate(used_cat_ids, start=2):
        col_total = round(sum(totals.get((day, cat_id), 0.0) for day in days), 1)
        ws.cell(row=total_row, column=col_idx, value=col_total).font = Font(bold=True)
        grand_total += col_total
    ws.cell(row=total_row, column=total_col, value=round(grand_total, 1)).font = Font(bold=True)

    wb.save(out_path)
```

- [ ] **Step 4: Run tests**

```
python -m pytest tests/test_pivot_export.py -v
```

Expected: 7 passed

- [ ] **Step 5: Run full test suite**

```
python -m pytest --tb=short -q
```

Expected: 109 passed (102 existing + 7 new)

- [ ] **Step 6: Commit**

```bash
git add src/workload_analyzer/services/export.py tests/test_pivot_export.py
git commit -m "feat: add export_xlsx_pivot() — Tage x Kategorien pivot export"
```

---

## Task 2: Reports UI — Schnellauswahl buttons + Export Pivot button

**Files:**
- Modify: `src/workload_analyzer/ui/reports_window.py`

### Background

`ReportsWindow._build_ui()` currently builds a toolbar with: `Von:` label → `_from_edit` → `Bis:` label → `_to_edit` → `Aktualisieren` button → stretch → `Export CSV` → `Export XLSX`.

You will add 4 shortcut buttons **before** the `Von:` label, and one `Export Pivot XLSX` button **after** `Export XLSX`.

The `_export_xlsx_pivot` method follows the same pattern as `_export_xlsx`.

- [ ] **Step 1: Verify the toolbar section in `reports_window.py`**

Read `src/workload_analyzer/ui/reports_window.py` lines 31–64 to confirm the current toolbar structure before editing.

- [ ] **Step 2: Replace the toolbar block in `_build_ui`**

In `_build_ui`, replace everything from `# --- Toolbar row ---` down to `layout.addLayout(toolbar)` (lines ~34–64) with:

```python
        # --- Toolbar row ---
        toolbar = QHBoxLayout()

        # Schnellauswahl buttons
        for label, slot in [
            ("Heute",        self._select_today),
            ("Diese Woche",  self._select_this_week),
            ("Diesen Monat", self._select_this_month),
            ("Letzten Monat",self._select_last_month),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            toolbar.addWidget(btn)

        toolbar.addSpacing(12)
        toolbar.addWidget(QLabel("Von:"))
        self._from_edit = QDateEdit()
        self._from_edit.setCalendarPopup(True)
        self._from_edit.setDate(
            QDateTime.currentDateTime().addDays(-7).date()
        )
        toolbar.addWidget(self._from_edit)

        toolbar.addWidget(QLabel("Bis:"))
        self._to_edit = QDateEdit()
        self._to_edit.setCalendarPopup(True)
        self._to_edit.setDate(QDateTime.currentDateTime().date())
        toolbar.addWidget(self._to_edit)

        refresh_btn = QPushButton("Aktualisieren")
        refresh_btn.clicked.connect(self._refresh)
        toolbar.addWidget(refresh_btn)

        toolbar.addStretch()

        export_csv_btn = QPushButton("Export CSV")
        export_csv_btn.clicked.connect(self._export_csv)
        toolbar.addWidget(export_csv_btn)

        export_xlsx_btn = QPushButton("Export XLSX")
        export_xlsx_btn.clicked.connect(self._export_xlsx)
        toolbar.addWidget(export_xlsx_btn)

        export_pivot_btn = QPushButton("Export Pivot XLSX")
        export_pivot_btn.clicked.connect(self._export_xlsx_pivot)
        toolbar.addWidget(export_pivot_btn)

        layout.addLayout(toolbar)
```

- [ ] **Step 3: Add the four `_select_*` methods and `_export_xlsx_pivot`**

Add these methods to `ReportsWindow`, after `_save_rounding` (or anywhere after `_build_ui`). Place them after the existing `_export_xlsx` method:

```python
    # ------------------------------------------------------------------
    # Schnellauswahl helpers
    # ------------------------------------------------------------------

    def _select_today(self) -> None:
        today = QDateTime.currentDateTime().date()
        self._from_edit.setDate(today)
        self._to_edit.setDate(today)
        self._refresh()

    def _select_this_week(self) -> None:
        import datetime as _dt
        today = _dt.date.today()
        monday = today - _dt.timedelta(days=today.weekday())  # weekday() 0 = Monday
        self._from_edit.setDate(_py_date_to_qdate(monday))
        self._to_edit.setDate(QDateTime.currentDateTime().date())
        self._refresh()

    def _select_this_month(self) -> None:
        import datetime as _dt
        today = _dt.date.today()
        first = today.replace(day=1)
        self._from_edit.setDate(_py_date_to_qdate(first))
        self._to_edit.setDate(QDateTime.currentDateTime().date())
        self._refresh()

    def _select_last_month(self) -> None:
        import datetime as _dt
        today = _dt.date.today()
        last_day_prev = today.replace(day=1) - _dt.timedelta(days=1)
        first_day_prev = last_day_prev.replace(day=1)
        self._from_edit.setDate(_py_date_to_qdate(first_day_prev))
        self._to_edit.setDate(_py_date_to_qdate(last_day_prev))
        self._refresh()

    def _export_xlsx_pivot(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Pivot XLSX speichern", "", "Excel-Dateien (*.xlsx)"
        )
        if not path:
            return
        from_ts, to_ts = self._range_ts()
        rounding = int(self._repo.get_setting("rounding_minutes", "0") or "0")
        from workload_analyzer.services.export import export_xlsx_pivot
        export_xlsx_pivot(self._repo, from_ts, to_ts, rounding, Path(path))
        QMessageBox.information(self, "Export", f"Pivot XLSX gespeichert:\n{path}")
```

- [ ] **Step 4: Add the `_py_date_to_qdate` helper**

Add this module-level helper function near the top of `reports_window.py`, after the imports:

```python
def _py_date_to_qdate(d: "datetime.date"):
    """Convert a Python date to QDate."""
    from PyQt6.QtCore import QDate
    return QDate(d.year, d.month, d.day)
```

- [ ] **Step 5: Verify the file compiles**

```
python -m py_compile src/workload_analyzer/ui/reports_window.py
```

Expected: no output

- [ ] **Step 6: Run full test suite**

```
python -m pytest --tb=short -q
```

Expected: 109 passed

- [ ] **Step 7: Commit**

```bash
git add src/workload_analyzer/ui/reports_window.py
git commit -m "feat: add Schnellauswahl buttons and Export Pivot XLSX to Reports window"
```

---

## Done

After Task 2, Phase 4 is complete:
- `export_xlsx_pivot()` produces a clean Tage × Kategorien XLSX with colored headers, row totals, and a grand total row
- Reports window has 4 shortcut buttons (Heute / Diese Woche / Diesen Monat / Letzten Monat) that immediately refresh the view
- New "Export Pivot XLSX" button triggers the pivot export
