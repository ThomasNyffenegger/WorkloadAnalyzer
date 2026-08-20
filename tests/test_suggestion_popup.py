"""Tests for SuggestionPopup: toast-style auto-close countdown and placement."""
import pytest
from workload_analyzer.ui.suggestion_popup import (
    SuggestionPopup, SUGGESTION_YES, SUGGESTION_NO, SUGGESTION_ALWAYS,
)


def test_progress_bar_starts_full(qtbot):
    popup = SuggestionPopup("Meetings", "Besprechungen")
    qtbot.addWidget(popup)
    popup.show()
    assert popup._progress_bar.value() == popup._progress_bar.maximum()


def test_auto_close_accepts_after_timeout(qtbot):
    popup = SuggestionPopup("Meetings", "Besprechungen")
    qtbot.addWidget(popup)
    results = []

    def on_finished(code):
        results.append(code)

    popup.finished.connect(on_finished)
    popup.show()

    # Fast-forward: one tick left before the bar empties
    popup._remaining_ms = 100
    popup._tick()

    assert results == [SUGGESTION_YES]


def test_progress_bar_shrinks_on_tick(qtbot):
    popup = SuggestionPopup("Meetings", "Besprechungen")
    qtbot.addWidget(popup)
    popup.show()
    before = popup._progress_bar.value()
    popup._tick()
    assert popup._progress_bar.value() == before - 100


def test_timer_stops_on_manual_close(qtbot):
    popup = SuggestionPopup("Meetings", "Besprechungen")
    qtbot.addWidget(popup)
    popup.show()
    assert popup._auto_timer.isActive()
    popup.done(SUGGESTION_YES)
    assert not popup._auto_timer.isActive()


def test_always_button_returns_always_code(qtbot):
    popup = SuggestionPopup("Meetings", "Besprechungen")
    qtbot.addWidget(popup)
    results = []
    popup.finished.connect(results.append)
    popup.show()
    popup.done(SUGGESTION_ALWAYS)
    assert results == [SUGGESTION_ALWAYS]


def test_done_called_twice_does_not_crash(qtbot):
    popup = SuggestionPopup("Meetings", "Besprechungen")
    qtbot.addWidget(popup)
    popup.show()
    popup.done(SUGGESTION_YES)
    popup.done(SUGGESTION_NO)  # must not raise or crash


def test_popup_anchors_to_bottom_right_of_screen(qtbot):
    popup = SuggestionPopup("Meetings", "Besprechungen")
    qtbot.addWidget(popup)
    popup.show()

    screen = popup.screen()
    geo = screen.availableGeometry()
    frame = popup.frameGeometry()

    assert frame.right() <= geo.right()
    assert frame.bottom() <= geo.bottom()
    # Anchored to the corner (small margin), not centered or top-left default.
    assert geo.right() - frame.right() < 50
    assert geo.bottom() - frame.bottom() < 50
