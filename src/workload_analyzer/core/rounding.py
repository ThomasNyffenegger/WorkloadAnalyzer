def round_seconds(seconds: int, step_minutes: int) -> int:
    """Round a duration in seconds to the nearest step_minutes boundary.

    step_minutes == 0 disables rounding. Ties round up.
    """
    if seconds < 0:
        raise ValueError("seconds must be non-negative")
    if step_minutes == 0:
        return seconds
    step = step_minutes * 60
    # Add half a step so that ties round up consistently.
    return ((seconds + step // 2) // step) * step
