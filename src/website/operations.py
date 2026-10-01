"""Local operations without paid services: private, consistent database backups."""
import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import tempfile
import zipfile


def backup(store, destination=None):
    directory = store.path.parent / 'backups'
    directory.mkdir(mode=0o700, exist_ok=True)
    destination = Path(destination) if destination else directory / ('seatwatch-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f') + '.zip')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Reserve exclusively; never overwrite an operator's existing backup.
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        with tempfile.TemporaryDirectory(prefix='seatwatch-backup-') as temp:
            copy = Path(temp) / 'tickets.sqlite3'
            with store.connect() as source, sqlite3.connect(copy) as target:
                source.backup(target)
                assert target.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.write(copy, 'tickets.sqlite3')
                # Account recovery and booking reconciliation need these private files.
                for folder in ('provider-sessions', 'tickets'):
                    root = store.path.parent / folder
                    if root.is_dir():
                        for path in root.iterdir():
                            if path.is_file() and not path.is_symlink() and path.suffix != '.tmp':
                                archive.write(path, folder + '/' + path.name)
        store.heartbeat('backup', 'ok')
        return destination
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


async def backup_loop(store, config):
    while True:
        try:
            await asyncio.to_thread(backup, store)
            files = sorted((store.path.parent / 'backups').glob('seatwatch-*.zip'))
            for old in files[:-config.website_backup_keep]:
                old.unlink()
        except Exception:
            store.heartbeat('backup', 'failed')
        await asyncio.sleep(config.website_backup_hours * 3600)
