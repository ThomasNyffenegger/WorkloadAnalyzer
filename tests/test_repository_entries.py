import pytest

from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository, OverlapError
from workload_analyzer.models import EntrySource


@pytest.fixture
def repo(tmp_db_path):
    conn = connect(tmp_db_path)
    r = Repository(conn)
    rid = r.create_role("Entwicklung")
    r.create_category(name="A", color="#0", role_id=rid)
    r.create_category(name="B", color="#0", role_id=rid)
    yield r
    conn.close()


def test_start_entry_returns_id(repo):
    cat = repo.list_categories()[0]
    eid = repo.start_entry(category_id=cat.id, start_ts=1000, source=EntrySource.MANUAL)
    assert eid > 0


def test_only_one_open_entry_allowed(repo):
    cat = repo.list_categories()[0]
    repo.start_entry(category_id=cat.id, start_ts=1000, source=EntrySource.MANUAL)
    with pytest.raises(OverlapError):
        repo.start_entry(category_id=cat.id, start_ts=2000, source=EntrySource.MANUAL)


def test_close_open_entry(repo):
    cat = repo.list_categories()[0]
    eid = repo.start_entry(category_id=cat.id, start_ts=1000, source=EntrySource.MANUAL)
    repo.close_entry(eid, end_ts=1500)
    open_entry = repo.get_open_entry()
    assert open_entry is None


def test_get_open_entry_returns_active(repo):
    cat = repo.list_categories()[0]
    eid = repo.start_entry(category_id=cat.id, start_ts=1000, source=EntrySource.MANUAL)
    open_entry = repo.get_open_entry()
    assert open_entry is not None
    assert open_entry.id == eid
    assert open_entry.is_active()


def test_insert_closed_entry_no_overlap_ok(repo):
    cat = repo.list_categories()[0]
    repo.insert_closed_entry(category_id=cat.id, start_ts=1000, end_ts=2000, source=EntrySource.MANUAL)
    repo.insert_closed_entry(category_id=cat.id, start_ts=2000, end_ts=3000, source=EntrySource.MANUAL)


def test_insert_overlapping_closed_entry_rejected(repo):
    cat = repo.list_categories()[0]
    repo.insert_closed_entry(category_id=cat.id, start_ts=1000, end_ts=2000, source=EntrySource.MANUAL)
    with pytest.raises(OverlapError):
        repo.insert_closed_entry(category_id=cat.id, start_ts=1500, end_ts=2500, source=EntrySource.MANUAL)


def test_update_entry_rejects_overlap(repo):
    cat = repo.list_categories()[0]
    repo.insert_closed_entry(category_id=cat.id, start_ts=1000, end_ts=2000, source=EntrySource.MANUAL)
    eid2 = repo.insert_closed_entry(category_id=cat.id, start_ts=3000, end_ts=4000, source=EntrySource.MANUAL)
    with pytest.raises(OverlapError):
        repo.update_entry(eid2, category_id=cat.id, start_ts=1500, end_ts=2500, comment=None)


def test_delete_entry(repo):
    cat = repo.list_categories()[0]
    eid = repo.insert_closed_entry(category_id=cat.id, start_ts=1000, end_ts=2000, source=EntrySource.MANUAL)
    repo.delete_entry(eid)
    assert repo.list_entries_between(0, 10000) == []


def test_list_entries_between(repo):
    cat = repo.list_categories()[0]
    repo.insert_closed_entry(category_id=cat.id, start_ts=1000, end_ts=2000, source=EntrySource.MANUAL)
    repo.insert_closed_entry(category_id=cat.id, start_ts=5000, end_ts=6000, source=EntrySource.MANUAL)
    rows = repo.list_entries_between(0, 3000)
    assert len(rows) == 1
