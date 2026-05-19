import datetime

import pytest
from workload_analyzer.services.outlook_monitor import OutlookMonitor


# ---------------------------------------------------------------------------
# Fake COM objects (no pywin32 required)
# ---------------------------------------------------------------------------

class FakeItem:
    def __init__(self, categories="", subject="", start=None, end=None):
        self.Categories = categories
        self.Subject = subject
        self.Start = start
        self.End = end


class FakeInspector:
    def __init__(self, item=None):
        self.CurrentItem = item


class FakeFolder:
    def __init__(self, items=None):
        self.Items = items or []


class FakeNamespace:
    def __init__(self, appointments=None):
        self._appointments = appointments or []

    def GetDefaultFolder(self, folder_id):
        return FakeFolder(self._appointments)


class FakeOutlookApp:
    def __init__(self, inspector=None, appointments=None):
        self._inspector = inspector
        self._ns = FakeNamespace(appointments)

    def ActiveInspector(self):
        return self._inspector

    def GetNamespace(self, name):
        return self._ns


def _make_monitor(app_obj):
    """Create an OutlookMonitor with a fake Outlook factory."""
    return OutlookMonitor(outlook_factory=lambda: app_obj)


# ---------------------------------------------------------------------------
# Tests: category detection
# ---------------------------------------------------------------------------

def test_category_detected_emitted(qtbot):
    app_obj = FakeOutlookApp(inspector=FakeInspector(FakeItem(categories="Coding")))
    monitor = _make_monitor(app_obj)

    detected = []
    monitor.category_detected.connect(detected.append)
    monitor._worker._poll()

    assert detected == ["Coding"]


def test_category_detected_strips_first_only(qtbot):
    app_obj = FakeOutlookApp(inspector=FakeInspector(FakeItem(categories="Coding, Meetings")))
    monitor = _make_monitor(app_obj)

    detected = []
    monitor.category_detected.connect(detected.append)
    monitor._worker._poll()

    assert detected == ["Coding"]


def test_no_signal_when_category_unchanged(qtbot):
    app_obj = FakeOutlookApp(inspector=FakeInspector(FakeItem(categories="Coding")))
    monitor = _make_monitor(app_obj)
    monitor._worker._poll()

    detected = []
    monitor.category_detected.connect(detected.append)
    monitor._worker._poll()

    assert detected == []


def test_no_signal_when_no_inspector(qtbot):
    app_obj = FakeOutlookApp(inspector=None)
    monitor = _make_monitor(app_obj)

    detected = []
    monitor.category_detected.connect(detected.append)
    monitor._worker._poll()

    assert detected == []


def test_availability_false_on_error(qtbot):
    def failing_factory():
        raise RuntimeError("Outlook not running")

    monitor = OutlookMonitor(outlook_factory=failing_factory)

    availability = []
    monitor.availability_changed.connect(availability.append)
    monitor._worker._poll()

    assert availability == [False]


def test_availability_true_on_recovery(qtbot):
    calls = [0]

    def flaky_factory():
        calls[0] += 1
        if calls[0] == 1:
            raise RuntimeError("down")
        return FakeOutlookApp()

    monitor = OutlookMonitor(outlook_factory=flaky_factory)
    availability = []
    monitor.availability_changed.connect(availability.append)

    monitor._worker._poll()
    monitor._worker._poll()

    assert availability == [False, True]


def test_no_duplicate_availability_signals(qtbot):
    def failing_factory():
        raise RuntimeError("down")

    monitor = OutlookMonitor(outlook_factory=failing_factory)
    availability = []
    monitor.availability_changed.connect(availability.append)

    monitor._worker._poll()
    monitor._worker._poll()
    monitor._worker._poll()

    assert availability == [False]


# ---------------------------------------------------------------------------
# Tests: meeting detection
# ---------------------------------------------------------------------------

def test_meeting_started_signal(qtbot):
    now = datetime.datetime.now()
    appt = FakeItem(
        subject="Team Sync",
        categories="Meetings",
        start=now - datetime.timedelta(minutes=5),
        end=now + datetime.timedelta(minutes=25),
    )
    app_obj = FakeOutlookApp(appointments=[appt])
    monitor = _make_monitor(app_obj)

    started = []
    monitor.meeting_started.connect(lambda t, c: started.append((t, c)))
    monitor._worker._poll()

    assert started == [("Team Sync", "Meetings")]


def test_meeting_ended_signal(qtbot):
    now = datetime.datetime.now()
    appt = FakeItem(
        subject="Team Sync",
        start=now - datetime.timedelta(minutes=5),
        end=now + datetime.timedelta(minutes=25),
    )
    app_obj = FakeOutlookApp(appointments=[appt])
    monitor = _make_monitor(app_obj)
    monitor._worker._poll()

    app_obj._ns = FakeNamespace(appointments=[])
    ended = []
    monitor.meeting_ended.connect(lambda: ended.append(True))
    monitor._worker._poll()

    assert ended == [True]


def test_no_duplicate_meeting_started(qtbot):
    now = datetime.datetime.now()
    appt = FakeItem(
        subject="Team Sync",
        start=now - datetime.timedelta(minutes=5),
        end=now + datetime.timedelta(minutes=25),
    )
    app_obj = FakeOutlookApp(appointments=[appt])
    monitor = _make_monitor(app_obj)
    monitor._worker._poll()

    started = []
    monitor.meeting_started.connect(lambda t, c: started.append(t))
    monitor._worker._poll()

    assert started == []


def test_meeting_no_category(qtbot):
    now = datetime.datetime.now()
    appt = FakeItem(
        subject="1:1",
        categories="",
        start=now - datetime.timedelta(minutes=1),
        end=now + datetime.timedelta(minutes=30),
    )
    app_obj = FakeOutlookApp(appointments=[appt])
    monitor = _make_monitor(app_obj)

    started = []
    monitor.meeting_started.connect(lambda t, c: started.append((t, c)))
    monitor._worker._poll()

    assert started == [("1:1", None)]


def test_meeting_ended_emitted_on_availability_loss(qtbot):
    now = datetime.datetime.now()
    appt = FakeItem(
        subject="Team Sync",
        start=now - datetime.timedelta(minutes=5),
        end=now + datetime.timedelta(minutes=25),
    )
    calls = [0]

    def flaky_factory():
        calls[0] += 1
        if calls[0] == 1:
            return FakeOutlookApp(appointments=[appt])
        raise RuntimeError("Outlook crashed")

    monitor = OutlookMonitor(outlook_factory=flaky_factory)
    monitor._worker._poll()

    ended = []
    monitor.meeting_ended.connect(lambda: ended.append(True))
    monitor._worker._poll()

    assert ended == [True]
