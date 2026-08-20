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


class FakeItems:
    """Simulates Outlook's Items collection.

    Iterating the full collection is the expensive COM/MAPI scan we must avoid
    on every poll. ``__iter__`` therefore raises — the worker is required to
    narrow the set via ``Restrict()`` first (which Outlook evaluates itself).
    """

    def __init__(self, appointments):
        self._appointments = list(appointments)
        self.IncludeRecurrences = False
        self.sorted_by = None

    def Sort(self, field, descending=False):
        self.sorted_by = field

    def Restrict(self, query):
        now = datetime.datetime.now()
        return [a for a in self._appointments if a.Start <= now <= a.End]

    def __iter__(self):
        raise AssertionError(
            "Full calendar iteration is forbidden — use Restrict() "
            "(guards against the per-poll full-calendar scan)"
        )


class FakeFolder:
    def __init__(self, items):
        self.Items = items


class FakeNamespace:
    def __init__(self, appointments=None):
        self._appointments = appointments or []

    def GetDefaultFolder(self, folder_id):
        return FakeFolder(FakeItems(self._appointments))


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
    assert detected == []  # first sighting — awaiting confirmation
    monitor._worker._poll()

    assert detected == ["Coding"]


def test_category_detected_strips_first_only(qtbot):
    app_obj = FakeOutlookApp(inspector=FakeInspector(FakeItem(categories="Coding, Meetings")))
    monitor = _make_monitor(app_obj)

    detected = []
    monitor.category_detected.connect(detected.append)
    monitor._worker._poll()
    monitor._worker._poll()

    assert detected == ["Coding"]


def test_no_signal_when_category_unchanged(qtbot):
    app_obj = FakeOutlookApp(inspector=FakeInspector(FakeItem(categories="Coding")))
    monitor = _make_monitor(app_obj)
    monitor._worker._poll()
    monitor._worker._poll()  # confirm "Coding" as the established baseline

    detected = []
    monitor.category_detected.connect(detected.append)
    monitor._worker._poll()

    assert detected == []


def test_transient_category_blip_is_debounced(qtbot):
    """A single-poll category blip (e.g. a reminder popup briefly opening an
    old item) must not trigger a switch — a category only counts as a real
    context change once it's seen on two consecutive polls."""
    app_obj = FakeOutlookApp(inspector=FakeInspector(FakeItem(categories="Coding")))
    monitor = _make_monitor(app_obj)
    detected = []
    monitor.category_detected.connect(detected.append)

    monitor._worker._poll()
    monitor._worker._poll()
    assert detected == ["Coding"]

    # Blip: a different category appears for exactly one poll, then reverts.
    app_obj._inspector = FakeInspector(FakeItem(categories="Meetings"))
    monitor._worker._poll()
    app_obj._inspector = FakeInspector(FakeItem(categories="Coding"))
    monitor._worker._poll()

    assert detected == ["Coding"]  # no spurious "Meetings" emission


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


def test_meeting_lookup_avoids_full_calendar_scan(qtbot):
    """Regression guard: meeting detection must not enumerate the whole
    calendar (FakeItems.__iter__ raises); it must narrow via Restrict()."""
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
    monitor._worker._poll()  # must not trigger a full-calendar scan

    assert started == [("Team Sync", "Meetings")]


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
