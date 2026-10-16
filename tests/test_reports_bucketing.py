"""Tests for the pure bucketing/formatting helpers behind the reports bar chart."""
import datetime
from types import SimpleNamespace

from workload_analyzer.ui.reports_window import (
    _bucket_key, _bucket_label, _day_slices, _format_duration, _split_by_day,
)


def _ts(y, mo, d, h=0, mi=0):
    return int(datetime.datetime(y, mo, d, h, mi).timestamp())


def _entry(cat_id, start, end):
    return SimpleNamespace(category_id=cat_id, start_ts=start, end_ts=end)


def test_split_by_day_within_one_day():
    start, end = _ts(2026, 10, 14, 9, 0), _ts(2026, 10, 14, 11, 30)
    assert _split_by_day(start, end) == [(datetime.date(2026, 10, 14), 150 * 60)]


def test_split_by_day_across_midnight():
    # the real overnight entry: 14.10. 15:59 -> 15.10. 09:10
    start, end = _ts(2026, 10, 14, 15, 59), _ts(2026, 10, 15, 9, 10)
    assert _split_by_day(start, end) == [
        (datetime.date(2026, 10, 14), (8 * 60 + 1) * 60),   # 15:59 -> 24:00
        (datetime.date(2026, 10, 15), (9 * 60 + 10) * 60),  # 00:00 -> 09:10
    ]


def test_split_by_day_spans_several_days():
    start, end = _ts(2026, 10, 14, 12, 0), _ts(2026, 10, 17, 6, 0)
    pieces = _split_by_day(start, end)
    assert [d for d, _ in pieces] == [
        datetime.date(2026, 10, 14), datetime.date(2026, 10, 15),
        datetime.date(2026, 10, 16), datetime.date(2026, 10, 17),
    ]
    assert sum(s for _, s in pieces) == end - start


def test_split_by_day_empty_interval():
    ts = _ts(2026, 10, 14, 9, 0)
    assert _split_by_day(ts, ts) == []


def test_day_slices_no_day_exceeds_24h_for_overnight_entry():
    entry = _entry(1, _ts(2026, 10, 14, 15, 59), _ts(2026, 10, 15, 9, 10))
    slices = _day_slices([entry], _ts(2026, 10, 9), _ts(2026, 10, 17), rounding=0)
    per_day = {}
    for _, day, minutes in slices:
        per_day[day] = per_day.get(day, 0) + minutes
    assert per_day[datetime.date(2026, 10, 14)] == 481
    assert per_day[datetime.date(2026, 10, 15)] == 550
    assert sum(per_day.values()) == 1031


def test_day_slices_clips_entry_to_selected_range():
    # range starts at 15.10. 00:00 — only the part after midnight counts
    entry = _entry(1, _ts(2026, 10, 14, 15, 59), _ts(2026, 10, 15, 9, 10))
    slices = _day_slices([entry], _ts(2026, 10, 15), _ts(2026, 10, 16), rounding=0)
    assert slices == [(1, datetime.date(2026, 10, 15), 550.0)]


def test_day_slices_rounding_is_spread_proportionally():
    # 62 min with 5-min rounding -> 60 min total, all on one day
    entry = _entry(1, _ts(2026, 10, 14, 9, 0), _ts(2026, 10, 14, 10, 2))
    slices = _day_slices([entry], _ts(2026, 10, 14), _ts(2026, 10, 15), rounding=5)
    assert len(slices) == 1
    assert abs(slices[0][2] - 60.0) < 1e-9


def test_day_slices_skips_non_positive_entries():
    ts = _ts(2026, 10, 14, 9, 0)
    assert _day_slices([_entry(1, ts, ts)], 0, 2**40, rounding=0) == []


def test_bucket_key_day():
    dt = datetime.datetime(2026, 8, 14, 9, 30)
    assert _bucket_key(dt, "Tag") == (2026, 8, 14)


def test_bucket_key_week_groups_same_iso_week():
    monday = datetime.datetime(2026, 8, 10, 8, 0)
    friday = datetime.datetime(2026, 8, 14, 18, 0)
    assert _bucket_key(monday, "Woche") == _bucket_key(friday, "Woche")


def test_bucket_key_week_splits_different_iso_weeks():
    week1 = datetime.datetime(2026, 8, 9, 12, 0)   # Sunday, still week 32
    week2 = datetime.datetime(2026, 8, 10, 12, 0)  # Monday, week 33
    assert _bucket_key(week1, "Woche") != _bucket_key(week2, "Woche")


def test_bucket_key_month():
    dt = datetime.datetime(2026, 8, 14, 9, 30)
    assert _bucket_key(dt, "Monat") == (2026, 8)


def test_bucket_label_day():
    assert _bucket_label((2026, 8, 14), "Tag") == "14.08."


def test_bucket_label_week():
    assert _bucket_label((2026, 33), "Woche") == "KW33"


def test_bucket_label_month():
    assert _bucket_label((2026, 8), "Monat") == "08.2026"


def test_format_duration_under_an_hour():
    assert _format_duration(45) == "45min"


def test_format_duration_with_hours():
    assert _format_duration(195) == "3h 15min"


def test_format_duration_rounds_fractional_minutes():
    assert _format_duration(90.6) == "1h 31min"
