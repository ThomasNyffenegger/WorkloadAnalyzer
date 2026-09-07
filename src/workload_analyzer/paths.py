import os
from pathlib import Path

APP_DIR_NAME = "WorkloadAnalyzer"
DB_FILE_NAME = "workload.db"


def is_frozen() -> bool:
    """True when running as a packaged build (Nuitka or PyInstaller), not from source.

    PyInstaller sets sys.frozen; Nuitka doesn't — it injects a __compiled__
    global into every compiled module instead, so the module-globals check
    is required to detect a Nuitka build.
    """
    import sys
    return getattr(sys, "frozen", False) or "__compiled__" in globals()


def frozen_executable_path() -> str:
    """Path to the running packaged executable.

    sys.executable is unreliable for this: PyInstaller points it at the
    real frozen exe, but Nuitka points it at a synthetic, non-existent
    internal "python.exe" instead of the actual compiled program.
    sys.argv[0] is correct under both.
    """
    import sys
    return sys.argv[0]


def data_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home()
    d = base / APP_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return data_dir() / DB_FILE_NAME
