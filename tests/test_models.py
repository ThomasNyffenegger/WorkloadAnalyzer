from workload_analyzer.models import Role, Category, TimeEntry, EntrySource


def test_entry_source_values():
    assert EntrySource.MANUAL.value == "manual"
    assert EntrySource.AUTO_OUTLOOK.value == "auto_outlook"
    assert EntrySource.AUTO_MEETING.value == "auto_meeting"
    assert EntrySource.MANUAL_OVERRIDE.value == "manual_override"
    assert EntrySource.SCREEN_LOCK_RECOVERY.value == "screen_lock_recovery"
    assert EntrySource.IDLE_RECOVERY.value == "idle_recovery"


def test_role_dataclass():
    r = Role(id=1, name="Entwicklung")
    assert r.id == 1
    assert r.name == "Entwicklung"


def test_category_dataclass():
    c = Category(id=2, name="Frontend", color="#ff0000", role_id=1, active=True)
    assert c.color == "#ff0000"
    assert c.active is True
    assert c.outlook_category_name is None


def test_time_entry_active_when_end_ts_none():
    e = TimeEntry(
        id=10, category_id=2, start_ts=1000, end_ts=None,
        source=EntrySource.MANUAL, comment=None,
    )
    assert e.is_active() is True


def test_time_entry_duration_seconds():
    e = TimeEntry(
        id=10, category_id=2, start_ts=1000, end_ts=1300,
        source=EntrySource.MANUAL, comment=None,
    )
    assert e.duration_seconds() == 300
