from __future__ import annotations

import time
from typing import Optional

from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from workload_analyzer.core.tracker import TimeTracker, TrackerState
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource


class _DragHandle(QLabel):
    """A label that drags the parent FloatingWidget when clicked and moved."""

    def __init__(self, text: str, parent_widget: "FloatingWidget"):
        super().__init__(text)
        self._fw = parent_widget
        self._drag_pos: Optional[QPoint] = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._fw.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self._fw.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None
        self._fw._save_position()


class FloatingWidget(QWidget):
    widget_hidden = pyqtSignal()  # emitted when user clicks the hide button

    def __init__(self, repo: Repository, tracker: TimeTracker, parent: Optional[QWidget] = None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.repo = repo
        self.tracker = tracker
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet("QWidget { background: #222; color: #eee; border-radius: 6px; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 6)
        layout.setSpacing(3)

        # --- Title bar (drag area + hide button) ---
        title_bar = QWidget()
        title_bar.setStyleSheet("QWidget { background: #333; border-radius: 4px; }")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(6, 2, 4, 2)
        self._drag_handle = _DragHandle("≡ WorkloadAnalyzer", self)
        self._drag_handle.setStyleSheet("color: #aaa; font-size: 11px; background: transparent;")
        title_layout.addWidget(self._drag_handle, 1)
        hide_btn = QPushButton("✕")
        hide_btn.setFixedWidth(20)
        hide_btn.setFlat(True)
        hide_btn.setStyleSheet("color: #aaa; background: transparent; border: none;")
        hide_btn.clicked.connect(self._on_hide)
        title_layout.addWidget(hide_btn)
        layout.addWidget(title_bar)

        # --- Color strip (category + role name) ---
        self._color_strip = QWidget()
        self._color_strip.setStyleSheet("background-color: #444; border-radius: 4px;")
        strip_layout = QHBoxLayout(self._color_strip)
        strip_layout.setContentsMargins(6, 4, 6, 4)
        self._cat_label = QLabel("Not tracking")
        self._cat_label.setStyleSheet("font-weight: bold; background: transparent;")
        strip_layout.addWidget(self._cat_label, 1)
        layout.addWidget(self._color_strip)

        # --- Elapsed time ---
        self.elapsed = QLabel("00:00:00")
        self.elapsed.setStyleSheet("font-family: monospace; font-size: 14px;")
        layout.addWidget(self.elapsed)

        # --- Controls ---
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

    def _on_hide(self) -> None:
        self.hide()
        self.widget_hidden.emit()

    def _restore_position(self) -> None:
        x = self.repo.get_setting("floating_widget_x")
        y = self.repo.get_setting("floating_widget_y")
        if x is not None and y is not None:
            self.move(int(x), int(y))

    def _save_position(self) -> None:
        self.repo.set_setting("floating_widget_x", str(self.x()))
        self.repo.set_setting("floating_widget_y", str(self.y()))

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
            cat_color = cat.color if cat else "#444"
            cat_name = cat.name if cat else "?"
            role_name = role.name if role else ""
            self._cat_label.setText(f"{cat_name}  ·  {role_name}")
            self._color_strip.setStyleSheet(
                f"background-color: {cat_color}; border-radius: 4px;"
            )
            elapsed = int(time.time()) - (state.started_at or int(time.time()))
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            self.elapsed.setText(f"{h:02d}:{m:02d}:{s:02d}")
            self.pause_btn.setText("⏸")
        elif state.kind == TrackerState.Kind.PAUSED:
            self._cat_label.setText("Paused")
            self._color_strip.setStyleSheet("background-color: #555; border-radius: 4px;")
            self.elapsed.setText("--:--:--")
            self.pause_btn.setText("▶")
        else:
            self._cat_label.setText("Not tracking")
            self._color_strip.setStyleSheet("background-color: #444; border-radius: 4px;")
            self.elapsed.setText("00:00:00")
            self.pause_btn.setText("⏸")
