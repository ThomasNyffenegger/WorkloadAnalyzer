import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook

from workload_analyzer.core.rounding import round_seconds
from workload_analyzer.db.repository import Repository


def _ts_to_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def _gather_rows(repo: Repository, from_ts: int, to_ts: int, rounding_minutes: int):
    """Yield (start, end, duration_min, role, category, source, comment) tuples."""
    cats = {c.id: c for c in repo.list_categories()}
    roles = {r.id: r for r in repo.list_roles()}
    for entry in repo.list_entries_between(from_ts, to_ts):
        if entry.end_ts is None:
            continue
        cat = cats.get(entry.category_id)
        if cat is None:
            continue
        role = roles.get(cat.role_id)
        role_name = role.name if role else ""
        duration_s = round_seconds(entry.duration_seconds(), rounding_minutes)
        if duration_s == 0 and rounding_minutes != 0:
            continue
        yield (
            _ts_to_iso(entry.start_ts),
            _ts_to_iso(entry.end_ts),
            duration_s // 60,
            role_name,
            cat.name,
            entry.source.value,
            entry.comment or "",
        )


def export_csv(repo: Repository, from_ts: int, to_ts: int, out_path: Path, rounding_minutes: int = 0) -> None:
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["start", "end", "duration_minutes", "role", "category", "source", "comment"])
        for row in _gather_rows(repo, from_ts, to_ts, rounding_minutes):
            writer.writerow(row)


def export_xlsx(repo: Repository, from_ts: int, to_ts: int, rounding_minutes: int, out_path: Path) -> None:
    rows = list(_gather_rows(repo, from_ts, to_ts, rounding_minutes))

    wb = Workbook()
    # Summary first
    summary = wb.active
    summary.title = "Summary"
    summary.append(["Role", "Category", "Total minutes"])
    totals: dict[tuple[str, str], int] = defaultdict(int)
    for start, end, dur, role, cat, src, comment in rows:
        totals[(role, cat)] += dur
    for (role, cat), dur in sorted(totals.items()):
        summary.append([role, cat, dur])

    # Details
    details = wb.create_sheet("Details")
    details.append(["start", "end", "duration_minutes", "role", "category", "source", "comment"])
    for row in rows:
        details.append(list(row))

    wb.save(out_path)
