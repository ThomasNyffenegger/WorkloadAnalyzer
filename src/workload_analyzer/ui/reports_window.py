"""Reports window: date-range picker, entry table (edit/delete), donut chart, CSV/XLSX export."""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QDate, QDateTime
from PyQt6.QtWidgets import (
    QButtonGroup, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDateEdit, QTabWidget, QWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox, QComboBox, QSizePolicy,
)

from workload_analyzer.db.repository import Repository
from workload_analyzer.core.rounding import round_seconds
from workload_analyzer.services.export import export_csv, export_xlsx, export_xlsx_pivot


def _py_date_to_qdate(d: datetime.date) -> QDate:
    """Convert a Python date to QDate."""
    return QDate(d.year, d.month, d.day)


def _bucket_key(dt: datetime.datetime, granularity: str) -> tuple:
    """Group key for the bar chart's time axis — same key = same bar."""
    if granularity == "Tag":
        return (dt.year, dt.month, dt.day)
    if granularity == "Woche":
        iso_year, iso_week, _ = dt.isocalendar()
        return (iso_year, iso_week)
    return (dt.year, dt.month)


def _bucket_label(key: tuple, granularity: str) -> str:
    if granularity == "Tag":
        year, month, day = key
        return f"{day:02d}.{month:02d}."
    if granularity == "Woche":
        _, week = key
        return f"KW{week:02d}"
    year, month = key
    return f"{month:02d}.{year}"


def _format_duration(total_minutes: float) -> str:
    total = round(total_minutes)
    hours, minutes = divmod(total, 60)
    return f"{hours}h {minutes:02d}min" if hours else f"{minutes}min"


