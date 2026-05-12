import sys
import time

from PyQt6.QtWidgets import QApplication, QInputDialog

from workload_analyzer.core.tracker import TimeTracker, TrackerState
from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource
from workload_analyzer.paths import db_path
from workload_analyzer.ui.tray import TrayIcon


def run() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # keep tray running

    conn = connect(db_path())
    repo = Repository(conn)
    tracker = TimeTracker(repo=repo, clock=lambda: int(time.time()))
    tracker.load_state()

    # First-run: if there are no categories, force settings.
    if not repo.list_categories(active_only=True):
        from workload_analyzer.ui.settings_window import SettingsWindow
        win = SettingsWindow(repo)
        win.exec()

    # If still no categories, exit politely.
    cats = repo.list_categories(active_only=True)
    if not cats:
        return 0

    # If not currently tracking, ask which category to start with.
    if tracker.current_state().kind != TrackerState.Kind.TRACKING:
        names = [c.name for c in cats]
        choice, ok = QInputDialog.getItem(None, "Womit beginnst du?", "Kategorie:", names, 0, False)
        if ok:
            cat = next(c for c in cats if c.name == choice)
            tracker.start(category_id=cat.id, source=EntrySource.MANUAL)

    tray = TrayIcon(repo=repo, tracker=tracker)

    # Wire windows on demand.
    def open_settings():
        from workload_analyzer.ui.settings_window import SettingsWindow
        SettingsWindow(repo).exec()
        tray.refresh()

    def open_reports():
        from workload_analyzer.ui.reports_window import ReportsWindow
        ReportsWindow(repo).exec()

    floating_widget = None

    def toggle_widget():
        nonlocal floating_widget
        from workload_analyzer.ui.floating_widget import FloatingWidget
        if floating_widget is None or not floating_widget.isVisible():
            floating_widget = FloatingWidget(repo=repo, tracker=tracker)
            floating_widget.show()
        else:
            floating_widget.hide()

    tray.open_settings.connect(open_settings)
    tray.open_reports.connect(open_reports)
    tray.toggle_widget.connect(toggle_widget)
    tray.quit_requested.connect(app.quit)

    return app.exec()
