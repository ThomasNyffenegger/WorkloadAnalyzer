"""Reports window: date-range picker, entry table (edit/delete), donut chart, CSV/XLSX export."""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QDateTime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDateEdit, QTabWidget, QWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox, QComboBox, QSizePolicy,
)

from workload_analyzer.db.repository import Repository
from workload_analyzer.core.rounding import round_seconds
from workload_analyzer.services.export import export_csv, export_xlsx


class ReportsWindow(QDialog):
    """Modal-less reports dialog. Shows table of entries + donut chart."""

    def __init__(self, repo: Repository, parent=None):
        super().__init__(parent)
        self._repo = repo
        self.setWindowTitle("Berichte")
        self.resize(900, 600)
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # --- Toolbar row ---
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Von:"))
        self._from_edit = QDateEdit()
        self._from_edit.setCalendarPopup(True)
        self._from_edit.setDate(
            QDateTime.currentDateTime().addDays(-7).date()
        )
        toolbar.addWidget(self._from_edit)

        toolbar.addWidget(QLabel("Bis:"))
        self._to_edit = QDateEdit()
        self._to_edit.setCalendarPopup(True)
        self._to_edit.setDate(QDateTime.currentDateTime().date())
        toolbar.addWidget(self._to_edit)

        refresh_btn = QPushButton("Aktualisieren")
        refresh_btn.clicked.connect(self._refresh)
        toolbar.addWidget(refresh_btn)

        toolbar.addStretch()

        export_csv_btn = QPushButton("Export CSV")
        export_csv_btn.clicked.connect(self._export_csv)
        toolbar.addWidget(export_csv_btn)

        export_xlsx_btn = QPushButton("Export XLSX")
        export_xlsx_btn.clicked.connect(self._export_xlsx)
        toolbar.addWidget(export_xlsx_btn)

        layout.addLayout(toolbar)

        # --- Tabs ---
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # Tab 1: Table
        table_widget = QWidget()
        table_layout = QVBoxLayout(table_widget)
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ["Start", "Ende", "Dauer (min)", "Rolle", "Kategorie", "Quelle", "Kommentar"]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table_layout.addWidget(self._table)

        row_btns = QHBoxLayout()
        edit_btn = QPushButton("Eintrag bearbeiten")
        edit_btn.clicked.connect(self._edit_selected)
        row_btns.addWidget(edit_btn)
        delete_btn = QPushButton("Eintrag löschen")
        delete_btn.clicked.connect(self._delete_selected)
        row_btns.addWidget(delete_btn)
        row_btns.addStretch()
        table_layout.addLayout(row_btns)

        self._tabs.addTab(table_widget, "Tabelle")

        # Tab 2: Chart
        chart_widget = QWidget()
        chart_layout = QVBoxLayout(chart_widget)

        chart_ctrl = QHBoxLayout()
        chart_ctrl.addWidget(QLabel("Gruppieren nach:"))
        self._group_combo = QComboBox()
        self._group_combo.addItems(["Rolle", "Kategorie"])
        self._group_combo.currentIndexChanged.connect(self._refresh_chart)
        chart_ctrl.addWidget(self._group_combo)
        chart_ctrl.addStretch()
        chart_layout.addLayout(chart_ctrl)

        self._chart_placeholder = QLabel("Keine Daten")
        self._chart_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chart_layout.addWidget(self._chart_placeholder)

        self._canvas = None  # lazy-init matplotlib canvas

        self._tabs.addTab(chart_widget, "Diagramm")

        self._chart_layout = chart_layout  # keep reference for canvas insertion

    def _range_ts(self) -> tuple[int, int]:
        """Return (from_ts, to_ts) in UTC unix seconds for the selected date range."""
        from_date = self._from_edit.date().toPyDate()
        to_date = self._to_edit.date().toPyDate()
        # from: start of day local; to: end of day local (exclusive → next day midnight)
        from_dt = datetime.datetime.combine(from_date, datetime.time.min).astimezone(datetime.timezone.utc)
        to_dt = datetime.datetime.combine(
            to_date + datetime.timedelta(days=1), datetime.time.min
        ).astimezone(datetime.timezone.utc)
        return int(from_dt.timestamp()), int(to_dt.timestamp())

    def _refresh(self) -> None:
        self._refresh_table()
        self._refresh_chart()

    def _refresh_table(self) -> None:
        from_ts, to_ts = self._range_ts()
        entries = self._repo.list_entries_between(from_ts, to_ts)
        cats = {c.id: c for c in self._repo.list_categories()}
        roles = {r.id: r for r in self._repo.list_roles()}

        rounding = int(self._repo.get_setting("rounding_minutes", "0") or "0")

        self._table.setRowCount(0)
        self._entry_ids: list[int] = []

        for entry in entries:
            if entry.end_ts is None:
                continue  # skip open entry
            cat = cats.get(entry.category_id)
            role_name = roles[cat.role_id].name if cat else "?"
            cat_name = cat.name if cat else "?"

            dur_sec = round_seconds(entry.duration_seconds(), rounding)
            dur_min = round(dur_sec / 60, 1)

            def _ts_str(ts: int) -> str:
                return datetime.datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")

            row = self._table.rowCount()
            self._table.insertRow(row)
            self._entry_ids.append(entry.id)

            self._table.setItem(row, 0, QTableWidgetItem(_ts_str(entry.start_ts)))
            self._table.setItem(row, 1, QTableWidgetItem(_ts_str(entry.end_ts)))
            self._table.setItem(row, 2, QTableWidgetItem(str(dur_min)))
            self._table.setItem(row, 3, QTableWidgetItem(role_name))
            self._table.setItem(row, 4, QTableWidgetItem(cat_name))
            self._table.setItem(row, 5, QTableWidgetItem(entry.source.value))
            self._table.setItem(row, 6, QTableWidgetItem(entry.comment or ""))

    def _refresh_chart(self) -> None:
        try:
            import matplotlib
            matplotlib.use("QtAgg")
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
        except ImportError:
            self._chart_placeholder.setText("matplotlib nicht verfügbar")
            return

        from_ts, to_ts = self._range_ts()
        entries = self._repo.list_entries_between(from_ts, to_ts)
        cats = {c.id: c for c in self._repo.list_categories()}
        roles = {r.id: r for r in self._repo.list_roles()}
        rounding = int(self._repo.get_setting("rounding_minutes", "0") or "0")

        group_by_role = self._group_combo.currentIndex() == 0

        totals: dict[str, float] = {}
        for entry in entries:
            if entry.end_ts is None:
                continue
            cat = cats.get(entry.category_id)
            if cat is None:
                continue
            label = roles[cat.role_id].name if group_by_role else cat.name
            dur_min = round_seconds(entry.duration_seconds(), rounding) / 60
            totals[label] = totals.get(label, 0) + dur_min

        if not totals:
            self._chart_placeholder.setText("Keine Daten im Zeitraum")
            if self._canvas is not None:
                self._canvas.setVisible(False)
            self._chart_placeholder.setVisible(True)
            return

        # Build or reuse canvas
        if self._canvas is None:
            fig = Figure(figsize=(5, 5), tight_layout=True)
            self._canvas = FigureCanvasQTAgg(fig)
            self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self._chart_layout.addWidget(self._canvas)

        self._chart_placeholder.setVisible(False)
        self._canvas.setVisible(True)

        fig = self._canvas.figure
        fig.clear()
        ax = fig.add_subplot(111)

        labels = list(totals.keys())
        sizes = [totals[l] for l in labels]
        wedge_props = {"width": 0.5}  # donut
        ax.pie(sizes, labels=labels, autopct="%1.1f%%", wedgeprops=wedge_props)
        ax.set_title("Zeitverteilung (Minuten)")
        self._canvas.draw()

    def _edit_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Hinweis", "Bitte einen Eintrag auswählen.")
            return
        entry_id = self._entry_ids[row]
        entries = self._repo.list_entries_between(0, 2**63 - 1)
        entry = next((e for e in entries if e.id == entry_id), None)
        if entry is None:
            return
        dlg = _EntryEditDialog(self._repo, entry, self)
        if dlg.exec():
            self._refresh()

    def _delete_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Hinweis", "Bitte einen Eintrag auswählen.")
            return
        entry_id = self._entry_ids[row]
        reply = QMessageBox.question(
            self, "Löschen bestätigen", "Eintrag wirklich löschen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._repo.delete_entry(entry_id)
            self._refresh()

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "CSV speichern", "", "CSV-Dateien (*.csv)"
        )
        if not path:
            return
        from_ts, to_ts = self._range_ts()
        rounding = int(self._repo.get_setting("rounding_minutes", "0") or "0")
        export_csv(self._repo, from_ts, to_ts, Path(path), rounding_minutes=rounding)
        QMessageBox.information(self, "Export", f"CSV gespeichert:\n{path}")

    def _export_xlsx(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "XLSX speichern", "", "Excel-Dateien (*.xlsx)"
        )
        if not path:
            return
        from_ts, to_ts = self._range_ts()
        rounding = int(self._repo.get_setting("rounding_minutes", "0") or "0")
        export_xlsx(self._repo, from_ts, to_ts, rounding, Path(path))
        QMessageBox.information(self, "Export", f"Excel gespeichert:\n{path}")


