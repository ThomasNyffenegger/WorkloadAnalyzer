"""System monitor — detects screen lock/unlock and idle via Windows APIs."""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import time
from typing import Callable, Optional

from PyQt6.QtCore import QAbstractNativeEventFilter, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

# Windows constants
WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
NOTIFY_FOR_THIS_SESSION = 0


class _MSG(ctypes.Structure):
    """Win32 MSG structure layout (64-bit)."""
    _fields_ = [
        ("hwnd",    ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam",  ctypes.c_size_t),
        ("lParam",  ctypes.c_size_t),
        ("time",    ctypes.c_ulong),
        ("ptX",     ctypes.c_long),
        ("ptY",     ctypes.c_long),
    ]


class SystemMonitor(QObject, QAbstractNativeEventFilter):
    """Detects Windows screen-lock and idle events.

    All Windows API calls are injectable for testing.

    Signals
    -------
    session_locked(lock_ts)              — emitted when screen is locked
    session_unlocked(lock_ts, unlock_ts) — emitted when screen is unlocked
    idle_started(idle_begin_ts)          — emitted when idle threshold exceeded
    user_returned(idle_start_ts, return_ts) — emitted when activity resumes after idle
    """

    session_locked   = pyqtSignal(int)       # lock_ts
    session_unlocked = pyqtSignal(int, int)  # lock_ts, unlock_ts
    idle_started     = pyqtSignal(int)       # idle_begin_ts
    user_returned    = pyqtSignal(int, int)  # idle_start_ts, return_ts

    def __init__(
        self,
        wts_register_fn: Optional[Callable] = None,
        wts_unregister_fn: Optional[Callable] = None,
        get_last_input_fn: Optional[Callable[[], int]] = None,
        clock: Optional[Callable[[], int]] = None,
        idle_threshold_seconds: int = 600,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)

        self._wts_register = wts_register_fn or self._default_register
        self._wts_unregister = wts_unregister_fn or self._default_unregister
        self._get_last_input = get_last_input_fn or self._default_get_last_input
        self._clock = clock or (lambda: int(time.time()))

        self._idle_threshold_ms = idle_threshold_seconds * 1000

        # Internal state
        self._locked: bool = False
        self._idle: bool = False
        self._lock_ts: Optional[int] = None
        self._idle_start_ts: Optional[int] = None

        self._idle_timer = QTimer(self)
        self._idle_timer.timeout.connect(self._poll_idle)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Register for WTS notifications and start idle polling."""
        app = QApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self)
        hwnd = self._get_hwnd()
        if hwnd:
            self._wts_register(hwnd, NOTIFY_FOR_THIS_SESSION)
        self._idle_timer.start(30_000)

    def stop(self) -> None:
        """Unregister WTS notifications and stop idle polling."""
        self._idle_timer.stop()
        app = QApplication.instance()
        if app is not None:
            app.removeNativeEventFilter(self)
        hwnd = self._get_hwnd()
        if hwnd:
            self._wts_unregister(hwnd)

    def set_idle_threshold(self, seconds: int) -> None:
        """Change the idle threshold. Effective on next poll cycle."""
        self._idle_threshold_ms = seconds * 1000

    # ------------------------------------------------------------------
    # QAbstractNativeEventFilter
    # ------------------------------------------------------------------

    def nativeEventFilter(self, event_type: bytes, message) -> tuple[bool, int]:
        try:
            msg = _MSG.from_address(int(message))
            if msg.message == WM_WTSSESSION_CHANGE:
                self._handle_wts_event(msg.wParam)
        except Exception:
            pass
        return False, 0  # never consume the event

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _handle_wts_event(self, w_param: int) -> None:
        now = self._clock()
        if w_param == WTS_SESSION_LOCK and not self._locked:
            self._locked = True
            self._lock_ts = now
            # If idle was active, lock takes over — clear idle silently
            if self._idle:
                self._idle = False
                self._idle_start_ts = None
            self.session_locked.emit(now)

        elif w_param == WTS_SESSION_UNLOCK and self._locked:
            self._locked = False
            assert self._lock_ts is not None, "_lock_ts must be set when _locked is True"
            lock_ts = self._lock_ts
            self._lock_ts = None
            self.session_unlocked.emit(lock_ts, now)

    def _poll_idle(self) -> None:
        """Poll GetLastInputInfo and emit idle/return signals as needed."""
        if self._locked:
            return  # lock takes precedence
        idle_ms = self._get_last_input()
        now = self._clock()

        if not self._idle and idle_ms >= self._idle_threshold_ms:
            self._idle = True
            self._idle_start_ts = now - idle_ms // 1000
            self.idle_started.emit(self._idle_start_ts)

        elif self._idle and idle_ms < self._idle_threshold_ms:
            self._idle = False
            idle_start = self._idle_start_ts or now
            self._idle_start_ts = None
            self.user_returned.emit(idle_start, now)

    @staticmethod
    def _get_hwnd() -> Optional[int]:
        app = QApplication.instance()
        if app is None:
            return None
        for widget in app.topLevelWidgets():
            hwnd = int(widget.winId())
            if hwnd:
                return hwnd
        return None

    @staticmethod
    def _default_register(hwnd: int, flags: int) -> None:
        ctypes.windll.wtsapi32.WTSRegisterSessionNotification(hwnd, flags)  # type: ignore[attr-defined]

    @staticmethod
    def _default_unregister(hwnd: int) -> None:
        ctypes.windll.wtsapi32.WTSUnRegisterSessionNotification(hwnd)  # type: ignore[attr-defined]

    @staticmethod
    def _default_get_last_input() -> int:
        """Return milliseconds since last user input."""
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(lii)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))  # type: ignore[attr-defined]
        get_tick = ctypes.windll.kernel32.GetTickCount64  # type: ignore[attr-defined]
        get_tick.restype = ctypes.c_ulonglong
        elapsed_ms = get_tick() - lii.dwTime
        return int(elapsed_ms)
