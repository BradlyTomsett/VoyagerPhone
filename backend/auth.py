"""Single-owner password authentication. Credentials and sessions stay outside Git."""
from contextlib import contextmanager
import hashlib
import hmac
from http.cookies import SimpleCookie, CookieError
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile
import time

COOKIE = 'voyager_session'
SESSION_SECONDS = 7 * 24 * 3600


def password_hash(password, salt):
    return hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt),
                          n=16384, r=8, p=1, dklen=32).hex()


def create_credentials(path, username='commander', password=None):
    """Return the initial password once; never overwrite an existing account."""
    path = Path(path)
    if path.exists():
        OwnerAuth(path)  # Validate rather than silently replacing a damaged account.
        return None
    if not re.fullmatch(r'[A-Za-z0-9_.@-]{3,64}', username):
        raise ValueError('LOGIN_USERNAME_INVALID')
    password = password or secrets.token_urlsafe(18)
    if not 16 <= len(password) <= 256:
        raise ValueError('LOGIN_PASSWORD_TOO_SHORT')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    salt = secrets.token_hex(16)
    value = {'version': 1, 'username': username, 'salt': salt,
             'password_hash': password_hash(password, salt)}
    # Publish a complete, fsynced file without clobbering another initializer.
    fd, staged = tempfile.mkstemp(prefix='.login-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream)
            stream.flush(); os.fsync(stream.fileno())
        try:
            os.link(staged, path)
        except FileExistsError:
            OwnerAuth(path)
            return None
    finally:
        os.unlink(staged)
    return password


class LoginError(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


class OwnerAuth:
    def __init__(self, path):
        self.path = Path(path)
        self.credentials = json.loads(self.path.read_text())
        value = self.credentials
        if (value.get('version') != 1 or
                not re.fullmatch(r'[A-Za-z0-9_.@-]{3,64}', value.get('username', '')) or
                not re.fullmatch(r'[a-f0-9]{32}', value.get('salt', '')) or
                not re.fullmatch(r'[a-f0-9]{64}', value.get('password_hash', ''))):
            raise ValueError('LOGIN_CONFIGURATION_INVALID')
        os.chmod(self.path, 0o600)
        self.database = self.path.with_name('login-sessions.sqlite3')
        fd = os.open(self.database, os.O_RDWR | os.O_CREAT, 0o600)
        os.fchmod(fd, 0o600); os.close(fd)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS sessions (digest TEXT PRIMARY KEY, expires REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS failures (created REAL NOT NULL)')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.database, timeout=20)
        try:
            with db:
                yield db
        finally:
            db.close()

    def cookie_token(self, environ):
        try:
            cookies = SimpleCookie(); cookies.load(environ.get('HTTP_COOKIE', ''))
            value = cookies.get(COOKIE)
            token = value.value if value else ''
            return token if re.fullmatch(r'[A-Za-z0-9_-]{43}', token) else ''
        except CookieError:
            return ''

    def authenticated(self, environ):
        token = self.cookie_token(environ)
        if not token:
            return False
        with self.db() as db:
            row = db.execute('SELECT expires FROM sessions WHERE digest=?',
                             (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        return bool(row and row[0] > time.time())

    def login(self, value):
        if (not isinstance(value, dict) or set(value) != {'username', 'password'} or
                not isinstance(value['username'], str) or not isinstance(value['password'], str) or
                len(value['username']) > 64 or not 1 <= len(value['password']) <= 256):
            raise LoginError(400, 'LOGIN_FIELDS_INVALID')
        # A global limit cannot be bypassed by spoofing proxy IP headers or usernames.
        # Serialize checks and scrypt so concurrent attempts obey the same limit.
        now = time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM failures WHERE created < ?', (now - 300,))
            limited = db.execute('SELECT COUNT(*) FROM failures').fetchone()[0] >= 20
            if limited:
                outcome = 'limited'
            else:
                hashed = password_hash(value['password'], self.credentials['salt'])
                matches = hmac.compare_digest(hashed, self.credentials['password_hash'])
                matches &= hmac.compare_digest(value['username'].encode(), self.credentials['username'].encode())
                if not matches:
                    db.execute('INSERT INTO failures VALUES (?)', (now,))
                    outcome = 'invalid'
                else:
                    token = secrets.token_urlsafe(32)
                    db.execute('DELETE FROM sessions WHERE expires <= ?', (now,))
                    db.execute('INSERT INTO sessions VALUES (?,?)',
                               (hashlib.sha256(token.encode()).hexdigest(), now + SESSION_SECONDS))
                    db.execute('DELETE FROM failures')
                    outcome = 'ok'
        # Raise after the transaction commits, so failed attempts remain counted.
        if outcome == 'limited':
            raise LoginError(429, 'LOGIN_RATE_LIMITED')
        if outcome == 'invalid':
            raise LoginError(401, 'LOGIN_INVALID')
        return token

    def logout(self, environ):
        token = self.cookie_token(environ)
        with self.db() as db:
            db.execute('DELETE FROM sessions WHERE digest=?',
                       (hashlib.sha256(token.encode()).hexdigest(),))


def session_cookie(environ, token='', clear=False):
    host = environ.get('HTTP_HOST', '').split(':')[0].lower()
    local = host in ('localhost', '127.0.0.1')
    secure = '' if local and os.environ.get('VOYAGER_REQUIRE_LOGIN') != '1' and not os.environ.get('CODESPACE_NAME') else '; Secure'
    age = 0 if clear else SESSION_SECONDS
    return f'{COOKIE}={token}; Path=/; Max-Age={age}; HttpOnly; SameSite=Lax{secure}'
