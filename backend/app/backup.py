"""Consistent SQLite and upload backups. MySQL requires an external dump."""
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import tempfile
import zipfile
from fastapi import HTTPException
from . import config, db

BACKUP_DIR = config.ROOT / 'backups'


def create_backup() -> Path:
    url = db.engine.url
    if url.get_backend_name() != 'sqlite' or not url.database or url.database == ':memory:':
        raise HTTPException(501, 'Automatic backups support file-based SQLite only; use mysqldump for MySQL.')
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / f"solartrack_backup_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / 'database.sqlite'
        with sqlite3.connect(url.database) as source, sqlite3.connect(str(snapshot)) as dest:
            source.backup(dest)
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(snapshot, 'database.sqlite')
            uploads = config.upload_dir()
            if uploads.exists():
                for file in uploads.rglob('*'):
                    if file.is_file() and not file.is_symlink():
                        z.write(file, (Path('uploads') / file.relative_to(uploads)).as_posix())
            z.writestr('manifest.json', json.dumps({'created_at': datetime.now().isoformat(), 'database_type': 'sqlite', 'database': 'database.sqlite'}))
    return target


def list_backups() -> list[dict]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return [{'filename': f.name, 'path': str(f), 'size_bytes': f.stat().st_size, 'created_at': datetime.fromtimestamp(f.stat().st_mtime).isoformat()} for f in sorted(BACKUP_DIR.glob('*.zip'), reverse=True)]
