from pathlib import Path
from workload_analyzer.services.backup import backup


def test_backup_creates_timestamped_file(tmp_path: Path):
    db = tmp_path / "workload.db"
    db.write_bytes(b"test database content")
    backup_dir = tmp_path / "backups"

    result = backup(db, backup_dir)

    assert result.exists()
    assert result.parent == backup_dir
    assert result.name.startswith("workload_")
    assert result.suffix == ".db"
    assert result.read_bytes() == b"test database content"


def test_backup_creates_directory_if_missing(tmp_path: Path):
    db = tmp_path / "workload.db"
    db.write_bytes(b"data")
    backup_dir = tmp_path / "a" / "b" / "c"

    backup(db, backup_dir)

    assert backup_dir.exists()


def test_backup_filename_contains_timestamp(tmp_path: Path):
    db = tmp_path / "workload.db"
    db.write_bytes(b"x")
    backup_dir = tmp_path / "backups"

    result = backup(db, backup_dir)

    # Format: workload_YYYYMMDD_HHMMSS.db — 8+1+6 chars between underscores
    parts = result.stem.split("_")   # ["workload", "20260514", "123456"]
    assert len(parts) == 3
    assert parts[0] == "workload"
    assert len(parts[1]) == 8   # YYYYMMDD
    assert len(parts[2]) == 6   # HHMMSS


def test_backup_returns_path_to_new_file(tmp_path: Path):
    db = tmp_path / "workload.db"
    db.write_bytes(b"data")

    result = backup(db, tmp_path / "backups")

    assert isinstance(result, Path)
    assert result.exists()
