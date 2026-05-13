"""Tests for SystemMonitor — screen lock and idle detection.

All tests bypass real Windows APIs via injectable dependencies.
WTS events are simulated by calling _handle_wts_event() directly.
Idle state is controlled via fake get_last_input_fn.
"""
from workload_analyzer.services.system_monitor import SystemMonitor

WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8


def make_monitor(idle_threshold_seconds=600):
    """Return a SystemMonitor with all Windows APIs replaced by fakes."""
    ts = [1_000_000]
    fake_idle_ms = [0]

    mon = SystemMonitor(
        wts_register_fn=lambda hwnd, flags: None,
        wts_unregister_fn=lambda hwnd: None,
        get_last_input_fn=lambda: fake_idle_ms[0],
        clock=lambda: ts[0],
        idle_threshold_seconds=idle_threshold_seconds,
    )
    mon._ts = ts
    mon._fake_idle_ms = fake_idle_ms
    return mon


def fire_lock(mon):
    mon._ts[0] += 1
    mon._handle_wts_event(WTS_SESSION_LOCK)


def fire_unlock(mon):
    mon._ts[0] += 1
    mon._handle_wts_event(WTS_SESSION_UNLOCK)


# --- Screen lock tests ---

def test_lock_emits_session_locked():
    mon = make_monitor()
    results = []
    mon.session_locked.connect(lambda ts: results.append(ts))
    mon._ts[0] = 1_000_100
    fire_lock(mon)
    assert results == [1_000_101]
    assert mon._locked is True


def test_unlock_emits_session_unlocked():
    mon = make_monitor()
    results = []
    mon.session_unlocked.connect(lambda lock, unlock: results.append((lock, unlock)))
    mon._ts[0] = 1_000_100
    fire_lock(mon)
    lock_ts = mon._lock_ts
    mon._ts[0] = 1_000_700
    fire_unlock(mon)
    assert len(results) == 1
    lock_emitted, unlock_emitted = results[0]
    assert lock_emitted == lock_ts
    assert unlock_emitted > lock_emitted
    assert mon._locked is False


def test_double_lock_ignored():
    mon = make_monitor()
    results = []
    mon.session_locked.connect(lambda ts: results.append(ts))
    fire_lock(mon)
    fire_lock(mon)  # second lock while already locked — ignored
    assert len(results) == 1


def test_unlock_without_prior_lock_ignored():
    mon = make_monitor()
    results = []
    mon.session_unlocked.connect(lambda l, u: results.append((l, u)))
    fire_unlock(mon)  # no prior lock
    assert results == []


def test_lock_ts_stored_correctly():
    mon = make_monitor()
    mon._ts[0] = 5_000_000
    fire_lock(mon)
    assert mon._lock_ts == 5_000_001
