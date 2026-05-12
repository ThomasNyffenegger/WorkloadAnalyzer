import pytest

from workload_analyzer.db.connection import connect
from workload_analyzer.db.repository import Repository


@pytest.fixture
def repo(tmp_db_path):
    conn = connect(tmp_db_path)
    yield Repository(conn)
    conn.close()


def test_get_setting_default(repo):
    assert repo.get_setting("missing", default="x") == "x"


def test_set_and_get_setting(repo):
    repo.set_setting("rounding_minutes", "15")
    assert repo.get_setting("rounding_minutes") == "15"


def test_overwrite_setting(repo):
    repo.set_setting("k", "1")
    repo.set_setting("k", "2")
    assert repo.get_setting("k") == "2"
