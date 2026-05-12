from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from workload_analyzer.db.repository import Repository


class SettingsWindow(QDialog):
    def __init__(self, repo: Repository, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("WorkloadAnalyzer — Einstellungen")
        self.resize(720, 520)

        tabs = QTabWidget(self)
        tabs.addTab(self._build_categories_tab(), "Rollen & Kategorien")
        tabs.addTab(self._build_general_tab(), "Allgemein")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    # --- Roles & Categories ---

    def _build_categories_tab(self) -> QWidget:
        w = QWidget(self)
        outer = QHBoxLayout(w)

        # Left: roles
        roles_box = QVBoxLayout()
        roles_box.addWidget(QLabel("Rollen"))
        self.roles_list = QListWidget()
        roles_box.addWidget(self.roles_list)
        rh = QHBoxLayout()
        add_role = QPushButton("Hinzufügen")
        add_role.clicked.connect(self._add_role)
        rename_role = QPushButton("Umbenennen")
        rename_role.clicked.connect(self._rename_role)
        del_role = QPushButton("Löschen")
        del_role.clicked.connect(self._delete_role)
        rh.addWidget(add_role)
        rh.addWidget(rename_role)
        rh.addWidget(del_role)
        roles_box.addLayout(rh)
        outer.addLayout(roles_box, 1)

        # Right: categories
        cats_box = QVBoxLayout()
        cats_box.addWidget(QLabel("Kategorien"))
        self.cat_table = QTableWidget(0, 5)
        self.cat_table.setHorizontalHeaderLabels(["Name", "Rolle", "Farbe", "Aktiv", "Outlook-Name"])
        self.cat_table.horizontalHeader().setStretchLastSection(True)
        cats_box.addWidget(self.cat_table)

        ch = QHBoxLayout()
        add_cat = QPushButton("Hinzufügen")
        add_cat.clicked.connect(self._add_category)
        edit_cat = QPushButton("Bearbeiten")
        edit_cat.clicked.connect(self._edit_category)
        del_cat = QPushButton("Löschen")
        del_cat.clicked.connect(self._delete_category)
        import_outlook = QPushButton("Aus Outlook importieren (Phase 2)")
        import_outlook.setEnabled(False)
        ch.addWidget(add_cat)
        ch.addWidget(edit_cat)
        ch.addWidget(del_cat)
        ch.addWidget(import_outlook)
        cats_box.addLayout(ch)
        outer.addLayout(cats_box, 2)

        self._refresh_roles()
        self._refresh_categories()
        return w

    def _refresh_roles(self) -> None:
        self.roles_list.clear()
        for r in self.repo.list_roles():
            item = QListWidgetItem(r.name)
            item.setData(Qt.ItemDataRole.UserRole, r.id)
            self.roles_list.addItem(item)

    def _refresh_categories(self) -> None:
        cats = self.repo.list_categories()
        roles = {r.id: r.name for r in self.repo.list_roles()}
        self.cat_table.setRowCount(len(cats))
        for row, c in enumerate(cats):
            self.cat_table.setItem(row, 0, QTableWidgetItem(c.name))
            self.cat_table.setItem(row, 1, QTableWidgetItem(roles.get(c.role_id, "")))
            color_item = QTableWidgetItem(c.color)
            color_item.setBackground(QColor(c.color))
            self.cat_table.setItem(row, 2, color_item)
            self.cat_table.setItem(row, 3, QTableWidgetItem("✓" if c.active else "—"))
            self.cat_table.setItem(row, 4, QTableWidgetItem(c.outlook_category_name or ""))
            self.cat_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, c.id)

    def _add_role(self) -> None:
        name, ok = QInputDialog.getText(self, "Neue Rolle", "Name:")
        if ok and name.strip():
            try:
                self.repo.create_role(name.strip())
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))
            self._refresh_roles()

    def _rename_role(self) -> None:
        item = self.roles_list.currentItem()
        if not item:
            return
        rid = item.data(Qt.ItemDataRole.UserRole)
        new, ok = QInputDialog.getText(self, "Umbenennen", "Name:", text=item.text())
        if ok and new.strip():
            self.repo.rename_role(rid, new.strip())
            self._refresh_roles()
            self._refresh_categories()

    def _delete_role(self) -> None:
        item = self.roles_list.currentItem()
        if not item:
            return
        rid = item.data(Qt.ItemDataRole.UserRole)
        # Block delete if categories reference this role
        if any(c.role_id == rid for c in self.repo.list_categories()):
            QMessageBox.warning(self, "Nicht möglich", "Rolle wird noch von Kategorien verwendet.")
            return
        if QMessageBox.question(self, "Löschen?", f"Rolle '{item.text()}' löschen?") == QMessageBox.StandardButton.Yes:
            self.repo.delete_role(rid)
            self._refresh_roles()

    def _add_category(self) -> None:
        roles = self.repo.list_roles()
        if not roles:
            QMessageBox.warning(self, "Keine Rollen", "Bitte zuerst eine Rolle anlegen.")
            return
        dlg = _CategoryDialog(self, roles=roles)
        if dlg.exec():
            data = dlg.values()
            try:
                self.repo.create_category(**data)
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))
            self._refresh_categories()

    def _edit_category(self) -> None:
        row = self.cat_table.currentRow()
        if row < 0:
            return
        cid = self.cat_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        cat = self.repo.get_category(cid)
        if not cat:
            return
        roles = self.repo.list_roles()
        dlg = _CategoryDialog(self, roles=roles, initial=cat)
        if dlg.exec():
            data = dlg.values()
            self.repo.update_category(cid, **data)
            self._refresh_categories()

    def _delete_category(self) -> None:
        row = self.cat_table.currentRow()
        if row < 0:
            return
        cid = self.cat_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "Löschen?", "Kategorie löschen?") == QMessageBox.StandardButton.Yes:
            try:
                self.repo.delete_category(cid)
            except Exception as e:
                QMessageBox.warning(self, "Fehler", f"Kategorie ist in Zeiteinträgen referenziert: {e}")
            self._refresh_categories()

    # --- General ---

    def _build_general_tab(self) -> QWidget:
        w = QWidget(self)
        form = QFormLayout(w)

        self.rounding_combo = QComboBox()
        for v in [0, 5, 10, 15]:
            label = "Aus" if v == 0 else f"{v} Min"
            self.rounding_combo.addItem(label, v)
        current = int(self.repo.get_setting("rounding_minutes", "0") or "0")
        idx = self.rounding_combo.findData(current)
        if idx >= 0:
            self.rounding_combo.setCurrentIndex(idx)
        self.rounding_combo.currentIndexChanged.connect(self._save_rounding)
        form.addRow("Rundung:", self.rounding_combo)

        info = QLabel("Hotkeys, Autostart, Backup und Outlook-Integration kommen in den nächsten Phasen.")
        info.setStyleSheet("color: #888;")
        info.setWordWrap(True)
        form.addRow(info)

        return w

    def _save_rounding(self) -> None:
        val = self.rounding_combo.currentData()
        self.repo.set_setting("rounding_minutes", str(val))


