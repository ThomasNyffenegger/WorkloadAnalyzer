import pytest
from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository


@pytest.fixture
def repo(tmp_db_path):
    return Repository(connect(tmp_db_path))


@pytest.fixture
def setup(repo):
    """Create a role + category for FK requirements."""
    role_id = repo.create_role("Dev")
    cat_id = repo.create_category("Coding", "#ff0000", role_id, outlook_category_name="coding")
    return {"role_id": role_id, "cat_id": cat_id}


def test_not_silenced_initially(repo, setup):
    assert repo.is_silenced("coding", setup["cat_id"]) is False


def test_record_rejection_increments_count(repo, setup):
    repo.record_rejection("coding", setup["cat_id"])
    repo.record_rejection("coding", setup["cat_id"])
    suggestions = repo.list_rejected_suggestions()
    assert len(suggestions) == 1
    assert suggestions[0].rejection_count == 2
    assert suggestions[0].silenced is False


def test_silenced_after_three_rejections(repo, setup):
    repo.record_rejection("coding", setup["cat_id"])
    repo.record_rejection("coding", setup["cat_id"])
    assert repo.is_silenced("coding", setup["cat_id"]) is False
    repo.record_rejection("coding", setup["cat_id"])
    assert repo.is_silenced("coding", setup["cat_id"]) is True


def test_immediate_silence(repo, setup):
    repo.record_rejection("coding", setup["cat_id"], immediate_silence=True)
    assert repo.is_silenced("coding", setup["cat_id"]) is True


def test_set_silenced_reactivates(repo, setup):
    repo.record_rejection("coding", setup["cat_id"], immediate_silence=True)
    s = repo.list_rejected_suggestions()[0]
    repo.set_silenced(s.id, False)
    assert repo.is_silenced("coding", setup["cat_id"]) is False


def test_list_rejected_suggestions_fields(repo, setup):
    repo.record_rejection("coding", setup["cat_id"])
    items = repo.list_rejected_suggestions()
    assert len(items) == 1
    s = items[0]
    assert s.outlook_category_name == "coding"
    assert s.app_category_id == setup["cat_id"]
    assert s.rejection_count == 1
    assert s.silenced is False
    assert s.auto_accept is False
    assert s.last_rejected_at is not None


def test_not_auto_accept_initially(repo, setup):
    assert repo.is_auto_accept("coding", setup["cat_id"]) is False


def test_mark_auto_accept(repo, setup):
    repo.mark_auto_accept("coding", setup["cat_id"])
    assert repo.is_auto_accept("coding", setup["cat_id"]) is True
    s = repo.list_rejected_suggestions()[0]
    assert s.auto_accept is True
    assert s.silenced is False


def test_mark_auto_accept_clears_silenced(repo, setup):
    """auto_accept and silenced are mutually exclusive outcomes of the same
    popup — marking auto-accept must undo a prior silence."""
    repo.record_rejection("coding", setup["cat_id"], immediate_silence=True)
    repo.mark_auto_accept("coding", setup["cat_id"])
    assert repo.is_silenced("coding", setup["cat_id"]) is False
    assert repo.is_auto_accept("coding", setup["cat_id"]) is True


def test_set_auto_accept_can_disable(repo, setup):
    repo.mark_auto_accept("coding", setup["cat_id"])
    s = repo.list_rejected_suggestions()[0]
    repo.set_auto_accept(s.id, False)
    assert repo.is_auto_accept("coding", setup["cat_id"]) is False
