"""Recovery popup shown after screen lock or idle absence."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QHBoxLayout, QLabel,
    QPushButton, QRadioButton, QVBoxLayout,
)

from workload_analyzer.models import Category

# Return codes from RecoveryPopup.exec()
RECOVERY_PREVIOUS = 1
RECOVERY_OTHER    = 2
RECOVERY_DISCARD  = 3


class RecoveryPopup(QDialog):
    """Asks the user what to do with absent time after screen lock or idle.

    Stays open until user clicks "Bestätigen" (no X-button close, no auto-close).

    Parameters
    ----------
    absent_seconds:
        Total time the user was absent.
    reason:
        Human-readable cause, e.g. "Bildschirm gesperrt" or "Inaktivität".
    previous_category:
        The category that was active before absence, or None if tracker was idle.
    all_categories:
        All active categories for the "other" picker.
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

        self._other_combo: Optional[QComboBox] = None
        self._radio_prev: Optional[QRadioButton] = None

        layout = QVBoxLayout(self)

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

        self._group = QButtonGroup(self)

        # Option A: previous category (hidden when previous_category is None)
        if previous_category is not None:
            self._radio_prev = QRadioButton(
                f"Auf vorherige Kategorie buchen  ({previous_category.name})"
            )
            self._radio_prev.setChecked(not long_absence)
            self._group.addButton(self._radio_prev, RECOVERY_PREVIOUS)
            layout.addWidget(self._radio_prev)

        # Option B: other category
        other_row = QHBoxLayout()
        self._radio_other = QRadioButton("Andere Kategorie wählen")
        self._group.addButton(self._radio_other, RECOVERY_OTHER)
        other_row.addWidget(self._radio_other)
        self._other_combo = QComboBox()
        for cat in all_categories:
            self._other_combo.addItem(cat.name, userData=cat.id)
        other_row.addWidget(self._other_combo, 1)
        layout.addLayout(other_row)

        # Option C: discard
        self._radio_discard = QRadioButton("Verwerfen (Zeit nicht buchen)")
        if long_absence or previous_category is None:
            self._radio_discard.setChecked(True)
        self._group.addButton(self._radio_discard, RECOVERY_DISCARD)
        layout.addWidget(self._radio_discard)

        # Confirm button — only way to close
        confirm = QPushButton("Bestätigen")
        confirm.setDefault(True)
        confirm.clicked.connect(self._on_confirm)
        layout.addWidget(confirm)

    def _on_confirm(self) -> None:
        choice = self._group.checkedId()
        if choice == -1:
            choice = RECOVERY_DISCARD
        self.done(choice)

    def selected_category_id(self) -> Optional[int]:
        """Return the chosen 'other' category id. Meaningful only when result == RECOVERY_OTHER."""
        if self._other_combo is None:
            return None
        return self._other_combo.currentData()