class _CategoryDialog(QDialog):
    def __init__(self, parent, roles, initial=None):
        super().__init__(parent)
        self.setWindowTitle("Kategorie")
        self.roles = roles

        layout = QFormLayout(self)
        self.name = QLineEdit(initial.name if initial else "")
        layout.addRow("Name:", self.name)

        self.role_combo = QComboBox()
        for r in roles:
            self.role_combo.addItem(r.name, r.id)
        if initial:
            idx = self.role_combo.findData(initial.role_id)
            if idx >= 0:
                self.role_combo.setCurrentIndex(idx)
        layout.addRow("Rolle:", self.role_combo)

        color_box = QHBoxLayout()
        self.color = initial.color if initial else "#3388cc"
        self.color_btn = QPushButton()
        self.color_btn.setStyleSheet(f"background: {self.color};")
        self.color_btn.clicked.connect(self._pick_color)
        color_box.addWidget(self.color_btn)
        layout.addRow("Farbe:", color_box)

        self.active = QCheckBox()
        self.active.setChecked(initial.active if initial else True)
        layout.addRow("Aktiv:", self.active)

        self.outlook_name = QLineEdit(initial.outlook_category_name if initial and initial.outlook_category_name else "")
        layout.addRow("Outlook-Name:", self.outlook_name)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(QColor(self.color), self)
        if c.isValid():
            self.color = c.name()
            self.color_btn.setStyleSheet(f"background: {self.color};")

    def values(self) -> dict:
        return {
            "name": self.name.text().strip(),
            "color": self.color,
            "role_id": self.role_combo.currentData(),
            "active": self.active.isChecked(),
            "outlook_category_name": self.outlook_name.text().strip() or None,
        }
