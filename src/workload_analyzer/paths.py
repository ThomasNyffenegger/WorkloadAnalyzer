import os
from pathlib import Path

APP_DIR_NAME = "WorkloadAnalyzer"
DB_FILE_NAME = "workload.db"


def data_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home()
    d = base / APP_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return data_dir() / DB_FILE_NAME
