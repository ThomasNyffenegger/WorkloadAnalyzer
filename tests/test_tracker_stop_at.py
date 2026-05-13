"""Tests for TimeTracker.stop_at()."""
import pytest
from workload_analyzer.core.tracker import TimeTracker, TrackerState
from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource


class FakeClock:
    def __init__(self, start: int = 1000):
        self.now = start

    def __call__(self) -> int:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += seconds


@pytest.fixture
def setup(tmp_db_path):
    conn = connect(tmp_db_path)
    repo = Repository(conn)
    rid = repo.create_role("R")
    cat_id = repo.create_category(name="Coding", color="#ff0000", role_id=rid)
    clock = FakeClock()
    tracker = TimeTracker(repo=repo, clock=clock)
    yield tracker, repo, clock, cat_id
    conn.close()


def test_stop_at_returns_category_id(setup):
    tracker, repo, clock, cat_id = setup
    tracker.start(cat_id, EntrySource.MANUAL)
    result = tracker.stop_at(1_000_600)
    assert result == cat_id


def test_stop_at_closes_entry_at_given_timestamp(setup):
    tracker, repo, clock, cat_id = setup
    tracker.start(cat_id, EntrySource.MANUAL)
    tracker.stop_at(1_000_600)
    entry = repo.list_entries_between(0, 9_999_999_999)[0]
    assert entry.end_ts == 1_000_600


def test_stop_at_transitions_to_paused(setup):
    tracker, repo, clock, cat_id = setup
    tracker.start(cat_id, EntrySource.MANUAL)
    tracker.stop_at(1_000_600)
    assert tracker.current_state().kind == TrackerState.Kind.PAUSED


def test_stop_at_preserves_last_category_id(setup):
    tracker, repo, clock, cat_id = setup
    tracker.start(cat_id, EntrySource.MANUAL)
    tracker.stop_at(1_000_600)
    assert tracker._last_category_id == cat_id


def test_stop_at_returns_none_when_not_tracking(setup):
    tracker, repo, clock, cat_id = setup
    result = tracker.stop_at(1_000_600)
    assert result is None


def test_stop_at_leaves_no_open_entry(setup):
    tracker, repo, clock, cat_id = setup
    tracker.start(cat_id, EntrySource.MANUAL)
    tracker.stop_at(1_000_600)
    assert repo.get_open_entry() is None
