import sys

import workload_analyzer.paths as paths_module
from workload_analyzer.paths import data_dir, db_path, is_frozen, frozen_executable_path


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


def test_is_frozen_false_when_running_from_source():
    assert is_frozen() is False


def test_is_frozen_true_via_sys_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert is_frozen() is True


def test_is_frozen_true_via_nuitka_compiled_marker(monkeypatch):
    # Nuitka injects a __compiled__ global into every compiled module
    # instead of setting sys.frozen (unlike PyInstaller) — simulate that.
    monkeypatch.setattr(paths_module, "__compiled__", True, raising=False)
    assert is_frozen() is True


def test_frozen_executable_path_uses_argv0_not_executable(monkeypatch):
    # Regression guard: sys.executable points at a synthetic, non-existent
    # "python.exe" under Nuitka, not the real compiled program — must use
    # sys.argv[0] instead.
    monkeypatch.setattr(sys, "executable", "C:\\bogus\\python.exe")
    monkeypatch.setattr(sys, "argv", ["C:\\real\\WorkloadAnalyzer.exe"])
    assert frozen_executable_path() == "C:\\real\\WorkloadAnalyzer.exe"