class ReportsWindow(QDialog):
    """Modal-less reports dialog. Shows table of entries + donut chart."""

    def __init__(self, repo: Repository, parent=None):
        super().__init__(parent)
        self._repo = repo
        self.setWindowTitle("Berichte")
        self.resize(900, 750)
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # --- Tabs ---
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # Tab 1: Table (date filter + export toolbar live here — they only
        # affect what's exported/listed, so they don't clutter the chart tab)
        table_widget = QWidget()
        table_layout = QVBoxLayout(table_widget)

        toolbar = QHBoxLayout()

        # Schnellauswahl buttons
        for label, slot in [
            ("Heute",        self._select_today),
            ("Diese Woche",  self._select_this_week),
            ("Diesen Monat", self._select_this_month),
            ("Letzten Monat",self._select_last_month),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            toolbar.addWidget(btn)

        toolbar.addSpacing(12)
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

        export_pivot_btn = QPushButton("Export Pivot XLSX")
        export_pivot_btn.clicked.connect(self._export_xlsx_pivot)
        toolbar.addWidget(export_pivot_btn)

        table_layout.addLayout(toolbar)

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
        chart_ctrl.addWidget(QLabel("Diagrammtyp:"))
        self._chart_type_group, chart_type_row, chart_type_btns = self._make_segmented_toggle(
            ["Kreis", "Balken"], checked_index=1  # Balken by default
        )
        self._chart_type_kreis_btn, self._chart_type_balken_btn = chart_type_btns
        self._chart_type_group.idToggled.connect(self._on_chart_type_toggled)
        chart_ctrl.addLayout(chart_type_row)

        chart_ctrl.addWidget(QLabel("Gruppieren nach:"))
        self._group_combo = QComboBox()
        self._group_combo.addItems(["Rolle", "Kategorie"])
        self._group_combo.setEnabled(False)  # only relevant for "Kreis"
        self._group_combo.currentIndexChanged.connect(self._refresh_chart)
        chart_ctrl.addWidget(self._group_combo)

        chart_ctrl.addWidget(QLabel("Zeitraster:"))
        self._granularity_group, granularity_row, granularity_btns = self._make_segmented_toggle(
            ["Tag", "Woche", "Monat"], checked_index=0  # Tag by default
        )
        self._granularity_group.idToggled.connect(
            lambda _id, checked: self._refresh_chart() if checked else None
        )
        chart_ctrl.addLayout(granularity_row)

        chart_ctrl.addStretch()
        chart_layout.addLayout(chart_ctrl)

        self._total_label = QLabel()
        chart_layout.addWidget(self._total_label)

        self._chart_placeholder = QLabel("Keine Daten")
        self._chart_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chart_layout.addWidget(self._chart_placeholder)

        self._canvas = None  # lazy-init matplotlib canvas

        self._tabs.addTab(chart_widget, "Diagramm")
        self._tabs.setCurrentIndex(1)  # Diagramm (Balken) is the default view on open

        self._chart_layout = chart_layout  # keep reference for canvas insertion

    def _make_segmented_toggle(self, labels: list[str], checked_index: int):
        """Build a row of mutually-exclusive toggle buttons styled as one
        segmented control — used instead of a QComboBox for short option
        lists (Diagrammtyp, Zeitraster) so the current choice is visible
        without opening a dropdown."""
        group = QButtonGroup(self)
        group.setExclusive(True)
        row = QHBoxLayout()
        row.setSpacing(0)
        row.setContentsMargins(0, 0, 0, 0)
        buttons = []
        for i, text in enumerate(labels):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setChecked(i == checked_index)
            if i == 0:
                shape = "border-top-right-radius: 0; border-bottom-right-radius: 0; border-right: none;"
            elif i == len(labels) - 1:
                shape = "border-top-left-radius: 0; border-bottom-left-radius: 0;"
            else:
                shape = "border-radius: 0; border-right: none;"
            btn.setStyleSheet(
                f"QPushButton {{ border: 1px solid #999999; {shape}"
                " padding: 4px 12px; background: #f0f0f0; }"
                "QPushButton:checked { background: #3d7dca; color: white; border-color: #3d7dca; }"
            )
            group.addButton(btn, i)
            row.addWidget(btn)
            buttons.append(btn)
        return group, row, buttons

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

    def _on_chart_type_toggled(self, button_id: int, checked: bool) -> None:
        if not checked:
            return  # idToggled fires for both the old and the newly-checked button
        is_bar = button_id == 1
        self._group_combo.setEnabled(not is_bar)
        for btn in self._granularity_group.buttons():
            btn.setEnabled(is_bar)
        self._refresh_chart()

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
        entries = [
            e for e in self._repo.list_entries_between(from_ts, to_ts)
            if e.end_ts is not None
        ]
        cats = {c.id: c for c in self._repo.list_categories()}
        roles = {r.id: r for r in self._repo.list_roles()}
        rounding = int(self._repo.get_setting("rounding_minutes", "0") or "0")

        usable = [e for e in entries if cats.get(e.category_id) is not None]
        total_minutes = sum(
            round_seconds(e.duration_seconds(), rounding) / 60 for e in usable
        )
        self._total_label.setText(f"Gesamt: {_format_duration(total_minutes)}")

        if not usable:
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

        if self._chart_type_kreis_btn.isChecked():
            self._draw_pie(ax, usable, cats, roles, rounding)
        else:
            self._draw_bars(ax, usable, cats, rounding)

        self._canvas.draw()

    def _draw_pie(self, ax, entries, cats, roles, rounding) -> None:
        group_by_role = self._group_combo.currentIndex() == 0

        totals: dict[str, float] = {}
        for entry in entries:
            cat = cats[entry.category_id]
            label = roles[cat.role_id].name if group_by_role else cat.name
            dur_min = round_seconds(entry.duration_seconds(), rounding) / 60
            totals[label] = totals.get(label, 0) + dur_min

        labels = list(totals.keys())
        sizes = [totals[l] for l in labels]
        wedge_props = {"width": 0.5}  # donut
        ax.pie(sizes, labels=labels, autopct="%1.1f%%", wedgeprops=wedge_props)
        ax.set_title("Zeitverteilung (Minuten)")

    def _draw_bars(self, ax, entries, cats, rounding) -> None:
        granularity = self._granularity_group.checkedButton().text()

        per_bucket: dict[tuple, dict[int, float]] = {}
        for entry in entries:
            dt = datetime.datetime.fromtimestamp(entry.start_ts)
            key = _bucket_key(dt, granularity)
            dur_min = round_seconds(entry.duration_seconds(), rounding) / 60
            bucket = per_bucket.setdefault(key, {})
            bucket[entry.category_id] = bucket.get(entry.category_id, 0) + dur_min

        bucket_keys = sorted(per_bucket.keys())
        cat_ids = sorted(
            {cid for bucket in per_bucket.values() for cid in bucket},
            key=lambda cid: cats[cid].name,
        )
        if not cat_ids:
            return

        totals_by_cat = {
            cid: sum(per_bucket[k].get(cid, 0) for k in bucket_keys) for cid in cat_ids
        }
        grand_total = sum(totals_by_cat.values()) or 1

        bar_count = len(cat_ids)
        width = 0.8 / bar_count
        for i, cid in enumerate(cat_ids):
            cat = cats[cid]
            pct = totals_by_cat[cid] / grand_total * 100
            values = [per_bucket[k].get(cid, 0) for k in bucket_keys]
            offset = (i - (bar_count - 1) / 2) * width
            positions = [x + offset for x in range(len(bucket_keys))]
            ax.bar(positions, values, width=width, color=cat.color)
            for x_pos, value in zip(positions, values):
                # Category name below every bar (rotated), anchored to the
                # axis line rather than the bar's own height so the top
                # letter lines up across bars regardless of value.
                ax.text(
                    x_pos, -0.02, cat.name, transform=ax.get_xaxis_transform(),
                    rotation=90, ha="center", va="top", fontsize=9, clip_on=False,
                )
                # Category's overall share of the grand total, on top of
                # each bar — skip zero-height bars, nothing to label there.
                if value > 0:
                    ax.text(
                        x_pos, value, f"{pct:.0f}%",
                        ha="center", va="bottom", fontsize=7,
                    )

        ax.set_xticks(range(len(bucket_keys)))
        ax.set_xticklabels([_bucket_label(k, granularity) for k in bucket_keys])

        # The rotated category names need room proportional to the longest
        # one — a fixed pad overlapped the period label (KW29 etc.) once
        # there were enough categories with long names.
        max_name_len = max(len(cats[cid].name) for cid in cat_ids)
        label_pad = min(150, 20 + max_name_len * 6.5)
        ax.tick_params(axis="x", pad=label_pad)
        fig_height_pt = ax.figure.get_size_inches()[1] * 72
        ax.figure.subplots_adjust(bottom=min(0.6, (label_pad + 35) / fig_height_pt))

        ax.set_ylabel("Minuten")
        ax.set_ylim(top=ax.get_ylim()[1] * 1.15)  # headroom for the % labels above bars

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

    # ------------------------------------------------------------------
    # Schnellauswahl helpers
    # ------------------------------------------------------------------

    def _select_today(self) -> None:
        today = _py_date_to_qdate(datetime.date.today())
        self._from_edit.setDate(today)
        self._to_edit.setDate(today)
        self._refresh()

    def _select_this_week(self) -> None:
        today = datetime.date.today()
        monday = today - datetime.timedelta(days=today.weekday())  # weekday() 0 = Monday
        self._from_edit.setDate(_py_date_to_qdate(monday))
        self._to_edit.setDate(_py_date_to_qdate(today))
        self._refresh()

    def _select_this_month(self) -> None:
        today = datetime.date.today()
        first = today.replace(day=1)
        self._from_edit.setDate(_py_date_to_qdate(first))
        self._to_edit.setDate(_py_date_to_qdate(today))
        self._refresh()

    def _select_last_month(self) -> None:
        today = datetime.date.today()
        last_day_prev = today.replace(day=1) - datetime.timedelta(days=1)
        first_day_prev = last_day_prev.replace(day=1)
        self._from_edit.setDate(_py_date_to_qdate(first_day_prev))
        self._to_edit.setDate(_py_date_to_qdate(last_day_prev))
        self._refresh()

    def _export_xlsx_pivot(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Pivot XLSX speichern", "", "Excel-Dateien (*.xlsx)"
        )
        if not path:
            return
        from_ts, to_ts = self._range_ts()
        rounding = int(self._repo.get_setting("rounding_minutes", "0") or "0")
        export_xlsx_pivot(self._repo, from_ts, to_ts, rounding, Path(path))
        QMessageBox.information(self, "Export", f"Pivot XLSX gespeichert:\n{path}")


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
