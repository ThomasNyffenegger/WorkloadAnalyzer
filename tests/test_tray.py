"""Tests for TrayIcon tooltip building."""
from workload_analyzer.core.tracker import TimeTracker
from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource
from workload_analyzer.ui.tray import TrayIcon


def _make_tray(tmp_db_path, tracking=False):
    conn = connect(tmp_db_path)
    repo = Repository(conn)
    role_id = repo.create_role("R")
    cat_id = repo.create_category(name="A", color="#0", role_id=role_id)
    clock = [1000]
    tracker = TimeTracker(repo=repo, clock=lambda: clock[0])
    if tracking:
        tracker.start(category_id=cat_id, source=EntrySource.MANUAL)
    tray = TrayIcon(repo=repo, tracker=tracker)
    return tray


def test_tooltip_suffix_does_not_accumulate_across_refreshes(qtbot, tmp_db_path):
    tray = _make_tray(tmp_db_path)

    tray.set_outlook_available(False)
    first = tray.icon.toolTip()
    assert first.count("Outlook nicht verfügbar") == 1

    # Repeated refreshes (e.g. the periodic 5s timer) must not keep
    # stacking the warning onto an already-warned tooltip.
    tray.refresh()
    tray.refresh()
    tray.refresh()

    assert tray.icon.toolTip() == first
    assert tray.icon.toolTip().count("Outlook nicht verfügbar") == 1


def test_tooltip_suffix_clears_when_outlook_recovers(qtbot, tmp_db_path):
    tray = _make_tray(tmp_db_path)
    tray.set_outlook_available(False)
    assert "Outlook nicht verfügbar" in tray.icon.toolTip()

    tray.set_outlook_available(True)
    assert "Outlook nicht verfügbar" not in tray.icon.toolTip()


def test_tooltip_suffix_persists_while_tracking_same_category(qtbot, tmp_db_path):
    """The base tooltip for TRACKING is only recomputed from the DB on a
    category change — must still not let the warning suffix pile up while
    the category stays the same across many refreshes."""
    tray = _make_tray(tmp_db_path, tracking=True)
    tray.set_outlook_available(False)
    first = tray.icon.toolTip()

    for _ in range(5):
        tray.refresh()

    assert tray.icon.toolTip() == first
    assert tray.icon.toolTip().count("Outlook nicht verfügbar") == 1
