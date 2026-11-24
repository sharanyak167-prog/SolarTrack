import sqlite3
import zipfile
from app import backup, db


def test_backup_uses_configured_sqlite_and_external_upload_dir(tmp_path, monkeypatch):
    db_path = tmp_path / 'custom.sqlite'
    db.init_db(f'sqlite:///{db_path}')
    uploads = tmp_path / 'external_uploads'
    uploads.mkdir()
    (uploads / 'bill.pdf').write_bytes(b'test')
    monkeypatch.setenv('UPLOAD_DIR', str(uploads))
    monkeypatch.setattr(backup, 'BACKUP_DIR', tmp_path / 'backups')
    archive = backup.create_backup()
    with zipfile.ZipFile(archive) as z:
        assert z.read('uploads/bill.pdf') == b'test'
        snapshot = tmp_path / 'restored.sqlite'
        snapshot.write_bytes(z.read('database.sqlite'))
    with sqlite3.connect(snapshot) as conn:
        assert conn.execute("select count(*) from sqlite_master where name='bills'").fetchone()[0] == 1
