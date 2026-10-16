from workload_analyzer.core.suspend_detector import SuspendDetector


class FakeClock:
    def __init__(self, now: int = 1_000_000):
        self.now = now

    def __call__(self) -> int:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += seconds


def test_regular_ticks_report_no_gap():
    clock = FakeClock()
    detector = SuspendDetector(threshold_seconds=600, clock=clock)
    for _ in range(10):
        clock.advance(5)
        assert detector.tick() is None


def test_gap_below_threshold_is_ignored():
    clock = FakeClock()
    detector = SuspendDetector(threshold_seconds=600, clock=clock)
    clock.advance(599)
    assert detector.tick() is None


def test_gap_at_threshold_returns_previous_tick():
    clock = FakeClock(1_000_000)
    detector = SuspendDetector(threshold_seconds=600, clock=clock)
    clock.advance(5)
    detector.tick()  # last known-alive moment: 1_000_005
    clock.advance(16 * 3600)  # standby overnight
    assert detector.tick() == 1_000_005


def test_detection_resets_after_reporting():
    clock = FakeClock()
    detector = SuspendDetector(threshold_seconds=600, clock=clock)
    clock.advance(3600)
    assert detector.tick() is not None
    clock.advance(5)
    assert detector.tick() is None  # back to normal, no repeat report
