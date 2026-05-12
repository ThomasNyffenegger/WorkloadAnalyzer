import pytest

from workload_analyzer.core.rounding import round_seconds


@pytest.mark.parametrize("seconds,step_min,expected", [
    (0, 5, 0),
    (60, 5, 0),       # 1 min rounds down with step 5
    (150, 5, 300),    # 2.5 min rounds up to 5
    (449, 5, 300),    # 7.5 min rounds down
    (450, 5, 600),    # exactly 7.5 rounds up
    (901, 15, 900),
    (899, 15, 900),
])
def test_round_seconds_nearest(seconds, step_min, expected):
    assert round_seconds(seconds, step_min) == expected


def test_round_seconds_step_zero_returns_input():
    assert round_seconds(123, 0) == 123


def test_round_seconds_negative_raises():
    with pytest.raises(ValueError):
        round_seconds(-1, 5)
