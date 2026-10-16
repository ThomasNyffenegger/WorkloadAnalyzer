"""Detects that the machine was suspended (standby/hibernate) via a wall-clock jump."""
from typing import Callable, Optional


class SuspendDetector:
    """Spots a standby/hibernate by an oversized gap between two ticks.

    Idle detection can't see suspend: GetLastInputInfo's tick count doesn't
    advance while the machine sleeps, so after resume the user looks like
    they were only idle for the (short) awake time. App timers are frozen
    during suspend as well, so the only trace is that the wall clock jumped
    between two ticks that should have been seconds apart.
    """

    def __init__(self, threshold_seconds: int, clock: Callable[[], int]):
        self._threshold = threshold_seconds
        self._clock = clock
        self._last_tick = clock()

    def tick(self) -> Optional[int]:
        """Record "now".

        Returns the previous tick's timestamp — the last moment the machine
        was known to be running — if the gap since then reached the
        threshold, otherwise None.
        """
        now = self._clock()
        previous = self._last_tick
        self._last_tick = now
        return previous if now - previous >= self._threshold else None
