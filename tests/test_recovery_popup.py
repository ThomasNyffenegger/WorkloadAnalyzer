"""Tests for RecoveryPopup dialog."""
import pytest
from workload_analyzer.models import Category
from workload_analyzer.ui.recovery_popup import (
    RecoveryPopup, RECOVERY_PREVIOUS, RECOVERY_OTHER, RECOVERY_DISCARD,
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
    # No "Vorherige" radio — discard should be pre-selected
    assert popup._radio_prev is None


def test_recovery_previous_returns_correct_code(qtbot):
    popup = RecoveryPopup(
        absent_seconds=600,
        reason="Bildschirm gesperrt",
        previous_category=make_prev_cat(),
        all_categories=make_cats(),
    )
    qtbot.addWidget(popup)
    popup._radio_prev.setChecked(True)
    popup._on_confirm()
    assert popup.result() == RECOVERY_PREVIOUS


def test_recovery_discard_returns_correct_code(qtbot):
    popup = RecoveryPopup(
        absent_seconds=600,
        reason="Bildschirm gesperrt",
        previous_category=make_prev_cat(),
        all_categories=make_cats(),
    )
    qtbot.addWidget(popup)
    popup._radio_discard.setChecked(True)
    popup._on_confirm()
    assert popup.result() == RECOVERY_DISCARD


def test_recovery_other_returns_correct_code(qtbot):
    popup = RecoveryPopup(
        absent_seconds=600,
        reason="Bildschirm gesperrt",
        previous_category=make_prev_cat(),
        all_categories=make_cats(),
    )
    qtbot.addWidget(popup)
    popup._radio_other.setChecked(True)
    popup._on_confirm()
    assert popup.result() == RECOVERY_OTHER


def test_selected_category_id_returns_combo_value(qtbot):
    cats = make_cats()
    popup = RecoveryPopup(
        absent_seconds=600,
        reason="Bildschirm gesperrt",
        previous_category=make_prev_cat(),
        all_categories=cats,
    )
    qtbot.addWidget(popup)
    popup._other_combo.setCurrentIndex(1)  # select "Meetings" (id=11)
    assert popup.selected_category_id() == 11


def test_long_absence_preselects_discard(qtbot):
    popup = RecoveryPopup(
        absent_seconds=9 * 3600,  # 9 hours
        reason="Bildschirm gesperrt",
        previous_category=make_prev_cat(),
        all_categories=make_cats(),
    )
    qtbot.addWidget(popup)
    assert popup._radio_discard.isChecked()


def test_no_previous_category_preselects_discard(qtbot):
    popup = RecoveryPopup(
        absent_seconds=300,
        reason="Inaktivität",
        previous_category=None,
        all_categories=make_cats(),
    )
    qtbot.addWidget(popup)
    assert popup._radio_discard.isChecked()
