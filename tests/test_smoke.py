"""End-to-end smoke test covering the full tracking and export flow."""
import csv
from pathlib import Path

import pytest
from openpyxl import load_workbook

from workload_analyzer.core.tracker import TimeTracker
from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource
from workload_analyzer.services.export import export_csv, export_xlsx


class FakeClock:
    def __init__(self, ts: int = 1_000_000):
        self.ts = ts

    def __call__(self) -> int:
        return self.ts

    def advance(self, seconds: int) -> None:
        self.ts += seconds


def test_full_tracking_and_export_flow(tmp_db_path, tmp_path: Path):
    # 1. Connect to temp DB and create repository
    conn = connect(tmp_db_path)
    repo = Repository(conn)

    # 2. Create a role and two categories
    role_id = repo.create_role("Engineering")
    c1 = repo.create_category(name="Design", color="#FF0000", role_id=role_id)
    c2 = repo.create_category(name="Coding", color="#00FF00", role_id=role_id)

    # 3. Create tracker with fake clock
    clock = FakeClock(ts=1_000_000)
    tracker = TimeTracker(repo=repo, clock=clock)

    # 4. Start tracking category 1
    tracker.start(category_id=c1, source=EntrySource.MANUAL)

    # 5. Advance 30 minutes, switch to category 2
    clock.advance(30 * 60)
    tracker.switch_to(category_id=c2, source=EntrySource.MANUAL)

    # 6. Advance 15 minutes, pause
    clock.advance(15 * 60)
    tracker.pause()

    # 7. Advance 5 minutes (paused — no entry), resume category 2
    clock.advance(5 * 60)
    tracker.resume()

    # 8. Advance 10 minutes, stop by pausing again
    clock.advance(10 * 60)
    tracker.pause()

    # 9. Assert at least 3 closed entries in the DB
    all_entries = repo.list_entries_between(0, 9_999_999_999)
    closed_entries = [e for e in all_entries if not e.is_active()]
    assert len(closed_entries) >= 3, (
        f"Expected at least 3 closed entries, got {len(closed_entries)}"
    )

    # 10. Export CSV and assert file exists with more than 1 line
    csv_path = tmp_path / "smoke_export.csv"
    export_csv(repo, from_ts=0, to_ts=9_999_999_999, out_path=csv_path)
    assert csv_path.exists(), "CSV export file was not created"
    with csv_path.open(encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) > 1, (
        f"CSV should have header + data rows, got {len(lines)} line(s)"
    )

    # 11. Export XLSX and assert file exists
    xlsx_path = tmp_path / "smoke_export.xlsx"
    export_xlsx(repo, from_ts=0, to_ts=9_999_999_999, rounding_minutes=0, out_path=xlsx_path)
    assert xlsx_path.exists(), "XLSX export file was not created"

    conn.close()


def test_rejection_learning_flow(tmp_db_path):
    """Smoke: record 3 rejections → silenced, then reactivate."""
    from workload_analyzer.db.connection import connect
    from workload_analyzer.db.repository import Repository

    repo = Repository(connect(tmp_db_path))
    role_id = repo.create_role("Dev")
    cat_id = repo.create_category("Coding", "#ff0000", role_id, outlook_category_name="Coding")

    assert not repo.is_silenced("Coding", cat_id)
    for _ in range(3):
        repo.record_rejection("Coding", cat_id)
    assert repo.is_silenced("Coding", cat_id)

    s = repo.list_rejected_suggestions()[0]
    repo.set_silenced(s.id, False)
    assert not repo.is_silenced("Coding", cat_id)
