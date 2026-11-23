"""Backup management for SolarTrack.

Creates and restores timestamped archives of the database and uploaded bill files.
"""
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import zipfile

from . import config

BACKUP_DIR = config.ROOT / "backups"


def create_backup() -> Path:
    """Create a zip archive containing database and uploaded files."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"solartrack_backup_{ts}.zip"

    manifest = {
        "created_at": datetime.now().isoformat(),
        "database_type": "sqlite" if config.database_url().startswith("sqlite") else "mysql",
        "files_included": [],
    }

    with zipfile.ZipFile(backup_file, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Database (SQLite)
        if config.database_url().startswith("sqlite"):
            db_path = config.ROOT / "dev.db"
            if db_path.exists():
                zf.write(db_path, arcname="dev.db")
                manifest["files_included"].append("dev.db")

        # 2. Uploaded Bills
        upload_folder = config.upload_dir()
        if upload_folder.exists():
            for f in upload_folder.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(config.ROOT)
                    zf.write(f, arcname=str(rel).replace("\\", "/"))
                    manifest["files_included"].append(str(rel).replace("\\", "/"))

        # 3. Manifest
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    return backup_file


def list_backups() -> list[dict]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backups = []
    for f in sorted(BACKUP_DIR.glob("*.zip"), reverse=True):
        stat = f.stat()
        backups.append({
            "filename": f.name,
            "path": str(f),
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return backups
