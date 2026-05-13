"""Popups for Outlook-driven suggestions and meeting category selection."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from workload_analyzer.models import Category

# Return codes from SuggestionPopup.exec()
SUGGESTION_YES = 1
SUGGESTION_NO = 2
SUGGESTION_NEVER = 3


class SuggestionPopup(QDialog):
    """Non-auto-closing popup asking whether to accept an Outlook category suggestion.

    Call exec() and check the return code against SUGGESTION_YES / SUGGESTION_NO /
    SUGGESTION_NEVER.
    """

    def __init__(
        self,
        outlook_name: str,
        app_category_name: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Kategorie erkannt")
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)

        label = QLabel(
            f'Outlook erkennt: "<b>{outlook_name}</b>" '
            f"→ <b>{app_category_name}</b>. Übernehmen?"
        )
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        layout.addWidget(label)

        btns = QHBoxLayout()
        yes_btn = QPushButton("Ja")
        no_btn = QPushButton("Nein")
        never_btn = QPushButton("Nie mehr")

        yes_btn.setDefault(True)
        yes_btn.clicked.connect(lambda: self.done(SUGGESTION_YES))
        no_btn.clicked.connect(lambda: self.done(SUGGESTION_NO))
        never_btn.clicked.connect(lambda: self.done(SUGGESTION_NEVER))

        btns.addWidget(yes_btn)
        btns.addWidget(no_btn)
        btns.addWidget(never_btn)
        layout.addLayout(btns)


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
