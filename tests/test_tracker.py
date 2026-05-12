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
    c1 = repo.create_category(name="A", color="#0", role_id=rid)
    c2 = repo.create_category(name="B", color="#0", role_id=rid)
    clock = FakeClock()
    tracker = TimeTracker(repo=repo, clock=clock)
    yield tracker, repo, clock, c1, c2
    conn.close()


def test_initial_state_is_idle(setup):
    tracker, *_ = setup
    state = tracker.current_state()
    assert state.kind == TrackerState.Kind.IDLE
    assert state.category_id is None


def test_start_creates_open_entry(setup):
    tracker, repo, clock, c1, _ = setup
    tracker.start(category_id=c1, source=EntrySource.MANUAL)
    state = tracker.current_state()
    assert state.kind == TrackerState.Kind.TRACKING
    assert state.category_id == c1
    assert repo.get_open_entry() is not None


def test_switch_closes_previous_opens_new(setup):
    tracker, repo, clock, c1, c2 = setup
    tracker.start(category_id=c1, source=EntrySource.MANUAL)
    clock.advance(60)
    tracker.switch_to(category_id=c2, source=EntrySource.MANUAL)
    entries = repo.list_entries_between(0, 99999)
    assert len(entries) == 2
    closed = [e for e in entries if not e.is_active()]
    open_ = [e for e in entries if e.is_active()]
    assert len(closed) == 1
    assert closed[0].category_id == c1
    assert closed[0].duration_seconds() == 60
    assert len(open_) == 1
    assert open_[0].category_id == c2


def test_switch_to_same_category_is_noop(setup):
    tracker, repo, clock, c1, _ = setup
    tracker.start(category_id=c1, source=EntrySource.MANUAL)
    clock.advance(30)
    tracker.switch_to(category_id=c1, source=EntrySource.MANUAL)
    entries = repo.list_entries_between(0, 99999)
    assert len(entries) == 1  # still one open entry


def test_pause_closes_open_entry(setup):
    tracker, repo, clock, c1, _ = setup
    tracker.start(category_id=c1, source=EntrySource.MANUAL)
    clock.advance(60)
    tracker.pause()
    assert tracker.current_state().kind == TrackerState.Kind.PAUSED
    assert repo.get_open_entry() is None


def test_resume_opens_new_entry_on_last_category(setup):
    tracker, repo, clock, c1, _ = setup
    tracker.start(category_id=c1, source=EntrySource.MANUAL)
    clock.advance(60)
    tracker.pause()
    clock.advance(120)
    tracker.resume()
    state = tracker.current_state()
    assert state.kind == TrackerState.Kind.TRACKING
    assert state.category_id == c1


def test_pause_when_idle_is_noop(setup):
    tracker, *_ = setup
    tracker.pause()
    assert tracker.current_state().kind == TrackerState.Kind.IDLE


def test_load_state_from_db_picks_up_open_entry(setup, tmp_db_path):
    tracker, repo, clock, c1, _ = setup
    tracker.start(category_id=c1, source=EntrySource.MANUAL)
    # Recreate tracker on same db — simulates app restart
    tracker2 = TimeTracker(repo=repo, clock=clock)
    tracker2.load_state()
    assert tracker2.current_state().kind == TrackerState.Kind.TRACKING
    assert tracker2.current_state().category_id == c1
