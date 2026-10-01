"""Local-only operations. Run python -m src.website.manage --help."""
import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import zipfile

from src.website.config import web_settings
from src.website.store import Store
from src.website.operations import backup


def restore(archive, destination):
    """Restore into a new directory only; leave the current installation untouched."""
    if destination.exists():
        raise ValueError('Restore destination must be a new directory.')
    with zipfile.ZipFile(archive) as source, tempfile.TemporaryDirectory(prefix='seatwatch-restore-') as temporary:
        root = Path(temporary)
        if sum(info.file_size for info in source.infolist()) > 512 * 1024 * 1024:
            raise ValueError('Backup is too large')
        for info in source.infolist():
            parts = Path(info.filename).parts
            if info.is_dir() or info.filename.startswith('/') or '..' in parts:
                raise ValueError('Invalid backup entry')
            if not (parts == ('tickets.sqlite3',) or (len(parts) == 2 and parts[0] in {'tickets','provider-sessions'})):
                raise ValueError('Unexpected backup entry')
            target = root / info.filename
            target.parent.mkdir(mode=0o700, exist_ok=True)
            target.write_bytes(source.read(info))
            target.chmod(0o600)
        if not (root / 'tickets.sqlite3').is_file():
            raise ValueError('Backup database missing')
        with sqlite3.connect(root / 'tickets.sqlite3') as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup database failed integrity check')
        destination.mkdir(mode=0o700, parents=True)
        shutil.copytree(root, destination, dirs_exist_ok=True)
    # Restored providers are never assumed to have an active browser or unpaid ticket.
    Store(destination / 'tickets.sqlite3').recover()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status', help='Counts and worker heartbeats; no passenger data')
    b = sub.add_parser('backup', help='Private online database/ticket/session backup')
    b.add_argument('--output', type=Path)
    r = sub.add_parser('restore', help='Restore a backup into a NEW data directory')
    r.add_argument('archive', type=Path)
    r.add_argument('destination', type=Path)
    sub.add_parser('doctor', help='Check local runtime and missing external configuration')
    args = parser.parse_args()
    if args.command == 'restore':
        restore(args.archive, args.destination)
        print('Restored. Stop the server and set WEBSITE_DATABASE to', args.destination / 'tickets.sqlite3')
        return
    store = Store(web_settings.website_database)
    if args.command == 'status':
        print(json.dumps(store.metrics(), indent=2))
    elif args.command == 'backup':
        print(backup(store, args.output))
    else:
        chrome = web_settings.browser_executable or shutil.which('google-chrome') or shutil.which('chromium')
        if not chrome and Path('/opt/google/chrome/chrome').exists():
            chrome = '/opt/google/chrome/chrome'
        print(json.dumps({'database':'ok','browser':bool(chrome),'booking_mode':web_settings.booking_mode,
                          'whatsapp_configured':web_settings.whatsapp_ready,
                          'public_https':web_settings.website_public_url.startswith('https://'),
                          'secure_cookies':web_settings.website_secure_cookies,
                          'browser_limit':web_settings.website_browser_limit,
                          'live_booking_validation':'Requires a real Shohoz account and user-completed payment'}, indent=2))


if __name__ == '__main__':
    main()
