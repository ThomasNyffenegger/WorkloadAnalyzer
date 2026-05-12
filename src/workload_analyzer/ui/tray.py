from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QApplication

from workload_analyzer.core.tracker import TimeTracker, TrackerState
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource


def _make_color_icon(color_hex: str) -> QIcon:
    pix = QPixmap(32, 32)
    pix.fill(QColor("transparent"))
    p = QPainter(pix)
    p.setBrush(QColor(color_hex))
    p.setPen(QColor("#222"))
    p.drawEllipse(4, 4, 24, 24)
    p.end()
    return QIcon(pix)


class TrayIcon(QObject):
    open_settings = pyqtSignal()
    open_reports = pyqtSignal()
    toggle_widget = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, repo: Repository, tracker: TimeTracker, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.repo = repo
        self.tracker = tracker

        self.icon = QSystemTrayIcon(_make_color_icon("#888888"))
        self.icon.setToolTip("WorkloadAnalyzer")

        self._build_menu()
        self.icon.show()

        # Refresh tooltip and menu state every 5 seconds.
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

        widget_action = QAction("Toggle floating widget", self.menu)
        widget_action.triggered.connect(self.toggle_widget.emit)
        self.menu.addAction(widget_action)

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
        self._switch_menu.clear()
        for cat in self.repo.list_categories(active_only=True):
            act = QAction(cat.name, self._switch_menu)
            act.setIcon(_make_color_icon(cat.color))
            act.triggered.connect(lambda _checked=False, cid=cat.id: self.tracker.switch_to(cid, EntrySource.MANUAL))
            self._switch_menu.addAction(act)

    def refresh(self) -> None:
        self._refresh_switch_menu()
        state = self.tracker.current_state()
        if state.kind == TrackerState.Kind.TRACKING and state.category_id is not None:
            cat = self.repo.get_category(state.category_id)
            if cat:
                role = self.repo.get_role(cat.role_id)
                role_name = role.name if role else ""
                self._header_action.setText(f"{cat.name} ({role_name})")
                self.icon.setIcon(_make_color_icon(cat.color))
                self.icon.setToolTip(f"Tracking: {cat.name}")
            self._pause_action.setEnabled(True)
            self._resume_action.setEnabled(False)
        elif state.kind == TrackerState.Kind.PAUSED:
            self._header_action.setText("Paused")
            self.icon.setIcon(_make_color_icon("#cccc44"))
            self.icon.setToolTip("WorkloadAnalyzer (paused)")
            self._pause_action.setEnabled(False)
            self._resume_action.setEnabled(True)
        else:
            self._header_action.setText("Not tracking")
            self.icon.setIcon(_make_color_icon("#888888"))
            self.icon.setToolTip("WorkloadAnalyzer")
            self._pause_action.setEnabled(False)
            self._resume_action.setEnabled(False)

    def _on_pause(self) -> None:
        self.tracker.pause()
        self.refresh()
