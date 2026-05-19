"""Smoke tests: OutlookMonitor thread starts and stops cleanly."""
import pytest
from workload_analyzer.services.outlook_monitor import OutlookMonitor


def _make_monitor():
    def failing_factory():
        raise RuntimeError("Outlook not available in tests")
    return OutlookMonitor(outlook_factory=failing_factory)


def test_thread_starts_on_start(qtbot):
    monitor = _make_monitor()
    assert not monitor._thread.isRunning()
    monitor.start(interval_seconds=60)
    assert monitor._thread.isRunning()
    monitor.stop()


def test_thread_stops_on_stop(qtbot):
    monitor = _make_monitor()
    monitor.start(interval_seconds=60)
    monitor.stop()
    assert not monitor._thread.isRunning()


def test_stop_when_not_started_is_safe(qtbot):
    monitor = _make_monitor()
    monitor.stop()  # must not raise


def test_set_interval_does_not_crash_when_running(qtbot):
    monitor = _make_monitor()
    monitor.start(interval_seconds=60)
    monitor.set_interval(30)  # must not raise
    monitor.stop()
