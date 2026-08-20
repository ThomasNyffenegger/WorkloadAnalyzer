from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource


@dataclass(frozen=True)
class TrackerState:
    class Kind(str, Enum):
        IDLE = "idle"
        TRACKING = "tracking"
        PAUSED = "paused"

    kind: "TrackerState.Kind"
    category_id: Optional[int]
    started_at: Optional[int]  # unix seconds of the current open entry's start


class TimeTracker:
    # If the app's last heartbeat is older than this when load_state() runs,
    # the app (or the PC) was not actually running in between — an open
    # entry from before the gap must not be resumed, or the offline time
    # would silently be counted as tracked work.
    _STALE_AFTER_SECONDS = 5 * 60

    def __init__(self, repo: Repository, clock: Callable[[], int]):
        self.repo = repo
        self.clock = clock
        self._state = TrackerState(
            kind=TrackerState.Kind.IDLE, category_id=None, started_at=None,
        )
        self._last_category_id: Optional[int] = None

    def current_state(self) -> TrackerState:
        return self._state

    def load_state(self) -> None:
        """Rehydrate tracker from DB (e.g., after app restart).

        An open entry is only resumed if the app's last heartbeat is recent.
        Otherwise the app (or the PC) was not running for the gap, and the
        stale entry is closed at that last heartbeat instead of being
        extended to now — the tracker stays IDLE so the caller can ask the
        user which category to (re)start.
        """
        open_entry = self.repo.get_open_entry()
        if open_entry is None:
            return

        last_heartbeat = self.repo.get_setting("last_heartbeat_ts")
        if last_heartbeat is not None:
            last_heartbeat_ts = int(last_heartbeat)
            if (
                last_heartbeat_ts > open_entry.start_ts
                and self.clock() - last_heartbeat_ts > self._STALE_AFTER_SECONDS
            ):
                self.repo.close_entry(open_entry.id, end_ts=last_heartbeat_ts)
                return

        self._state = TrackerState(
            kind=TrackerState.Kind.TRACKING,
            category_id=open_entry.category_id,
            started_at=open_entry.start_ts,
        )
        self._last_category_id = open_entry.category_id

    def start(self, category_id: int, source: EntrySource) -> None:
        if self._state.kind == TrackerState.Kind.TRACKING:
            return self.switch_to(category_id, source)
        now = self.clock()
        self.repo.start_entry(category_id=category_id, start_ts=now, source=source)
        self._state = TrackerState(
            kind=TrackerState.Kind.TRACKING, category_id=category_id, started_at=now,
        )
        self._last_category_id = category_id

    def switch_to(self, category_id: int, source: EntrySource) -> None:
        if (
            self._state.kind == TrackerState.Kind.TRACKING
            and self._state.category_id == category_id
        ):
            return  # noop
        now = self.clock()
        open_entry = self.repo.get_open_entry()
        if open_entry is not None:
            self.repo.close_entry(open_entry.id, end_ts=now)
        self.repo.start_entry(category_id=category_id, start_ts=now, source=source)
        self._state = TrackerState(
            kind=TrackerState.Kind.TRACKING, category_id=category_id, started_at=now,
        )
        self._last_category_id = category_id

    def pause(self) -> None:
        if self._state.kind != TrackerState.Kind.TRACKING:
            return
        now = self.clock()
        open_entry = self.repo.get_open_entry()
        if open_entry is not None:
            self.repo.close_entry(open_entry.id, end_ts=now)
        self._state = TrackerState(
            kind=TrackerState.Kind.PAUSED,
            category_id=None,
            started_at=None,
        )

    def resume(self) -> None:
        if self._state.kind != TrackerState.Kind.PAUSED:
            return
        if self._last_category_id is None:
            return
        self.start(self._last_category_id, source=EntrySource.MANUAL)

    def stop_at(self, ts: int) -> Optional[int]:
        """Stop the running entry at the given timestamp.

        Returns the category_id of the stopped entry, or None if not tracking.
        Transitions tracker to PAUSED state.
        """
        if self._state.kind != TrackerState.Kind.TRACKING:
            return None
        open_entry = self.repo.get_open_entry()
        if open_entry is not None:
            self.repo.close_entry(open_entry.id, end_ts=ts)
        prev_cat = self._state.category_id
        self._last_category_id = prev_cat
        self._state = TrackerState(
            kind=TrackerState.Kind.PAUSED,
            category_id=None,
            started_at=None,
        )
        return prev_cat
