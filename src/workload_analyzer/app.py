import logging
import sys
import time
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QInputDialog

from workload_analyzer.core.tracker import TimeTracker, TrackerState
from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import OverlapError, Repository
from workload_analyzer.models import EntrySource
from workload_analyzer.paths import db_path
from workload_analyzer.services.outlook_monitor import OutlookMonitor
from workload_analyzer.ui.tray import TrayIcon


def run() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # keep tray running

    conn = connect(db_path())
    repo = Repository(conn)
    _backup_path = repo.get_setting("backup_path", "")
    if _backup_path:
        try:
            from workload_analyzer.services.backup import backup
            backup(db_path(), Path(_backup_path))
        except Exception as exc:
            logging.getLogger(__name__).warning("Startup backup failed: %s", exc)
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

    from workload_analyzer.services.hotkey_manager import GlobalHotkeyManager
    hotkeys = GlobalHotkeyManager()
    for i in range(1, 10):
        hotkeys.register(i)

    def _on_hotkey(n: int) -> None:
        cats = repo.list_categories(active_only=True)
        if n <= len(cats):
            tracker.switch_to(cats[n - 1].id, EntrySource.MANUAL)
            tray.refresh()

    hotkeys.triggered.connect(_on_hotkey)

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
            return  # No mapping — suppress
        if cat.id == tracker.current_state().category_id:
            return  # Already on this category — suppress
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
    # System Monitor (screen lock + idle)
    # ------------------------------------------------------------------
    from workload_analyzer.services.system_monitor import SystemMonitor
    from workload_analyzer.ui.recovery_popup import (
        RecoveryPopup, RECOVERY_PREVIOUS, RECOVERY_OTHER, RECOVERY_DISCARD,
    )

    idle_threshold_minutes = int(
        repo.get_setting("idle_threshold_minutes", "10") or "10"
    )
    sys_monitor = SystemMonitor(idle_threshold_seconds=idle_threshold_minutes * 60)

    # Absence state shared between on_absence_started and on_return handlers
    _absence = [None]  # Optional[(absence_start_ts: int, prev_cat_id: Optional[int])]

    def _on_absence_started(absence_start_ts: int) -> None:
        prev_cat_id = tracker.stop_at(absence_start_ts)
        _absence[0] = (absence_start_ts, prev_cat_id)

    def _show_recovery(absence_end_ts: int, reason: str, source: EntrySource) -> None:
        info = _absence[0]
        if info is None:
            return
        _absence[0] = None
        absence_start_ts, prev_cat_id = info
        absent_seconds = absence_end_ts - absence_start_ts

        active_cats = repo.list_categories(active_only=True)
        prev_cat = next((c for c in active_cats if c.id == prev_cat_id), None)

        popup = RecoveryPopup(absent_seconds, reason, prev_cat, active_cats)
        result = popup.exec()

        if result == RECOVERY_PREVIOUS and prev_cat_id is not None:
            try:
                repo.insert_closed_entry(prev_cat_id, absence_start_ts, absence_end_ts, source)
            except OverlapError:
                pass  # overlap guard — entry for this time range already exists
            tracker.start(prev_cat_id, EntrySource.MANUAL)

        elif result == RECOVERY_OTHER:
            chosen_id = popup.selected_category_id()
            if chosen_id is not None:
                try:
                    repo.insert_closed_entry(chosen_id, absence_start_ts, absence_end_ts, source)
                except OverlapError:
                    pass
                tracker.start(chosen_id, EntrySource.MANUAL)
            elif prev_cat_id is not None:
                # Empty category list edge case — fall back to previous category
                tracker.start(prev_cat_id, EntrySource.MANUAL)

        else:  # RECOVERY_DISCARD (or no previous category)
            if prev_cat_id is not None:
                tracker.start(prev_cat_id, EntrySource.MANUAL)

        tray.refresh()

    def _on_session_locked(lock_ts: int) -> None:
        _on_absence_started(lock_ts)

    def _on_session_unlocked(lock_ts: int, unlock_ts: int) -> None:
        _show_recovery(unlock_ts, "Bildschirm gesperrt", EntrySource.SCREEN_LOCK_RECOVERY)

    def _on_idle_started(idle_start_ts: int) -> None:
        _on_absence_started(idle_start_ts)

    def _on_user_returned(idle_start_ts: int, return_ts: int) -> None:
        _show_recovery(return_ts, "Inaktivität", EntrySource.IDLE_RECOVERY)

    sys_monitor.session_locked.connect(_on_session_locked)
    sys_monitor.session_unlocked.connect(_on_session_unlocked)
    sys_monitor.idle_started.connect(_on_idle_started)
    sys_monitor.user_returned.connect(_on_user_returned)
    sys_monitor.start()

    # ------------------------------------------------------------------
    # Settings / Reports / Widget
    # ------------------------------------------------------------------
    def open_settings():
        from workload_analyzer.ui.settings_window import SettingsWindow
        win = SettingsWindow(repo, monitor=monitor, system_monitor=sys_monitor)
        win.exec()
        tray.refresh()

    def open_reports():
        from workload_analyzer.ui.reports_window import ReportsWindow
        ReportsWindow(repo).exec()

    floating_widget = None

    def toggle_widget():
        nonlocal floating_widget
        from workload_analyzer.ui.floating_widget import FloatingWidget
        if floating_widget is None:
            floating_widget = FloatingWidget(repo=repo, tracker=tracker)
            floating_widget.widget_hidden.connect(
                lambda: tray.set_widget_visible(False)
            )
            floating_widget.show()
            tray.set_widget_visible(True)
        elif floating_widget.isVisible():
            floating_widget.hide()
            tray.set_widget_visible(False)
        else:
            floating_widget.show()
            tray.set_widget_visible(True)

    tray.open_settings.connect(open_settings)
    tray.open_reports.connect(open_reports)
    tray.toggle_widget.connect(toggle_widget)

    def _quit():
        hotkeys.unregister_all()
        sys_monitor.stop()
        monitor.stop()
        app.quit()

    tray.quit_requested.connect(_quit)

    return app.exec()
