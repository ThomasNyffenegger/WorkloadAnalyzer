"""Tests for the pure bucketing/formatting helpers behind the reports bar chart."""
import datetime

from workload_analyzer.ui.reports_window import _bucket_key, _bucket_label, _format_duration


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
