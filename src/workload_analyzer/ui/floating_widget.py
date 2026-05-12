from typing import Optional

from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtGui import QMouseEvent, QColor
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from workload_analyzer.core.tracker import TimeTracker, TrackerState
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource


class FloatingWidget(QWidget):
    def __init__(self, repo: Repository, tracker: TimeTracker, parent: Optional[QWidget] = None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.repo = repo
        self.tracker = tracker
        self._drag_pos: Optional[QPoint] = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet("QWidget { background: #222; color: #eee; border-radius: 6px; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        top = QHBoxLayout()
        self.dot = QLabel("●")
        self.dot.setStyleSheet("color: #888; font-size: 18px;")
        top.addWidget(self.dot)
        self.label = QLabel("Not tracking")
        top.addWidget(self.label, 1)
        layout.addLayout(top)

        self.elapsed = QLabel("00:00:00")
        self.elapsed.setStyleSheet("font-family: monospace; font-size: 14px;")
        layout.addWidget(self.elapsed)

        bottom = QHBoxLayout()
        self.combo = QComboBox()
        bottom.addWidget(self.combo, 1)
        self.pause_btn = QPushButton("⏸")
        self.pause_btn.setFixedWidth(32)
        self.pause_btn.clicked.connect(self._on_pause)
        bottom.addWidget(self.pause_btn)
        layout.addLayout(bottom)

        self.combo.activated.connect(self._on_combo)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(1000)

        self._restore_position()
        self.refresh()

    def _restore_position(self) -> None:
        x = self.repo.get_setting("floating_widget_x")
        y = self.repo.get_setting("floating_widget_y")
        if x is not None and y is not None:
            self.move(int(x), int(y))

    def _save_position(self) -> None:
        self.repo.set_setting("floating_widget_x", str(self.x()))
        self.repo.set_setting("floating_widget_y", str(self.y()))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None
        self._save_position()

    def _populate_combo(self) -> None:
        current = self.combo.currentData()
        self.combo.blockSignals(True)
        self.combo.clear()
        for c in self.repo.list_categories(active_only=True):
            self.combo.addItem(c.name, c.id)
        state = self.tracker.current_state()
        if state.category_id is not None:
            idx = self.combo.findData(state.category_id)
            if idx >= 0:
                self.combo.setCurrentIndex(idx)
        elif current is not None:
            idx = self.combo.findData(current)
            if idx >= 0:
                self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)

    def _on_combo(self, _index: int) -> None:
        cid = self.combo.currentData()
        if cid is not None:
            self.tracker.switch_to(cid, EntrySource.MANUAL)
            self.refresh()

    def _on_pause(self) -> None:
        state = self.tracker.current_state()
        if state.kind == TrackerState.Kind.TRACKING:
            self.tracker.pause()
        elif state.kind == TrackerState.Kind.PAUSED:
            self.tracker.resume()
        self.refresh()

    def refresh(self) -> None:
        self._populate_combo()
        state = self.tracker.current_state()
        if state.kind == TrackerState.Kind.TRACKING and state.category_id is not None:
            cat = self.repo.get_category(state.category_id)
            role = self.repo.get_role(cat.role_id) if cat else None
            self.dot.setStyleSheet(f"color: {cat.color if cat else '#888'}; font-size: 18px;")
            self.label.setText(f"{cat.name}  ·  {role.name if role else ''}")
            import time
            elapsed = int(time.time()) - (state.started_at or int(time.time()))
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            self.elapsed.setText(f"{h:02d}:{m:02d}:{s:02d}")
            self.pause_btn.setText("⏸")
        elif state.kind == TrackerState.Kind.PAUSED:
            self.dot.setStyleSheet("color: #cc4; font-size: 18px;")
            self.label.setText("Paused")
            self.elapsed.setText("--:--:--")
            self.pause_btn.setText("▶")
        else:
            self.dot.setStyleSheet("color: #888; font-size: 18px;")
            self.label.setText("Not tracking")
            self.elapsed.setText("00:00:00")
            self.pause_btn.setText("⏸")
