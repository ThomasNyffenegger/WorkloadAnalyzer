"""Outlook COM monitor — polls Outlook every N seconds and emits Qt signals."""
from __future__ import annotations

import datetime
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class OutlookMonitor(QObject):
    """Polls classic Outlook via COM (main thread, QTimer) and emits signals.

    Pass ``outlook_factory`` in tests to inject a fake Outlook application
    object instead of the real COM server.
    """

    category_detected = pyqtSignal(str)        # Outlook category name from active inspector
    meeting_started = pyqtSignal(str, object)   # (meeting title, Optional[str] outlook_category)
    meeting_ended = pyqtSignal()
    availability_changed = pyqtSignal(bool)     # True = Outlook reachable

    def __init__(
        self,
        outlook_factory: Optional[Callable] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        if outlook_factory is not None:
            self._factory = outlook_factory
        else:
            self._factory = self._default_factory

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)

        # Internal state for debouncing
        self._last_category: Optional[str] = None
        self._in_meeting: bool = False
        self._available: Optional[bool] = None  # None = never polled yet
        self._interval_ms: int = 15_000

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, interval_seconds: int = 15) -> None:
        """Start polling at the given interval."""
        self._interval_ms = interval_seconds * 1000
        self._timer.start(self._interval_ms)

    def stop(self) -> None:
        """Stop polling."""
        self._timer.stop()

    def set_interval(self, seconds: int) -> None:
        """Change poll interval. Persists across stop/start."""
        self._interval_ms = seconds * 1000
        if self._timer.isActive():
            self._timer.start(self._interval_ms)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _default_factory():
        import win32com.client  # noqa: PLC0415 — lazy import, Windows only
        return win32com.client.GetActiveObject("Outlook.Application")

    def _poll(self) -> None:
        """Single poll cycle. Called by QTimer and directly in tests."""
        try:
            app = self._factory()
        except Exception:
            if self._available is not False:
                self._available = False
                self.availability_changed.emit(False)
            if self._in_meeting:
                self._in_meeting = False
                self.meeting_ended.emit()
            return

        if self._available is not True:
            self._available = True
            self.availability_changed.emit(True)

        self._check_inspector(app)
        self._check_meeting(app)

    def _check_inspector(self, app) -> None:
        """Detect the category of the item open in the active inspector."""
        category: Optional[str] = None
        try:
            inspector = app.ActiveInspector()
            if inspector is not None:
                cats = inspector.CurrentItem.Categories
                if cats:
                    category = cats.split(",")[0].strip() or None
        except Exception:
            pass

        if category != self._last_category:
            self._last_category = category
            if category:
                self.category_detected.emit(category)

    def _check_meeting(self, app) -> None:
        """Detect whether a calendar appointment is currently running."""
        now = datetime.datetime.now()
        title: Optional[str] = None
        outlook_cat: Optional[str] = None

        try:
            ns = app.GetNamespace("MAPI")
            folder = ns.GetDefaultFolder(9)  # olFolderCalendar = 9
            for item in folder.Items:
                try:
                    if item.Start <= now <= item.End:
                        title = item.Subject
                        cats = item.Categories
                        outlook_cat = cats.split(",")[0].strip() if cats else None
                        break
                except Exception:
                    continue
        except Exception:
            pass

        if title is not None and not self._in_meeting:
            self._in_meeting = True
            self.meeting_started.emit(title, outlook_cat)
        elif title is None and self._in_meeting:
            self._in_meeting = False
            self.meeting_ended.emit()
