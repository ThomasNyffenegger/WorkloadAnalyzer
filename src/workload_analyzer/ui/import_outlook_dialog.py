"""Dialog to import categories from classic Outlook into WorkloadAnalyzer."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from workload_analyzer.db.repository import Repository


# Mapping from Outlook OlCategoryColor enum int to approximate hex colour.
_OUTLOOK_COLORS: dict[int, str] = {
    0: "#888888",   # None
    1: "#e7a1a2",   # Red
    2: "#f9ba89",   # Orange
    3: "#f7d67b",   # Peach
    4: "#fcf26b",   # Yellow
    5: "#9dc27b",   # Green
    6: "#84b5b7",   # Teal
    7: "#d0c57b",   # Olive
    8: "#7ba5c5",   # Blue
    9: "#9999d8",   # Purple
    10: "#c27ba0",  # Maroon
    11: "#a0a0a0",  # Steel
    12: "#8c8c8c",  # DarkSteel
    13: "#7f7f7f",  # Gray
    14: "#595959",  # DarkGray
    15: "#222222",  # Black
    16: "#c53030",  # DarkRed
    17: "#d65f27",  # DarkOrange
    18: "#d4ac35",  # DarkPeach
    19: "#d4c730",  # DarkYellow
    20: "#5d9e4a",  # DarkGreen
    21: "#3f8c8e",  # DarkTeal
    22: "#7f7830",  # DarkOlive
    23: "#3560a3",  # DarkBlue
    24: "#6060a0",  # DarkPurple
    25: "#a03c78",  # DarkMaroon
}


def _outlook_color_to_hex(color_int: int) -> str:
    return _OUTLOOK_COLORS.get(color_int, "#888888")


class ImportOutlookDialog(QDialog):
    """Reads all Outlook categories via COM and lets the user map them to app categories.

    For each checked Outlook category the user can either:
    - Create a new app category (option "— Neu anlegen —")
    - Assign to an existing app category

    On OK, new categories are created and existing ones get their
    ``outlook_category_name`` updated.
    """

    def __init__(self, repo: Repository, parent=None):
        super().__init__(parent)
        self._repo = repo
        self.setWindowTitle("Aus Outlook importieren")
        self.resize(640, 420)
        self._app_categories = repo.list_categories()
        self._roles = repo.list_roles()
        self._outlook_data: list[tuple[str, str]] = []  # (name, color_hex)
        self._build_ui()
        self._load_outlook_categories()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Wähle Outlook-Kategorien zum Importieren aus:"))

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Outlook-Name", "Farbe", "Importieren", "App-Kategorie"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _load_outlook_categories(self) -> None:
        try:
            import win32com.client
            app = win32com.client.GetActiveObject("Outlook.Application")
            ns = app.GetNamespace("MAPI")
            outlook_cats = ns.Categories
        except Exception as exc:
            QMessageBox.critical(
                self, "Outlook nicht verfügbar",
                f"Outlook konnte nicht geöffnet werden:\n{exc}"
            )
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self.reject)
            return

        self._table.setRowCount(0)
        self._outlook_data.clear()

        for i in range(outlook_cats.Count):
            try:
                cat = outlook_cats.Item(i + 1)
                name = cat.Name
                color_hex = _outlook_color_to_hex(int(cat.Color))
            except Exception:
                continue

            self._outlook_data.append((name, color_hex))
            row = self._table.rowCount()
            self._table.insertRow(row)

            # Column 0: name
            self._table.setItem(row, 0, QTableWidgetItem(name))

            # Column 1: colour swatch
            dot = QLabel()
            dot.setFixedSize(16, 16)
            dot.setStyleSheet(
                f"background-color: {color_hex}; border-radius: 8px;"
            )
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.addWidget(dot)
            cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            self._table.setCellWidget(row, 1, cell)

            # Column 2: checkbox
            cb = QCheckBox()
            cb_cell = QWidget()
            cb_layout = QHBoxLayout(cb_cell)
            cb_layout.addWidget(cb)
            cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            self._table.setCellWidget(row, 2, cb_cell)

            # Column 3: app category combo
            combo = QComboBox()
            combo.addItem("— Neu anlegen —", userData=None)
            for app_cat in self._app_categories:
                combo.addItem(app_cat.name, userData=app_cat.id)
            self._table.setCellWidget(row, 3, combo)

    def _save(self) -> None:
        if not self._roles:
            QMessageBox.warning(self, "Fehler", "Bitte zuerst eine Rolle anlegen.")
            return

        default_role_id = self._roles[0].id

        for row in range(self._table.rowCount()):
            cb_cell = self._table.cellWidget(row, 2)
            cb = cb_cell.findChild(QCheckBox)
            if not cb or not cb.isChecked():
                continue

            outlook_name, color_hex = self._outlook_data[row]
            combo: QComboBox = self._table.cellWidget(row, 3)
            app_cat_id: Optional[int] = combo.currentData()

            if app_cat_id is None:
                # Create a new app category
                self._repo.create_category(
                    name=outlook_name,
                    color=color_hex,
                    role_id=default_role_id,
                    outlook_category_name=outlook_name,
                )
            else:
                # Update existing category's Outlook mapping
                cat = self._repo.get_category(app_cat_id)
                if cat:
                    self._repo.update_category(
                        app_cat_id,
                        cat.name,
                        cat.color,
                        cat.role_id,
                        cat.active,
                        outlook_category_name=outlook_name,
                    )

        self.accept()
