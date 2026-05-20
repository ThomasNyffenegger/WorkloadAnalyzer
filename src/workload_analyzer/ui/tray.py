import time
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QApplication

from workload_analyzer.core.tracker import TimeTracker, TrackerState
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource


_icon_cache: dict[str, QIcon] = {}


def _make_color_icon(color_hex: str) -> QIcon:
    if color_hex in _icon_cache:
        return _icon_cache[color_hex]
    pix = QPixmap(32, 32)
    pix.fill(QColor("transparent"))
    p = QPainter(pix)
    p.setBrush(QColor(color_hex))
    p.setPen(QColor("#222"))
    p.drawEllipse(4, 4, 24, 24)
    p.end()
    icon = QIcon(pix)
    _icon_cache[color_hex] = icon
    return icon


class TrayIcon(QObject):
    open_settings = pyqtSignal()
    open_reports = pyqtSignal()
    toggle_widget = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, repo: Repository, tracker: TimeTracker, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.repo = repo
        self.tracker = tracker
        self._outlook_available: bool = True
        self._last_cat_id: Optional[int] = None
        self._last_cat_change_ts: float = time.time()
        self._reminder_active: bool = False
        self._blink_state: bool = False

        self._cached_cat = None   # cached Category object — avoids DB in _on_blink
        self._cached_role = None  # cached Role for the same category
        self._last_refreshed_cat_id: Optional[int] = None  # guards DB refresh in refresh()

        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(2000)
        self._blink_timer.timeout.connect(self._on_blink)

        self.icon = QSystemTrayIcon(_make_color_icon("#888888"))
        self.icon.setToolTip("WorkloadAnalyzer")

        self._build_menu()
        self.icon.show()
        self.icon.activated.connect(self._on_tray_activated)
        self._widget_visible: bool = True

        self._switch_menu_dirty: bool = True
        # Rebuild switch menu lazily when menu is about to show
        self.menu.aboutToShow.connect(self._refresh_switch_menu)

        # Refresh tooltip and icon every 5 seconds (no menu rebuild)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(5000)
        self.refresh()

    def _build_menu(self) -> None:
        self.menu = QMenu()

        self._header_action = QAction("Not tracking", self.menu)
        self._header_action.setEnabled(False)
        self.menu.addAction(self._header_action)
        self.menu.addSeparator()

        self._switch_menu = self.menu.addMenu("Switch to…")
        self._refresh_switch_menu()

        pause_action = QAction("Pause", self.menu)
        pause_action.triggered.connect(self._on_pause)
        self.menu.addAction(pause_action)
        self._pause_action = pause_action

        resume_action = QAction("Resume", self.menu)
        resume_action.triggered.connect(self.tracker.resume)
        self.menu.addAction(resume_action)
        self._resume_action = resume_action

        self.menu.addSeparator()

        self._widget_action = QAction("Widget ausblenden", self.menu)
        self._widget_action.triggered.connect(self.toggle_widget.emit)
        self.menu.addAction(self._widget_action)

        reports_action = QAction("Reports…", self.menu)
        reports_action.triggered.connect(self.open_reports.emit)
        self.menu.addAction(reports_action)

        settings_action = QAction("Settings…", self.menu)
        settings_action.triggered.connect(self.open_settings.emit)
        self.menu.addAction(settings_action)

        self.menu.addSeparator()

        quit_action = QAction("Quit", self.menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        self.menu.addAction(quit_action)

        self.icon.setContextMenu(self.menu)

    def _refresh_switch_menu(self) -> None:
        if not self._switch_menu_dirty:
            return
        self._switch_menu_dirty = False
        self._switch_menu.clear()
        for cat in self.repo.list_categories(active_only=True):
            act = QAction(cat.name, self._switch_menu)
            act.setIcon(_make_color_icon(cat.color or "#888888"))
            act.triggered.connect(lambda _checked=False, cid=cat.id: self._on_switch_category(cid))
            self._switch_menu.addAction(act)

    def _on_switch_category(self, category_id: int) -> None:
        self.tracker.switch_to(category_id, EntrySource.MANUAL)
        self.refresh()

    def invalidate_categories(self) -> None:
        """Force switch-menu rebuild and category/role cache flush on next refresh."""
        self._switch_menu_dirty = True
        self._last_refreshed_cat_id = None

    def refresh(self) -> None:
        state = self.tracker.current_state()

        # Reminder state tracking
        current_cat_id = state.category_id if state.kind == TrackerState.Kind.TRACKING else None
        if current_cat_id != self._last_cat_id:
            self._last_cat_id = current_cat_id
            self._last_cat_change_ts = time.time()
            self._reminder_active = False
            self._blink_state = False
            self._blink_timer.stop()
        elif not self._reminder_active and time.time() - self._last_cat_change_ts > 7200:
            self._reminder_active = True
            self._blink_timer.start()

        if state.kind == TrackerState.Kind.TRACKING and state.category_id is not None:
            if state.category_id != self._last_refreshed_cat_id:
                # Category changed — refresh DB cache for cat and role
                self._last_refreshed_cat_id = state.category_id
                self._cached_cat = self.repo.get_category(state.category_id)
                self._cached_role = self.repo.get_role(self._cached_cat.role_id) if self._cached_cat else None
                if self._cached_cat:
                    role_name = self._cached_role.name if self._cached_role else ""
                    self._header_action.setText(f"{self._cached_cat.name} ({role_name})")
                    self.icon.setToolTip(f"Tracking: {self._cached_cat.name}")
            self._pause_action.setEnabled(True)
            self._resume_action.setEnabled(False)
        elif state.kind == TrackerState.Kind.PAUSED:
            self._header_action.setText("Paused")
            self.icon.setToolTip("WorkloadAnalyzer (paused)")
            self._pause_action.setEnabled(False)
            self._resume_action.setEnabled(True)
        else:
            self._header_action.setText("Not tracking")
            self.icon.setToolTip("WorkloadAnalyzer")
            self._pause_action.setEnabled(False)
            self._resume_action.setEnabled(False)

        if not self._outlook_available:
            self.icon.setToolTip(self.icon.toolTip() + " ⚠ Outlook nicht verfügbar")

        self._apply_icon(state)

    def _on_blink(self) -> None:
        self._blink_state = not self._blink_state
        self._apply_icon(self.tracker.current_state())

    def _apply_icon(self, state: TrackerState) -> None:
        if not self._outlook_available:
            self.icon.setIcon(_make_color_icon("#ff8800"))
            return
        if state.kind == TrackerState.Kind.TRACKING and state.category_id is not None:
            cat = self._cached_cat  # use cached value — no DB call needed
            if cat:
                color = "#888888" if (self._reminder_active and self._blink_state) else cat.color
                self.icon.setIcon(_make_color_icon(color))
            else:
                self.icon.setIcon(_make_color_icon("#888888"))
        elif state.kind == TrackerState.Kind.PAUSED:
            self.icon.setIcon(_make_color_icon("#cccc44"))
        else:
            self.icon.setIcon(_make_color_icon("#888888"))

    def _on_pause(self) -> None:
        self.tracker.pause()
        self.refresh()

    def set_outlook_available(self, available: bool) -> None:
        """Called when OutlookMonitor reports availability change."""
        self._outlook_available = available
        self.refresh()

    def set_widget_visible(self, visible: bool) -> None:
        """Update menu label to reflect floating widget visibility."""
        self._widget_visible = visible
        self._widget_action.setText(
            "Widget ausblenden" if visible else "Widget anzeigen"
        )

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_widget.emit()
