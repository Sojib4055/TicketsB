"""Bounded resources, encrypted session checkpoints and a single-worker lease."""
import fcntl
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken

from src.website.domain import NeedsAttention, ProviderBusy


class BrowserBudget:
    def __init__(self, limit):
        self.limit, self.used = limit, 0

    def acquire(self):
        # Runs on the application's event loop; no await between check and increment.
        if self.used >= self.limit:
            raise ProviderBusy('All provider sessions are busy. Your request will wait for capacity.')
        self.used += 1

    def release(self):
        self.used = max(0, self.used - 1)


class WorkerLease:
    def __init__(self, database):
        self.path = database.with_suffix(database.suffix + '.worker.lock')
        self.handle = None

    def acquire(self):
        self.handle = self.path.open('a+')
        self.path.chmod(0o600)
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.handle.close()
            self.handle = None
            raise RuntimeError('Another SeatWatch worker is using this database. Stop it before starting a second server.')

    def close(self):
        if self.handle:
            fcntl.flock(self.handle, fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None


class SessionVault:
    """Only provider storage state and allowlisted URLs; never screenshot/input fields."""
    def __init__(self, database):
        self.directory = database.parent / 'provider-sessions'
        self.directory.mkdir(mode=0o700, exist_ok=True)
        self.directory.chmod(0o700)
        key_path = self.directory / 'key'
        try:
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'wb') as out:
                out.write(Fernet.generate_key())
        self.fernet = Fernet(key_path.read_bytes())

    def path(self, jid):
        if not re.fullmatch(r'[a-f0-9]{32}', jid):
            raise ValueError('Invalid session identifier')
        return self.directory / (jid + '.enc')

    @staticmethod
    def allowed_url(url):
        try:
            parsed = urlparse(url)
            return (parsed.scheme == 'https' and parsed.hostname == 'www.shohoz.com'
                    and parsed.port in (None, 443) and not parsed.username
                    and parsed.path.startswith('/bus-tickets/booking/bus/')
                    and any(part in parsed.path for part in ('/search', '/pay', '/confirmed', '/trip-info')))
        except ValueError:
            return False

    def save(self, jid, state):
        if not self.allowed_url(state.get('url', '')):
            raise ValueError('Provider page cannot be checkpointed')
        data = json.dumps({'saved_at': time.time(), **state}).encode()
        if len(data) > 2 * 1024 * 1024:
            raise ValueError('Provider session is too large')
        path = self.path(jid)
        temporary = path.with_suffix('.tmp')
        with temporary.open('wb') as out:
            os.chmod(temporary, 0o600)
            out.write(self.fernet.encrypt(data))
        temporary.replace(path)

    def load(self, jid):
        path = self.path(jid)
        if not path.is_file():
            return None
        try:
            value = json.loads(self.fernet.decrypt(path.read_bytes()))
            if time.time() - value['saved_at'] > 86400 or not self.allowed_url(value['url']):
                self.delete(jid)
                return None
            return value
        except (InvalidToken, ValueError, KeyError):
            raise NeedsAttention('The saved provider session cannot be recovered. Check the booking directly with Shohoz.')

    def delete(self, jid):
        self.path(jid).unlink(missing_ok=True)
