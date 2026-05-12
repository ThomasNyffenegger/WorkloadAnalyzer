import pytest

from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository
from workload_analyzer.models import Role


@pytest.fixture
def repo(tmp_db_path):
    conn = connect(tmp_db_path)
    yield Repository(conn)
    conn.close()


def test_create_role_returns_id(repo: Repository):
    role_id = repo.create_role("Entwicklung")
    assert isinstance(role_id, int)
    assert role_id > 0


def test_list_roles_returns_all(repo: Repository):
    repo.create_role("Entwicklung")
    repo.create_role("Projektleitung")
    roles = repo.list_roles()
    assert len(roles) == 2
    names = [r.name for r in roles]
    assert "Entwicklung" in names
    assert "Projektleitung" in names


def test_create_role_duplicate_name_raises(repo: Repository):
    repo.create_role("Entwicklung")
    with pytest.raises(Exception):
        repo.create_role("Entwicklung")


def test_rename_role(repo: Repository):
    rid = repo.create_role("Dev")
    repo.rename_role(rid, "Entwicklung")
    assert repo.get_role(rid).name == "Entwicklung"


def test_delete_role(repo: Repository):
    rid = repo.create_role("Tmp")
    repo.delete_role(rid)
    assert repo.get_role(rid) is None
