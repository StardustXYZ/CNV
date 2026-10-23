"""Database backups taken before each sync."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3

from sqlalchemy.engine import make_url

BACKUP_PREFIX = "cnv-"


def sqlite_path(database_url: str) -> Path | None:
    """File path of a SQLite database URL, or None for other databases / in-memory."""
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return Path(url.database)


def backup_database(database_url: str, backups_dir: Path, label: str, keep: int) -> Path | None:
    """Copy the SQLite database into ``backups_dir`` and keep only the newest ``keep`` copies.

    Uses SQLite's online backup, safe while the app has the database open. Returns the
    new file, or None when there is nothing to back up. Only files made here
    (``cnv-*.db``) are ever deleted.
    """
    source = sqlite_path(database_url)
    if source is None or not source.exists():
        return None
    backups_dir.mkdir(parents=True, exist_ok=True)
    target = backups_dir / f"{BACKUP_PREFIX}{datetime.now():%Y%m%d-%H%M%S}-{label}.db"

    src = sqlite3.connect(source)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    for old in list_backups(backups_dir)[keep:]:
        old.unlink(missing_ok=True)
    return target


def list_backups(backups_dir: Path) -> list[Path]:
    """Backups made by CNV, newest first."""
    if not backups_dir.exists():
        return []
    return sorted(backups_dir.glob(f"{BACKUP_PREFIX}*.db"), key=lambda p: p.name, reverse=True)