class _EntryEditDialog(QDialog):
    """Edit start/end timestamps, category and comment of an existing time entry."""

    def __init__(self, repo: Repository, entry, parent=None):
        super().__init__(parent)
        self._repo = repo
        self._entry = entry
        self.setWindowTitle("Eintrag bearbeiten")
        self._build_ui()

    def _build_ui(self) -> None:
        from PyQt6.QtWidgets import QFormLayout, QDialogButtonBox, QLineEdit
        from PyQt6.QtCore import QDateTime as QDT

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._start_edit = _DateTimeEdit(self._entry.start_ts)
        form.addRow("Start:", self._start_edit)

        self._end_edit = _DateTimeEdit(self._entry.end_ts or self._entry.start_ts + 60)
        form.addRow("Ende:", self._end_edit)

        self._cat_combo = QComboBox()
        cats = self._repo.list_categories()
        for cat in cats:
            self._cat_combo.addItem(cat.name, userData=cat.id)
            if cat.id == self._entry.category_id:
                self._cat_combo.setCurrentIndex(self._cat_combo.count() - 1)
        form.addRow("Kategorie:", self._cat_combo)

        self._comment_edit = QLineEdit(self._entry.comment or "")
        form.addRow("Kommentar:", self._comment_edit)

        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _save(self) -> None:
        start_ts = self._start_edit.timestamp()
        end_ts = self._end_edit.timestamp()
        if end_ts <= start_ts:
            QMessageBox.warning(self, "Fehler", "Ende muss nach Start liegen.")
            return
        cat_id = self._cat_combo.currentData()
        comment = self._comment_edit.text().strip() or None
        try:
            self._repo.update_entry(self._entry.id, cat_id, start_ts, end_ts, comment)
        except Exception as exc:
            QMessageBox.critical(self, "Fehler", str(exc))
            return
        self.accept()


class _DateTimeEdit(QWidget):
    """A combined date+time widget returning a unix timestamp."""

    def __init__(self, ts: int, parent=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QDateTimeEdit as _QDTEdit
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._dte = _QDTEdit()
        self._dte.setCalendarPopup(True)
        self._dte.setDisplayFormat("dd.MM.yyyy HH:mm")
        dt = datetime.datetime.fromtimestamp(ts)
        from PyQt6.QtCore import QDateTime, QDate, QTime
        self._dte.setDateTime(
            QDateTime(
                QDate(dt.year, dt.month, dt.day),
                QTime(dt.hour, dt.minute, dt.second),
            )
        )
        layout.addWidget(self._dte)

    def timestamp(self) -> int:
        qdt = self._dte.dateTime()
        py_dt = datetime.datetime(
            qdt.date().year(), qdt.date().month(), qdt.date().day(),
            qdt.time().hour(), qdt.time().minute(), qdt.time().second(),
        )
        return int(py_dt.astimezone(datetime.timezone.utc).timestamp())
