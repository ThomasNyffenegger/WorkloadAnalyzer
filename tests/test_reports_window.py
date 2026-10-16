"""Bar chart percentage labels: share of the bar's own day, not of the whole range."""
import datetime

from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource
from workload_analyzer.ui.reports_window import ReportsWindow


def _ts(day: datetime.date, hour: int, minute: int = 0) -> int:
    return int(datetime.datetime.combine(day, datetime.time(hour, minute)).timestamp())


def _percent_labels(window) -> list[str]:
    ax = window._canvas.figure.axes[0]
    return sorted(t.get_text() for t in ax.texts if t.get_text().endswith("%"))


def _make_window(tmp_db_path, entries):
    repo = Repository(connect(tmp_db_path))
    role_id = repo.create_role("R")
    ids = {
        "A": repo.create_category(name="A", color="#1D9E75", role_id=role_id),
        "B": repo.create_category(name="B", color="#D85A30", role_id=role_id),
    }
    for name, start, end in entries:
        repo.insert_closed_entry(ids[name], start, end, EntrySource.MANUAL)
    return ReportsWindow(repo)


def test_bar_percentages_are_share_of_each_days_total(qtbot, tmp_db_path):
    today = datetime.date.today()
    day1, day2 = today - datetime.timedelta(days=3), today - datetime.timedelta(days=2)
    window = _make_window(tmp_db_path, [
        # day 1: A 60 min, B 180 min  -> 25% / 75%
        ("A", _ts(day1, 8), _ts(day1, 9)),
        ("B", _ts(day1, 9), _ts(day1, 12)),
        # day 2: A 120 min only        -> 100%
        ("A", _ts(day2, 8), _ts(day2, 10)),
    ])
    qtbot.addWidget(window)

    # A has 180 of 360 minutes overall (50%) — that number must NOT appear.
    assert _percent_labels(window) == ["100%", "25%", "75%"]


def test_bar_percentages_of_one_day_sum_to_100(qtbot, tmp_db_path):
    day = datetime.date.today() - datetime.timedelta(days=1)
    window = _make_window(tmp_db_path, [
        ("A", _ts(day, 8), _ts(day, 9)),    # 60
        ("B", _ts(day, 9), _ts(day, 10)),   # 60
    ])
    qtbot.addWidget(window)

    assert _percent_labels(window) == ["50%", "50%"]
