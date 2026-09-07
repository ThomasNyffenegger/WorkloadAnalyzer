"""Recovery popup shown after screen lock or idle absence."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from workload_analyzer.models import Category

# Return codes from RecoveryPopup.exec()
RECOVERY_BOOK    = 1
RECOVERY_DISCARD = 2


def _centered(button: QPushButton, max_width: int = 180) -> QHBoxLayout:
    """Cap a button's width and center it instead of stretching full-width."""
    button.setMaximumWidth(max_width)
    row = QHBoxLayout()
    row.addStretch()
    row.addWidget(button)
    row.addStretch()
    return row


class RecoveryPopup(QDialog):
    """Asks the user what to do with absent time after screen lock or idle.

    Stays open until the user picks an action (no X-button close, no auto-close).

    Parameters
    ----------
    absent_seconds:
        Total time the user was absent.
    reason:
        Human-readable cause, e.g. "Bildschirm gesperrt" or "Inaktivität".
    previous_category:
        The category that was active before absence, or None if tracker was idle.
        Pre-selected in the category dropdown.
    all_categories:
        All active categories to choose from.
    """

    def __init__(
        self,
        absent_seconds: int,
        reason: str,
        previous_category: Optional[Category],
        all_categories: list[Category],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Abwesenheit erkannt")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
        )
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header label
        minutes = max(1, absent_seconds // 60)
        label = QLabel(
            f"Du warst <b>{minutes} Minuten</b> abwesend ({reason}).<br>"
            "Was möchtest du mit dieser Zeit machen?"
        )
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        layout.addWidget(label)

        # Warning for very long absences (>= 8 h)
        long_absence = absent_seconds >= 8 * 3600
        if long_absence:
            warn = QLabel("<i>⚠ Sehr lange Abwesenheit — Verwerfen empfohlen.</i>")
            warn.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(warn)

        # Actions stacked vertically: Verwerfen right below the recommendation,
        # then the category picker, then Buchen to commit it. Buttons are
        # capped in width and centered rather than stretched full-width.
        discard_btn = QPushButton("Verwerfen")
        discard_btn.clicked.connect(lambda: self.done(RECOVERY_DISCARD))
        layout.addLayout(_centered(discard_btn))

        layout.addSpacing(6)

        # Category picker — previous category pre-selected when available
        combo_row = QHBoxLayout()
        combo_row.addWidget(QLabel("Kategorie:"))
        self._category_combo = QComboBox()
        selected_index = 0
        for i, cat in enumerate(all_categories):
            self._category_combo.addItem(cat.name, userData=cat.id)
            if previous_category is not None and cat.id == previous_category.id:
                selected_index = i
        if all_categories:
            self._category_combo.setCurrentIndex(selected_index)
        combo_row.addWidget(self._category_combo, 1)
        layout.addLayout(combo_row)

        layout.addSpacing(6)

        book_btn = QPushButton("Buchen")
        book_btn.clicked.connect(lambda: self.done(RECOVERY_BOOK))
        book_btn.setEnabled(bool(all_categories))
        layout.addLayout(_centered(book_btn))

        if long_absence or previous_category is None:
            discard_btn.setDefault(True)
        else:
            book_btn.setDefault(True)

    def selected_category_id(self) -> Optional[int]:
        """Return the chosen category id. Meaningful only when result == RECOVERY_BOOK."""
        return self._category_combo.currentData()
