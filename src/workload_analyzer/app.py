import sys
import time

from PyQt6.QtWidgets import QApplication, QInputDialog

from workload_analyzer.core.tracker import TimeTracker, TrackerState
from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import EntrySource
from workload_analyzer.paths import db_path
from workload_analyzer.services.outlook_monitor import OutlookMonitor
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

    # ------------------------------------------------------------------
    # Outlook Monitor
    # ------------------------------------------------------------------
    poll_seconds = int(repo.get_setting("outlook_poll_seconds", "15") or "15")
    monitor = OutlookMonitor()
    _active_popup = [None]  # list to allow mutation in nested closures

    def _on_category_detected(outlook_name: str) -> None:
        from workload_analyzer.ui.suggestion_popup import (
            SuggestionPopup, SUGGESTION_YES, SUGGESTION_NO, SUGGESTION_NEVER,
        )
        cat = repo.find_category_by_outlook_name(outlook_name)
        if cat is None:
            return
        if repo.is_silenced(outlook_name, cat.id):
            return
        # Close any previously open popup (treated as rejection)
        if _active_popup[0] is not None and _active_popup[0].isVisible():
            _active_popup[0].done(SUGGESTION_NO)
        popup = SuggestionPopup(outlook_name, cat.name)
        _active_popup[0] = popup
        result = popup.exec()
        if result == SUGGESTION_YES:
            tracker.switch_to(cat.id, EntrySource.AUTO_OUTLOOK)
        elif result == SUGGESTION_NO:
            repo.record_rejection(outlook_name, cat.id)
        elif result == SUGGESTION_NEVER:
            repo.record_rejection(outlook_name, cat.id, immediate_silence=True)

    def _on_meeting_started(title: str, outlook_category) -> None:
        from workload_analyzer.ui.suggestion_popup import MeetingCategoryDialog
        active_cats = repo.list_categories(active_only=True)
        if outlook_category:
            cat = repo.find_category_by_outlook_name(outlook_category)
            if cat:
                tracker.switch_to(cat.id, EntrySource.AUTO_MEETING)
                return
        # No mapped category — ask user
        dlg = MeetingCategoryDialog(title, active_cats)
        if dlg.exec():
            cat_id = dlg.selected_category_id()
            if cat_id is not None:
                tracker.switch_to(cat_id, EntrySource.AUTO_MEETING)

    def _on_meeting_ended() -> None:
        pass  # Lock release — tracker continues on current category

    monitor.category_detected.connect(_on_category_detected)
    monitor.meeting_started.connect(_on_meeting_started)
    monitor.meeting_ended.connect(_on_meeting_ended)
    monitor.availability_changed.connect(tray.set_outlook_available)
    monitor.start(poll_seconds)

    # ------------------------------------------------------------------
    # Settings / Reports / Widget
    # ------------------------------------------------------------------
    def open_settings():
        from workload_analyzer.ui.settings_window import SettingsWindow
        win = SettingsWindow(repo, monitor=monitor)
        win.exec()
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

    def _quit():
        monitor.stop()
        app.quit()

    tray.quit_requested.connect(_quit)

    return app.exec()
