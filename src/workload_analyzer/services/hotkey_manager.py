import ctypes
import ctypes.wintypes
import logging
from typing import Optional

from PyQt6.QtCore import QAbstractNativeEventFilter, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget

_log = logging.getLogger(__name__)

MOD_CONTROL = 0x0002
MOD_SHIFT   = 0x0004
WM_HOTKEY   = 0x0312
_VK = {i: 0x30 + i for i in range(1, 10)}  # 0x31=VK_1 … 0x39=VK_9


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, event_type, message):
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                self._callback(int(msg.wParam))
                return True, 0
        except Exception:
            pass
        return False, 0


class GlobalHotkeyManager(QWidget):
    triggered = pyqtSignal(int)  # emits 1..9

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._registered: list[int] = []
        # Invisible sink widget — keeps a reference alive and provides winId if needed
        self._sink = QWidget(self)
        self._sink.setFixedSize(0, 0)
        self._sink.hide()
        self._filter = _HotkeyFilter(self._on_hotkey)
        QApplication.instance().installNativeEventFilter(self._filter)

    def _on_hotkey(self, n: int) -> None:
        self.triggered.emit(n)

    def register(self, n: int) -> None:
        if n not in range(1, 10):
            return
        ok = ctypes.windll.user32.RegisterHotKey(None, n, MOD_CONTROL | MOD_SHIFT, _VK[n])
        if ok:
            self._registered.append(n)
        else:
            _log.warning("Could not register Ctrl+Shift+%d (already in use?)", n)

    def unregister_all(self) -> None:
        for n in self._registered:
            ctypes.windll.user32.UnregisterHotKey(None, n)
        self._registered.clear()
        app = QApplication.instance()
        if app:
            app.removeNativeEventFilter(self._filter)
