import os
from pathlib import Path

APP_DIR_NAME = "WorkloadAnalyzer"
DB_FILE_NAME = "workload.db"


def data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if not base:
        base = str(Path.home())
    d = Path(base) / APP_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return data_dir() / DB_FILE_NAME
