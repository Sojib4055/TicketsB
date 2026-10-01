import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                    password TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, mode TEXT NOT NULL,
                    status TEXT NOT NULL, request TEXT NOT NULL, data TEXT NOT NULL,
                    next_poll REAL NOT NULL, created REAL NOT NULL, updated REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS jobs_owner ON jobs(user_id);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    kind TEXT NOT NULL, message TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY, job_id TEXT NOT NULL, dedupe TEXT UNIQUE NOT NULL,
                    kind TEXT NOT NULL, body TEXT NOT NULL, recipient TEXT NOT NULL,
                    status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt REAL NOT NULL, message_id TEXT, error TEXT, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS auth_attempts (key TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS request_keys (
                    user_id TEXT NOT NULL, key TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    job_id TEXT NOT NULL, PRIMARY KEY(user_id, key));
                CREATE TABLE IF NOT EXISTS recovery_codes (
                    user_id TEXT PRIMARY KEY, digest TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS runtime_status (
                    name TEXT PRIMARY KEY, heartbeat REAL NOT NULL, detail TEXT NOT NULL);
            ''')
        path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def password_hash(password, salt=None):
        salt = salt or secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()
        return salt + ':' + digest

    def register(self, name, email, password):
        uid = secrets.token_hex(16)
        with self.connect() as db:
            db.execute('INSERT INTO users VALUES (?, ?, ?, ?, ?)',
                       (uid, email, name, self.password_hash(password), time.time()))
        return {'id': uid, 'name': name, 'email': email}

    def authenticate(self, email, password):
        with self.connect() as db:
            row = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        hashed = row['password'] if row else self.password_hash('invalid-password', '0' * 32)
        if not hmac.compare_digest(hashed, self.password_hash(password, hashed.split(':')[0])) or row is None:
            return None
        return {key: row[key] for key in ('id', 'name', 'email')}

    def create_session(self, user_id):
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES (?, ?, ?)',
                       (hashlib.sha256(token.encode()).hexdigest(), user_id, time.time() + 7 * 86400))
        return token

    def session_user(self, token):
        with self.connect() as db:
            row = db.execute('SELECT users.id, name, email FROM users JOIN sessions ON users.id=sessions.user_id '
                             'WHERE sessions.token=? AND sessions.expires>?',
                             (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        return dict(row) if row else None

    def logout(self, token):
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE token=?', (hashlib.sha256(token.encode()).hexdigest(),))

    def throttle(self, key):
        now = time.time()
        with self.connect() as db:
            db.execute('DELETE FROM auth_attempts WHERE created < ?', (now - 900,))
            count = db.execute('SELECT COUNT(*) FROM auth_attempts WHERE key=?', (key,)).fetchone()[0]
            if count >= 15:
                return False
            db.execute('INSERT INTO auth_attempts VALUES (?, ?)', (key, now))
        return True

    def create_job(self, user_id, request, mode):
        jid, now = secrets.token_hex(16), time.time()
        fingerprint = hashlib.sha256((mode + request.model_dump_json(exclude={'request_key'})).encode()).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if request.request_key:
                previous = db.execute('SELECT * FROM request_keys WHERE user_id=? AND key=?', (user_id, request.request_key)).fetchone()
                if previous:
                    if previous['fingerprint'] != fingerprint:
                        raise ValueError('This submission key already belongs to a different request. Open a new journey form.')
                    return self.decode(db.execute('SELECT * FROM jobs WHERE id=? AND user_id=?', (previous['job_id'], user_id)).fetchone())
            count = db.execute("SELECT COUNT(*) FROM jobs WHERE user_id=? AND status NOT IN ('CONFIRMED','EXPIRED','CANCELLED')", (user_id,)).fetchone()[0]
            if count >= 10:
                raise ValueError('You can have up to 10 active booking requests')
            db.execute('INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                       (jid, user_id, mode, 'SCHEDULED', request.model_dump_json(), '{}', now, now, now))
            if request.request_key:
                db.execute('INSERT INTO request_keys VALUES (?,?,?,?)', (user_id, request.request_key, fingerprint, jid))
        self.event(jid, 'created', 'Booking request saved. Monitoring will start shortly.')
        return self.job(jid, user_id)

    @staticmethod
    def decode(row):
        if row is None:
            return None
        result = dict(row)
        result['request'], result['data'] = json.loads(result['request']), json.loads(result['data'])
        return result

    def job(self, jid, user_id=None):
        with self.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?' + (' AND user_id=?' if user_id else ''),
                             (jid, user_id) if user_id else (jid,)).fetchone()
        return self.decode(row)

    def jobs(self, user_id):
        with self.connect() as db:
            return [self.decode(r) for r in db.execute('SELECT * FROM jobs WHERE user_id=? ORDER BY created DESC', (user_id,))]

    def due(self):
        with self.connect() as db:
            return [self.decode(r) for r in db.execute("SELECT * FROM jobs WHERE status IN ('SCHEDULED','MONITORING','AWAITING_PAYMENT') AND next_poll<=? ORDER BY next_poll LIMIT 20", (time.time(),))]

    def heartbeat(self, name, detail='ok'):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO runtime_status VALUES (?,?,?)', (name, time.time(), detail))

    def metrics(self):
        with self.connect() as db:
            return {'jobs': dict(db.execute('SELECT status,COUNT(*) FROM jobs GROUP BY status').fetchall()),
                    'notifications': dict(db.execute('SELECT status,COUNT(*) FROM notifications GROUP BY status').fetchall()),
                    'runtime': {r['name']: {'heartbeat':r['heartbeat'], 'detail':r['detail']} for r in db.execute('SELECT * FROM runtime_status')}}

    def recovery_code(self, user_id):
        code = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO recovery_codes VALUES (?,?,?)',
                       (user_id, hashlib.sha256(code.encode()).hexdigest(), time.time()))
        return code

    def reset_password(self, email, code, password):
        digest = hashlib.sha256(code.strip().encode()).hexdigest()
        hashed = self.password_hash(password)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT u.id,r.digest FROM users u JOIN recovery_codes r ON r.user_id=u.id WHERE email=?', (email,)).fetchone()
            if not hmac.compare_digest(row['digest'] if row else '0' * 64, digest):
                return False
            db.execute('UPDATE users SET password=? WHERE id=?', (hashed, row['id']))
            db.execute('DELETE FROM recovery_codes WHERE user_id=?', (row['id'],))
            db.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))
        return True

    def update(self, jid, status, data, delay=0, expected=None):
        with self.connect() as db:
            result = db.execute('UPDATE jobs SET status=?, data=?, next_poll=?, updated=? WHERE id=?' + (' AND status=?' if expected else ''),
                (status, json.dumps(data), time.time() + delay, time.time(), jid) + ((expected,) if expected else ()))
            return result.rowcount == 1

    def event(self, jid, kind, message):
        with self.connect() as db:
            db.execute('INSERT INTO events(job_id,kind,message,created) VALUES (?, ?, ?, ?)', (jid, kind, message, time.time()))

    def events(self, jid):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM events WHERE job_id=? ORDER BY id DESC LIMIT 40', (jid,))]

    def alert(self, job, kind, body, identity=''):
        req = job['request']
        status = 'preview' if job['mode'] == 'demo' else 'queued'
        if not req['whatsapp_opt_in']:
            status = 'not_requested'
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO notifications(id,job_id,dedupe,kind,body,recipient,status,next_attempt,created) VALUES (?,?,?,?,?,?,?,?,?)',
                       (secrets.token_hex(16), job['id'], f"{job['id']}:{kind}:{identity}", kind, body, req['whatsapp_phone'], status, time.time(), time.time()))

    def alerts(self, user_id):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT n.id,n.job_id,n.kind,n.body,n.status,n.error,n.created FROM notifications n JOIN jobs j ON j.id=n.job_id WHERE j.user_id=? ORDER BY n.created DESC LIMIT 50', (user_id,))]

    def recover(self):
        with self.connect() as db:
            rows = db.execute("SELECT id, data FROM jobs WHERE status='PREPARING' OR (mode='live' AND status='AWAITING_PAYMENT')").fetchall()
        for row in rows:
            data = json.loads(row['data'])
            data['reservation_attempted'] = True
            data['recovery_required'] = True
            data['message'] = 'The server restarted during a reservation. Check Shohoz before creating another booking; no automatic retry was made.'
            self.update(row['id'], 'NEEDS_ATTENTION', data)
            self.event(row['id'], 'attention', data['message'])
