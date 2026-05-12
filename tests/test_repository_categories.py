import pytest

from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository


@pytest.fixture
def repo(tmp_db_path):
    conn = connect(tmp_db_path)
    r = Repository(conn)
    r.create_role("Entwicklung")
    yield r
    conn.close()


def test_create_category(repo):
    role_id = repo.list_roles()[0].id
    cid = repo.create_category(name="Frontend", color="#ff0000", role_id=role_id)
    assert cid > 0


def test_list_categories_includes_role_name(repo):
    role_id = repo.list_roles()[0].id
    repo.create_category(name="Frontend", color="#ff0000", role_id=role_id)
    cats = repo.list_categories()
    assert len(cats) == 1
    assert cats[0].name == "Frontend"
    assert cats[0].role_id == role_id


def test_list_active_categories_excludes_inactive(repo):
    role_id = repo.list_roles()[0].id
    cid1 = repo.create_category(name="Active", color="#0", role_id=role_id)
    cid2 = repo.create_category(name="Inactive", color="#0", role_id=role_id)
    repo.set_category_active(cid2, False)
    active = repo.list_categories(active_only=True)
    assert [c.id for c in active] == [cid1]


def test_update_category(repo):
    role_id = repo.list_roles()[0].id
    cid = repo.create_category(name="Old", color="#000", role_id=role_id)
    repo.update_category(cid, name="New", color="#fff", role_id=role_id, active=True, outlook_category_name="OL")
    cats = repo.list_categories()
    assert cats[0].name == "New"
    assert cats[0].color == "#fff"
    assert cats[0].outlook_category_name == "OL"


def test_find_category_by_outlook_name(repo):
    role_id = repo.list_roles()[0].id
    cid = repo.create_category(name="Frontend", color="#0", role_id=role_id, outlook_category_name="Project A - FE")
    found = repo.find_category_by_outlook_name("Project A - FE")
    assert found is not None
    assert found.id == cid


def test_delete_category(repo):
    role_id = repo.list_roles()[0].id
    cid = repo.create_category(name="Tmp", color="#0", role_id=role_id)
    repo.delete_category(cid)
    assert repo.list_categories() == []
