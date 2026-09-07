from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from workload_analyzer.db.repository import Repository


class SettingsWindow(QDialog):
    def __init__(self, repo: Repository, monitor=None, system_monitor=None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.repo = repo
        self._monitor = monitor           # Optional[OutlookMonitor]
        self._system_monitor = system_monitor  # Optional[SystemMonitor]
        self.setWindowTitle("WorkloadAnalyzer — Einstellungen")
        self.resize(720, 520)

        tabs = QTabWidget(self)
        tabs.addTab(self._build_categories_tab(), "Rollen & Kategorien")
        tabs.addTab(self._build_general_tab(), "Allgemein")
        tabs.addTab(self._build_outlook_tab(), "Outlook")

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
        self.cat_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cat_table.setSortingEnabled(True)
        cats_box.addWidget(self.cat_table)

        ch = QHBoxLayout()
        add_cat = QPushButton("Hinzufügen")
        add_cat.clicked.connect(self._add_category)
        edit_cat = QPushButton("Bearbeiten")
        edit_cat.clicked.connect(self._edit_category)
        del_cat = QPushButton("Löschen")
        del_cat.clicked.connect(self._delete_category)
        import_outlook = QPushButton("Aus Outlook importieren")
        import_outlook.clicked.connect(self._import_from_outlook)
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

        self._idle_spin = QSpinBox()
        self._idle_spin.setRange(5, 60)
        self._idle_spin.setSuffix(" Min")
        current_idle = int(self.repo.get_setting("idle_threshold_minutes", "10") or "10")
        self._idle_spin.setValue(current_idle)
        self._idle_spin.valueChanged.connect(self._save_idle_threshold)
        form.addRow("Idle-Schwellwert:", self._idle_spin)

        # Autostart
        from workload_analyzer.services import autostart as _autostart
        from workload_analyzer.paths import is_frozen
        self._autostart_checkbox = QCheckBox()
        if is_frozen():
            self._autostart_checkbox.setChecked(_autostart.is_enabled())
        else:
            self._autostart_checkbox.setEnabled(False)
            self._autostart_checkbox.setToolTip("Nur im installierten Paket verfügbar")
        self._autostart_checkbox.toggled.connect(self._save_autostart)
        form.addRow("Mit Windows starten:", self._autostart_checkbox)

        # Backup path
        backup_row = QHBoxLayout()
        self._backup_path_edit = QLineEdit()
        default_backup = str(Path.home() / "Documents" / "WorkloadAnalyzer" / "backups")
        self._backup_path_edit.setPlaceholderText(default_backup)
        self._backup_path_edit.setText(self.repo.get_setting("backup_path", ""))
        self._backup_path_edit.editingFinished.connect(self._save_backup_path)
        browse_btn = QPushButton("Durchsuchen…")
        browse_btn.clicked.connect(self._browse_backup_path)
        backup_row.addWidget(self._backup_path_edit)
        backup_row.addWidget(browse_btn)
        form.addRow("Backup-Pfad:", backup_row)

        return w

    def _save_rounding(self) -> None:
        val = self.rounding_combo.currentData()
        self.repo.set_setting("rounding_minutes", str(val))

    def _save_idle_threshold(self, value: int) -> None:
        self.repo.set_setting("idle_threshold_minutes", str(value))
        if self._system_monitor is not None:
            self._system_monitor.set_idle_threshold(value * 60)

    def _save_autostart(self, checked: bool) -> None:
        from workload_analyzer.paths import is_frozen, frozen_executable_path
        if not is_frozen():
            return
        from workload_analyzer.services import autostart as _autostart
        if checked:
            _autostart.enable(frozen_executable_path())
        else:
            _autostart.disable()

    def _save_backup_path(self) -> None:
        self.repo.set_setting("backup_path", self._backup_path_edit.text().strip())

    def _browse_backup_path(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Backup-Ordner wählen")
        if path:
            self._backup_path_edit.setText(path)
            self._save_backup_path()

    def _build_outlook_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        # Poll interval
        form = QFormLayout()
        self._poll_spin = QSpinBox()
        self._poll_spin.setRange(5, 60)
        self._poll_spin.setSuffix(" s")
        current_poll = int(self.repo.get_setting("outlook_poll_seconds", "15") or "15")
        self._poll_spin.setValue(current_poll)
        self._poll_spin.valueChanged.connect(self._save_poll_interval)
        form.addRow("Poll-Intervall:", self._poll_spin)
        layout.addLayout(form)

        layout.addWidget(QLabel("Outlook-Erkennungen:"))

        self._rejected_table = QTableWidget(0, 5)
        self._rejected_table.setHorizontalHeaderLabels(
            ["Outlook-Name", "App-Kategorie", "Status", "Ablehnungen", "Aktion"]
        )
        self._rejected_table.horizontalHeader().setStretchLastSection(True)
        self._rejected_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._rejected_table)

        self._refresh_rejected()
        return w

    def _save_poll_interval(self, value: int) -> None:
        self.repo.set_setting("outlook_poll_seconds", str(value))
        if self._monitor is not None:
            self._monitor.set_interval(value)

    def _refresh_rejected(self) -> None:
        suggestions = self.repo.list_rejected_suggestions()
        cats = {c.id: c.name for c in self.repo.list_categories()}
        self._rejected_table.setRowCount(0)
        self._suggestion_ids: list[int] = []
        for s in suggestions:
            row = self._rejected_table.rowCount()
            self._rejected_table.insertRow(row)
            self._suggestion_ids.append(s.id)
            self._rejected_table.setItem(row, 0, QTableWidgetItem(s.outlook_category_name))
            self._rejected_table.setItem(row, 1, QTableWidgetItem(cats.get(s.app_category_id, "?")))
            status = "Automatisch" if s.auto_accept else ("Stumm" if s.silenced else "Aktiv")
            self._rejected_table.setItem(row, 2, QTableWidgetItem(status))
            self._rejected_table.setItem(row, 3, QTableWidgetItem(str(s.rejection_count)))

            if s.auto_accept:
                action_btn = QPushButton("Automatik beenden")
                action_btn.clicked.connect(
                    lambda _checked=False, sid=s.id: self._clear_auto_accept(sid)
                )
            else:
                action_btn = QPushButton("Reaktivieren" if s.silenced else "Stumm schalten")
                action_btn.clicked.connect(
                    lambda _checked=False, sid=s.id, silenced=s.silenced: self._toggle_silenced(sid, silenced)
                )
            self._rejected_table.setCellWidget(row, 4, action_btn)

    def _toggle_silenced(self, suggestion_id: int, currently_silenced: bool) -> None:
        self.repo.set_silenced(suggestion_id, not currently_silenced)
        self._refresh_rejected()

    def _clear_auto_accept(self, suggestion_id: int) -> None:
        self.repo.set_auto_accept(suggestion_id, False)
        self._refresh_rejected()

    def _import_from_outlook(self) -> None:
        from workload_analyzer.ui.import_outlook_dialog import ImportOutlookDialog
        dlg = ImportOutlookDialog(self.repo, self)
        if dlg.exec():
            self._refresh_categories()


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
