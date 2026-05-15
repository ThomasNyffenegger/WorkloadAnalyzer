import shutil
from datetime import datetime
from pathlib import Path


def backup(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"workload_{ts}.db"
    shutil.copy2(db_path, dest)
    return dest
