from workload_analyzer.paths import data_dir, db_path


def test_data_dir_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    result = data_dir()
    assert result == tmp_path / "WorkloadAnalyzer"
    assert result.exists()


def test_db_path_inside_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert db_path() == tmp_path / "WorkloadAnalyzer" / "workload.db"


def test_data_dir_fallback_without_appdata(monkeypatch, tmp_path):
    monkeypatch.delenv("APPDATA", raising=False)
    from pathlib import Path
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    result = data_dir()
    assert result == tmp_path / "home" / "WorkloadAnalyzer"
    assert result.exists()
