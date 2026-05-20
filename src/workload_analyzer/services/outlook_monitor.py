"""Outlook COM monitor — polls Outlook every N seconds and emits Qt signals.

COM polling runs in a background QThread (_OutlookWorker) to avoid blocking
the main thread during calendar iteration.
"""
from __future__ import annotations

import datetime
import logging
from typing import Callable, Optional

_log = logging.getLogger(__name__)

from PyQt6.QtCore import QMetaObject, QObject, QThread, QTimer, Qt, pyqtSignal, pyqtSlot


class _OutlookWorker(QObject):
    """Runs inside a QThread. All COM calls happen here."""

    category_detected = pyqtSignal(str)
    meeting_started = pyqtSignal(str, object)
    meeting_ended = pyqtSignal()
    availability_changed = pyqtSignal(bool)

    def __init__(self, outlook_factory: Callable, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._factory = outlook_factory
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._last_category: Optional[str] = None
        self._in_meeting: bool = False
        self._available: Optional[bool] = None
        self._interval_ms: int = 15_000

    @pyqtSlot()
    def start_polling(self) -> None:
        """Called in worker thread when QThread starts."""
        try:
            import pythoncom  # noqa: PLC0415
            pythoncom.CoInitialize()
        except Exception:
            pass  # Not on Windows or pythoncom unavailable — tests run without it
        self._timer.start(self._interval_ms)

    @pyqtSlot()
    def stop_polling(self) -> None:
        """Stop timer and uninitialize COM. Called before thread quits."""
        self._timer.stop()
        try:
            import pythoncom  # noqa: PLC0415
            pythoncom.CoUninitialize()
        except Exception:
            pass

    @pyqtSlot(int)
    def update_interval(self, ms: int) -> None:
        self._interval_ms = ms
        if self._timer.isActive():
            self._timer.start(ms)

    def _poll(self) -> None:
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
        category: Optional[str] = None
        try:
            inspector = app.ActiveInspector()
            if inspector is not None:
                cats = inspector.CurrentItem.Categories
                if cats:
                    category = cats.split(",")[0].strip() or None
        except Exception as exc:
            _log.debug("_check_inspector error: %s", exc)

        if category != self._last_category:
            self._last_category = category
            if category:
                self.category_detected.emit(category)

    def _check_meeting(self, app) -> None:
        now = datetime.datetime.now()
        title: Optional[str] = None
        outlook_cat: Optional[str] = None

        try:
            ns = app.GetNamespace("MAPI")
            folder = ns.GetDefaultFolder(9)
            for item in folder.Items:
                try:
                    if item.Start <= now <= item.End:
                        title = item.Subject
                        cats = item.Categories
                        outlook_cat = cats.split(",")[0].strip() if cats else None
                        break
                except Exception as exc:
                    _log.debug("_check_meeting item error: %s", exc)
                    continue
        except Exception as exc:
            _log.debug("_check_meeting namespace error: %s", exc)

        if title is not None and not self._in_meeting:
            self._in_meeting = True
            self.meeting_started.emit(title, outlook_cat)
        elif title is None and self._in_meeting:
            self._in_meeting = False
            self.meeting_ended.emit()


class OutlookMonitor(QObject):
    """Public API — same signals and methods as before. COM runs in background thread."""

    category_detected = pyqtSignal(str)
    meeting_started = pyqtSignal(str, object)
    meeting_ended = pyqtSignal()
    availability_changed = pyqtSignal(bool)

    _request_interval = pyqtSignal(int)  # internal: route set_interval to worker

    def __init__(
        self,
        outlook_factory: Optional[Callable] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        factory = outlook_factory if outlook_factory is not None else self._default_factory

        self._worker = _OutlookWorker(factory)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)

        # Wire lifecycle
        self._thread.started.connect(self._worker.start_polling)

        # Forward worker signals to OutlookMonitor signals (queued across threads)
        self._worker.category_detected.connect(self.category_detected)
        self._worker.meeting_started.connect(self.meeting_started)
        self._worker.meeting_ended.connect(self.meeting_ended)
        self._worker.availability_changed.connect(self.availability_changed)

        # Route interval changes to worker thread
        self._request_interval.connect(self._worker.update_interval)

    def start(self, interval_seconds: int = 15) -> None:
        if self._thread.isRunning():
            return
        self._worker._interval_ms = interval_seconds * 1000
        self._thread.start()

    def stop(self) -> None:
        if self._thread.isRunning():
            QMetaObject.invokeMethod(
                self._worker, "stop_polling",
                Qt.ConnectionType.BlockingQueuedConnection,
            )
            self._thread.quit()
            if not self._thread.wait(3000):  # 3s timeout — don't block forever if COM hangs
                _log.warning("OutlookMonitor worker thread did not stop within 3s; forcing termination")
                self._thread.terminate()

    def set_interval(self, seconds: int) -> None:
        self._request_interval.emit(seconds * 1000)

    @staticmethod
    def _default_factory():
        import win32com.client  # noqa: PLC0415
        return win32com.client.GetActiveObject("Outlook.Application")
