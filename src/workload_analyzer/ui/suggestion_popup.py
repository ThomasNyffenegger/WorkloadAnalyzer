"""Popups for Outlook-driven suggestions and meeting category selection."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
)

from workload_analyzer.models import Category

# Return codes from SuggestionPopup.exec()
SUGGESTION_YES = 1
SUGGESTION_NO = 2
SUGGESTION_ALWAYS = 3


_COUNTDOWN_SECONDS = 5
_TICK_MS = 100
_SCREEN_MARGIN = 16


class SuggestionPopup(QDialog):
    """Toast-style popup for an auto-detected Outlook category switch.

    Anchored to the bottom-right corner of the screen so it doesn't grab
    focus like a centered modal dialog. Auto-accepts (SUGGESTION_YES) after
    a short countdown, shown as a shrinking progress bar.

    Buttons:
    - "Ja": switch immediately (or just let the countdown run out)
    - "Nein": skip this one suggestion (after 3x for the same pairing, it's
      silenced automatically — see Repository.record_rejection)
    - "Ja, immer": switch now AND remember this Outlook-category →
      App-category pairing as trusted — future detections switch
      automatically without showing this popup again (reactivatable later
      in Einstellungen → Outlook)
    """

    def __init__(
        self,
        outlook_name: str,
        app_category_name: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedWidth(300)
        self.setStyleSheet(
            """
            QDialog { background: #2b2b2b; border: 1px solid #454545; border-radius: 8px; }
            QLabel { color: #e8e8e8; font-size: 12px; }
            QProgressBar { background: #454545; border: none; border-radius: 2px; }
            QProgressBar::chunk { background: #6aa0ff; border-radius: 2px; }
            QPushButton {
                background: #3c3c3c; color: #e8e8e8; border: 1px solid #555555;
                border-radius: 4px; padding: 3px 10px; font-size: 11px;
            }
            QPushButton:hover { background: #484848; }
            QPushButton:default { border-color: #6aa0ff; }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 10)

        label = QLabel(
            f'Kategorie wird gewechselt: "<b>{outlook_name}</b>" → <b>{app_category_name}</b>'
        )
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        layout.addWidget(label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(4)
        layout.addWidget(self._progress_bar)

        btns = QHBoxLayout()
        yes_btn = QPushButton("Ja")
        no_btn = QPushButton("Nein")
        always_btn = QPushButton("Ja, immer")
        always_btn.setToolTip(
            "Diese Zuordnung künftig automatisch übernehmen, ohne Nachfrage."
        )

        yes_btn.setDefault(True)
        yes_btn.clicked.connect(lambda: self.done(SUGGESTION_YES))
        no_btn.clicked.connect(lambda: self.done(SUGGESTION_NO))
        always_btn.clicked.connect(lambda: self.done(SUGGESTION_ALWAYS))

        btns.addWidget(yes_btn)
        btns.addWidget(no_btn)
        btns.addWidget(always_btn)
        layout.addLayout(btns)

        self._remaining_ms = _COUNTDOWN_SECONDS * 1000
        self._progress_bar.setRange(0, self._remaining_ms)
        self._progress_bar.setValue(self._remaining_ms)
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(_TICK_MS)
        self._auto_timer.timeout.connect(self._tick)
        self._auto_timer.start()

    def _tick(self) -> None:
        self._remaining_ms -= _TICK_MS
        self._progress_bar.setValue(max(self._remaining_ms, 0))
        if self._remaining_ms <= 0:
            self.done(SUGGESTION_YES)

    def done(self, result: int) -> None:
        if self._auto_timer.isActive():
            self._auto_timer.stop()
        super().done(result)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        screen = self.screen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        frame = self.frameGeometry()
        x = geo.right() - frame.width() - _SCREEN_MARGIN
        y = geo.bottom() - frame.height() - _SCREEN_MARGIN
        self.move(x, y)


class MeetingCategoryDialog(QDialog):
    """Blocking dialog asking which category to assign to a meeting with no Outlook category.

    Closing via the X button returns QDialog.DialogCode.Rejected — caller keeps
    the current tracking category unchanged.
    """

    def __init__(self, meeting_title: str, categories: list[Category], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Meeting gestartet")
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumWidth(340)

        layout = QVBoxLayout(self)

        label = QLabel(f"Meeting <b>{meeting_title}</b> gestartet. Welche Kategorie?")
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        layout.addWidget(label)

        self._combo = QComboBox()
        for cat in categories:
            self._combo.addItem(cat.name, userData=cat.id)
        layout.addWidget(self._combo)

        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        layout.addWidget(ok_btn)

    def selected_category_id(self) -> Optional[int]:
        return self._combo.currentData()
