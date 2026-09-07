"""Tests for RecoveryPopup dialog."""
import pytest
from workload_analyzer.models import Category
from workload_analyzer.ui.recovery_popup import (
    RecoveryPopup, RECOVERY_BOOK, RECOVERY_DISCARD,
)


def make_cats():
    return [
        Category(id=10, name="Projektarbeit", color="#ff0000", role_id=1),
        Category(id=11, name="Meetings", color="#00ff00", role_id=1),
    ]


def make_prev_cat():
    return Category(id=10, name="Projektarbeit", color="#ff0000", role_id=1)


def test_popup_constructs_with_previous_category(qtbot):
    popup = RecoveryPopup(
        absent_seconds=600,
        reason="Bildschirm gesperrt",
        previous_category=make_prev_cat(),
        all_categories=make_cats(),
    )
    qtbot.addWidget(popup)
    assert popup is not None


def test_popup_constructs_without_previous_category(qtbot):
    popup = RecoveryPopup(
        absent_seconds=600,
        reason="Inaktivität",
        previous_category=None,
        all_categories=make_cats(),
    )
    qtbot.addWidget(popup)
    assert popup is not None


def test_previous_category_preselected_in_combo(qtbot):
    popup = RecoveryPopup(
        absent_seconds=600,
        reason="Bildschirm gesperrt",
        previous_category=make_cats()[1],  # "Meetings", id=11
        all_categories=make_cats(),
    )
    qtbot.addWidget(popup)
    assert popup.selected_category_id() == 11


def test_no_previous_category_defaults_to_first_entry(qtbot):
    popup = RecoveryPopup(
        absent_seconds=600,
        reason="Inaktivität",
        previous_category=None,
        all_categories=make_cats(),
    )
    qtbot.addWidget(popup)
    assert popup.selected_category_id() == 10  # first category in the list


def test_book_button_returns_correct_code(qtbot):
    popup = RecoveryPopup(
        absent_seconds=600,
        reason="Bildschirm gesperrt",
        previous_category=make_prev_cat(),
        all_categories=make_cats(),
    )
    qtbot.addWidget(popup)
    popup.done(RECOVERY_BOOK)
    assert popup.result() == RECOVERY_BOOK


def test_discard_button_returns_correct_code(qtbot):
    popup = RecoveryPopup(
        absent_seconds=600,
        reason="Bildschirm gesperrt",
        previous_category=make_prev_cat(),
        all_categories=make_cats(),
    )
    qtbot.addWidget(popup)
    popup.done(RECOVERY_DISCARD)
    assert popup.result() == RECOVERY_DISCARD


def test_selected_category_id_returns_combo_value(qtbot):
    cats = make_cats()
    popup = RecoveryPopup(
        absent_seconds=600,
        reason="Bildschirm gesperrt",
        previous_category=make_prev_cat(),
        all_categories=cats,
    )
    qtbot.addWidget(popup)
    popup._category_combo.setCurrentIndex(1)  # select "Meetings" (id=11)
    assert popup.selected_category_id() == 11
