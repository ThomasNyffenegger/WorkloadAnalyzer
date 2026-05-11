import os
from pathlib import Path

from workload_analyzer.paths import data_dir, db_path


def test_data_dir_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    result = data_dir()
    assert result == tmp_path / "WorkloadAnalyzer"
    assert result.exists()


def test_db_path_inside_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert db_path() == tmp_path / "WorkloadAnalyzer" / "workload.db"
