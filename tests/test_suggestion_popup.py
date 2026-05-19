"""Tests for SuggestionPopup auto-close countdown."""
import pytest
from PyQt6.QtCore import QTimer
from workload_analyzer.ui.suggestion_popup import (
    SuggestionPopup, SUGGESTION_YES, SUGGESTION_NO,
)


def test_yes_button_shows_countdown(qtbot):
    popup = SuggestionPopup("Meetings", "Besprechungen")
    qtbot.addWidget(popup)
    popup.show()
    # Initially shows countdown start value
    assert "10" in popup._yes_btn.text()


def test_auto_close_accepts_after_timeout(qtbot):
    popup = SuggestionPopup("Meetings", "Besprechungen")
    qtbot.addWidget(popup)
    results = []

    def on_finished(code):
        results.append(code)

    popup.finished.connect(on_finished)
    popup.show()

    # Fast-forward: set countdown to 1 and trigger one tick
    popup._countdown = 1
    popup._tick()

    assert results == [SUGGESTION_YES]


def test_countdown_decrements(qtbot):
    popup = SuggestionPopup("Meetings", "Besprechungen")
    qtbot.addWidget(popup)
    popup.show()
    popup._tick()
    assert popup._countdown == 9
    assert "9" in popup._yes_btn.text()


def test_timer_stops_on_manual_close(qtbot):
    popup = SuggestionPopup("Meetings", "Besprechungen")
    qtbot.addWidget(popup)
    popup.show()
    assert popup._auto_timer.isActive()
    popup.done(SUGGESTION_YES)
    assert not popup._auto_timer.isActive()


def test_done_called_twice_does_not_crash(qtbot):
    popup = SuggestionPopup("Meetings", "Besprechungen")
    qtbot.addWidget(popup)
    popup.show()
    popup.done(SUGGESTION_YES)
    popup.done(SUGGESTION_NO)  # must not raise or crash
