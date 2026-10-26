"""Persistent single-owner WSGI application. Run one Gunicorn worker (threads OK)."""
import copy
from contextlib import contextmanager
import fcntl
import hmac
import io
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import sqlite3
import threading
import time
import uuid
import zipfile
from .engine import EngineBridge, SubmissionNotCommitted, canonical, digest
from .model import ModelClient, ModelError, CRITERIA
from .settings import load_settings, save_settings, validated_settings, public_settings
from .auth import OwnerAuth, LoginError, session_cookie

BASE = Path(__file__).resolve().parents[1]
ACTIVE = ('QUEUED', 'PREPARING', 'GENERATING', 'REVIEWING', 'AWAITING_CONFIRMATION', 'COMMITTING', 'RECOVERY_REQUIRED')

class APIError(Exception):
    def __init__(self, status, code, detail=None):
        self.status, self.code, self.detail = status, code, detail

class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, input_hash TEXT NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL, updated REAL NOT NULL)')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, job_id):
        with self.db() as db:
            row = db.execute('SELECT body FROM jobs WHERE id=?', (job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, job):
        job['updated_at'] = time.time()
        with self.db() as db:
            db.execute('UPDATE jobs SET status=?,body=?,updated=? WHERE id=?',
                (job['status'], canonical(job), job['updated_at'], job['id']))

    def list(self):
        with self.db() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT body FROM jobs ORDER BY updated DESC LIMIT 100')]

    def create(self, request):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT input_hash,body FROM jobs WHERE id=?', (request['client_id'],)).fetchone()
            input_hash = digest(request)
            if row:
                if row[0] != input_hash:
                    raise APIError(409, 'REQUEST_ID_REUSED')
                return json.loads(row[1]), False
            active = db.execute('SELECT id FROM jobs WHERE status IN (' + ','.join('?' for _ in ACTIVE) + ') LIMIT 1', ACTIVE).fetchone()
            if active:
                raise APIError(409, 'TURN_ALREADY_ACTIVE', active[0])
            job = {'id': request['client_id'], 'request': request, 'status': 'QUEUED',
                   'created_at': time.time(), 'updated_at': time.time(), 'usage': []}
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?)',
                       (job['id'], input_hash, job['status'], canonical(job), job['updated_at']))
            return job, True

class GameService:
    def __init__(self, data=None, model=None, bridge_factory=EngineBridge, start=True):
        self.data = Path(data or os.environ.get('VOYAGER_DATA_DIR', str(BASE / 'data'))).resolve()
        self.data.mkdir(parents=True, exist_ok=True)
        self.process_lock = (self.data / 'web-worker.lock').open('a+')
        try:
            fcntl.flock(self.process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('ONE_WEB_WORKER_PER_GAME_REQUIRED') from None
        root = self.data / 'game'
        if not root.exists():
            stage = self.data / ('initializing-' + uuid.uuid4().hex)
            shutil.copytree(BASE / 'seed', stage)
            stage.rename(root)
        self.store = Store(self.data / 'web.sqlite3')
        self.model = model or ModelClient(load_settings(self.data))
        self.transition_lock = threading.RLock()
        self.bridge = bridge_factory(root, self.authorize, self.review_exact)
        self.bridge.recover()
        self.signal = threading.Event()
        # Generation was never committed; do not silently spend tokens again after restart.
        # COMMITTING retains its exact envelope and replays only the native idempotent commit.
        with self.store.db() as db:
            rows = db.execute('SELECT body FROM jobs WHERE status IN (?,?,?,?)',
                              ('PREPARING', 'GENERATING', 'REVIEWING', 'QUEUED')).fetchall()
        for row in rows:
            job = json.loads(row[0]); job.update(status='INTERRUPTED', error='GENERATION_INTERRUPTED_RETRY_WITH_NEW_REQUEST')
            self.store.save(job)
        self.stopping = False
        if start:
            self.thread = threading.Thread(target=self.worker, daemon=True, name='voyager-turns')
            self.thread.start()

    def authorize(self, envelope):
        job = self.store.get(envelope.get('command', {}).get('command_id', ''))
        return bool(job and job['status'] == 'COMMITTING' and job.get('confirmed_at')
                    and job.get('envelope') == envelope
                    and job.get('plan_hash') == digest(job.get('payload'))
                    and job.get('review', {}).get('status') == 'PASS')

    def review_exact(self, proposal):
        job = self.store.get(proposal.get('turn_id', ''))
        if (job and job.get('review_payload_hash') == digest(proposal)
                and job.get('review', {}).get('status') == 'PASS'):
            return copy.deepcopy(job['review'])
        return None

    def create(self, data):
        if not self.model.configured:
            raise APIError(503, 'MODEL_NOT_CONFIGURED')
        if not isinstance(data, dict) or set(data) - {'client_id','intent','mode','actor_id','scene_id'}:
            raise APIError(400, 'REQUEST_FIELDS_INVALID')
        if not re.fullmatch(r'WEB-[a-zA-Z0-9-]{8,80}', data.get('client_id', '')):
            raise APIError(400, 'REQUEST_ID_INVALID')
        if data.get('mode') not in ('query', 'action'):
            raise APIError(400, 'MODE_INVALID')
        if not isinstance(data.get('intent'), str) or not 1 <= len(data['intent'].strip()) <= 2000:
            raise APIError(400, 'INTENT_INVALID')
        if data['mode'] == 'action' and not re.fullmatch(r'PER-[A-Za-z0-9_.:-]+', data.get('actor_id', '')):
            raise APIError(400, 'ACTION_REQUIRES_ACTOR')
        if data.get('scene_id') is not None:
            if not isinstance(data['scene_id'], str):
                raise APIError(400, 'SCENE_ID_INVALID')
            # An unfilled optional scene means "use the current scene". Keep
            # explicit IDs strict, and normalize before durable request hashing.
            scene_id = data['scene_id'].strip() or None
            if scene_id is not None and not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', scene_id):
                raise APIError(400, 'SCENE_ID_INVALID')
            data = {**data, 'scene_id': scene_id}
        with self.transition_lock:
            job, created = self.store.create(data)
        self.signal.set()
        return self.public(job)

    def model_settings(self):
        return public_settings({'api_key': self.model.key, 'base_url': self.model.base,
            'model_id': self.model.model, 'review_model_id': self.model.reviewer,
            'protocol': self.model.protocol})

    def configure_model(self, value):
        with self.transition_lock:
            with self.store.db() as db:
                active = db.execute('SELECT id FROM jobs WHERE status IN (' +
                    ','.join('?' for _ in ACTIVE) + ') LIMIT 1', ACTIVE).fetchone()
            if active:
                raise APIError(409, 'FINISH_ACTIVE_TURN_BEFORE_MODEL_CHANGE')
            current = {'api_key': self.model.key, 'base_url': self.model.base,
                'model_id': self.model.model, 'review_model_id': self.model.reviewer,
                'protocol': self.model.protocol}
            try:
                settings = validated_settings(value, current)
                client = ModelClient(settings)
            except ValueError as ex:
                raise APIError(400, safe_error(ex)) from None
            save_settings(self.data, settings)
            self.model = client
            return self.model_settings()

    def public(self, job):
        return {k: v for k, v in job.items() if k in {
            'id','request','status','created_at','updated_at','message','choices','payload',
            'plan_hash','error','review','usage','result','base_identity','kind','validation','uncommitted','reference_issues'}}

    def reject_unchanged_setup(self, job):
        """Call only after successful guard recovery; migrate known old failures."""
        if (job.get('status') == 'RECOVERY_REQUIRED' and job.get('kind') == 'setup'
                and job.get('error') in {'STORY_ENTITY_UNAVAILABLE', 'STORY_LOCATION_REFERENCE_INVALID', 'SETUP_REFERENCE_UNAVAILABLE'}
                and job.get('base_identity') == self.bridge.identity()):
            job.update(status='BLOCKED', uncommitted=True)
            self.store.save(job)
            return True
        return False

    def confirm(self, job_id, plan_hash):
        with self.transition_lock:
            job = self.store.get(job_id)
            if not job:
                raise APIError(404, 'TURN_NOT_FOUND')
            if job.get('plan_hash') != plan_hash:
                raise APIError(409, 'PLAN_HASH_MISMATCH')
            if job['status'] in ('COMMITTING', 'SAVED'):
                return self.public(job)
            if job['status'] != 'AWAITING_CONFIRMATION':
                raise APIError(409, 'TURN_NOT_CONFIRMABLE')
            if job['base_identity'] != self.bridge.identity():
                job.update(status='STALE', error='SAVE_CHANGED_PREPARE_AGAIN'); self.store.save(job)
                raise APIError(409, 'SAVE_CHANGED_PREPARE_AGAIN')
            # Persist the exact user-confirmed envelope and version BEFORE executing effects.
            job['envelope'] = self.bridge.envelope(job, job['kind'], job['payload'])
            job['next_version'] = self.bridge.next_version()
            job.update(status='COMMITTING', confirmed_at=time.time())
            self.store.save(job); self.signal.set()
            return self.public(job)

    def cancel(self, job_id):
        with self.transition_lock:
            job = self.store.get(job_id)
            if not job or job['status'] != 'AWAITING_CONFIRMATION':
                raise APIError(409, 'TURN_NOT_CANCELLABLE')
            job['status'] = 'CANCELLED'; self.store.save(job)
            return self.public(job)

    def generate(self, job):
        job['status'] = 'PREPARING'; self.store.save(job)
        req = job['request']
        context = self.bridge.context(req['intent'], req.get('scene_id'), req.get('actor_id'))
        job['base_identity'] = context['prepare']['base_identity']
        contract_kind = 'setup' if context['status'] == 'NO_OPEN_SCENE' else 'turn'
        packet = {'mode': req['mode'], 'original_intent': req['intent'], 'selected_actor': req.get('actor_id'),
                  'context': context}
        # Short dialogue continuity is advisory; only engine context establishes current facts.
        prior = [j for j in reversed(self.store.list()) if j['id'] != job['id']][-6:]
        packet['recent_dialogue'] = [
            {'intent': j['request']['intent'][:1000], 'message': j.get('message', '')[:1500],
             'status': j['status'], 'world_effects_committed': j['status'] == 'SAVED'} for j in prior]
        if req['mode'] == 'action':
            packet['native_schema'] = self.bridge.contracts(contract_kind)
        job['status'] = 'GENERATING'; self.store.save(job)
        plan, usage = self.model.generate(packet); job['usage'].append(usage)
        kind = plan.get('kind')
        if kind not in ('answer','setup','turn','needs_information') or not isinstance(plan.get('message'), str):
            raise ValueError('MODEL_PLAN_INVALID')
        choices = plan.get('choices', [])
        if not isinstance(choices, list) or any(not isinstance(x, str) or len(x) > 500 for x in choices):
            raise ValueError('MODEL_CHOICES_INVALID')
        job.update(kind=kind, message=plan['message'], choices=choices[:6])
        if req['mode'] == 'query' and kind not in ('answer','needs_information'):
            raise ValueError('QUERY_CANNOT_WRITE')
        if kind in ('answer','needs_information'):
            job['status'] = 'ANSWERED' if kind == 'answer' else 'NEEDS_INFORMATION'
            self.store.save(job); return
        payload = self.bridge.normalize(plan, job, context)
        job['status'] = 'REVIEWING'; self.store.save(job)
        verdict, usage = self.model.review(context, payload, req['intent'], kind)
        job['usage'].append(usage); job['review'] = verdict
        if verdict.get('status') != 'PASS' or verdict.get('criteria') != CRITERIA:
            job.update(status='BLOCKED', error='INDEPENDENT_REVIEW_FAILED'); self.store.save(job); return
        job['review_payload_hash'] = digest(payload)
        if kind == 'turn':
            validation = self.bridge.validate(payload, verdict); job['validation'] = validation
            if validation.get('status') not in ('NEEDS_AUTHORIZATION', 'VALID'):
                job.update(status='BLOCKED', error=validation.get('code', 'NATIVE_VALIDATION_FAILED'))
                self.store.save(job); return
        job.update(payload=payload, plan_hash=digest(payload), status='AWAITING_CONFIRMATION')
        self.store.save(job)

    def commit(self, job):
        result = self.bridge.submit(job)
        if result.get('status') in ('SAVED','ALREADY_APPLIED'):
            job.update(status='SAVED', result=result)
            job.pop('error', None); job.pop('uncommitted', None)
        elif result.get('status') == 'COMMITTED_REPORT_REQUIRES_REREAD':
            # Never regenerate/reexecute. Keep the exact envelope for explicit recovery.
            job.update(status='RECOVERY_REQUIRED', error='COMMITTED_REPORT_REQUIRES_REREAD')
        else:
            job.update(status='BLOCKED', error=result.get('code', result.get('status','SUBMIT_FAILED')))
        self.store.save(job)

    def process(self, job):
        was_commit = job['status'] == 'COMMITTING'
        try:
            if job['status'] == 'COMMITTING': self.commit(job)
            elif job['status'] == 'QUEUED': self.generate(job)
        except Exception as ex:
            # Keep uncertain commits recoverable; never re-plan their mechanical actions.
            rejected = was_commit and isinstance(ex, SubmissionNotCommitted)
            job.update(status='BLOCKED' if rejected else 'RECOVERY_REQUIRED' if was_commit else 'FAILED',
                       error=safe_error(ex))
            if rejected: job['uncommitted'] = True
            self.store.save(job)

    def worker(self):
        while not self.stopping:
            with self.store.db() as db:
                row = db.execute("SELECT body FROM jobs WHERE status IN ('COMMITTING','QUEUED') ORDER BY updated LIMIT 1").fetchone()
            if row:
                self.process(json.loads(row[0]))
            else:
                self.signal.wait(0.5); self.signal.clear()

    def export(self):
        with self.bridge.lock:
            a = self.bridge.host._engine()
            with a.SnapshotContext(self.bridge.root):
                a.ensure_source_ready(self.bridge.root)
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
                    for p in self.bridge.root.rglob('*'):
                        rel = p.relative_to(self.bridge.root)
                        if p.is_file() and not any(x.startswith('.') or x == '__pycache__' for x in rel.parts):
                            archive.write(p, str(rel))
                return buffer.getvalue()

def safe_error(ex):
    value = str(ex).split(':')[0]
    return value if re.fullmatch(r'[A-Z][A-Z0-9_]{2,100}', value) else 'REQUEST_FAILED'

_service = None
_service_lock = threading.Lock()
_owner_auth = None
_owner_auth_path = None
_owner_auth_fingerprint = None
_auth_lock = threading.Lock()

def login_auth():
    global _owner_auth, _owner_auth_path, _owner_auth_fingerprint
    configured = os.environ.get('VOYAGER_AUTH_FILE')
    path = Path(configured or Path(os.environ.get('VOYAGER_DATA_DIR', str(BASE / 'data'))) / 'login.json')
    if not path.exists():
        if configured or os.environ.get('VOYAGER_REQUIRE_LOGIN') == '1':
            raise APIError(503, 'SERVER_LOGIN_NOT_CONFIGURED')
        return None
    with _auth_lock:
        stat = path.stat()
        fingerprint = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
        if _owner_auth_path != str(path) or _owner_auth_fingerprint != fingerprint:
            _owner_auth = OwnerAuth(path)
            _owner_auth_path = str(path)
            _owner_auth_fingerprint = fingerprint
        return _owner_auth

def read_json(environ):
    try: length = int(environ.get('CONTENT_LENGTH','0') or 0)
    except ValueError: raise APIError(400, 'CONTENT_LENGTH_INVALID')
    if not 0 < length <= 131072: raise APIError(413, 'REQUEST_SIZE_INVALID')
    if not environ.get('CONTENT_TYPE','').startswith('application/json'):
        raise APIError(415, 'JSON_REQUIRED')
    try: return json.loads(environ['wsgi.input'].read(length))
    except ValueError: raise APIError(400, 'JSON_INVALID')

def check_session_request(environ):
    if (environ.get('HTTP_X_VOYAGER_REQUEST') != '1' or
            environ.get('HTTP_SEC_FETCH_SITE') == 'cross-site'):
        raise APIError(403, 'CSRF_REQUIRED')

def service():
    global _service
    with _service_lock:
        if _service is None: _service = GameService()
        return _service

def application(environ, start_response):
    headers = [('X-Content-Type-Options','nosniff'), ('Referrer-Policy','no-referrer'),
               ('Cache-Control','no-store'), ('X-Frame-Options','DENY')]
    origin = environ.get('HTTP_ORIGIN', '')
    allowed = {x.strip().rstrip('/') for x in os.environ.get('VOYAGER_ALLOWED_ORIGINS','').split(',') if x.strip()}
    same = environ.get('wsgi.url_scheme', 'http') + '://' + environ.get('HTTP_HOST', '')
    if origin and origin.rstrip('/') in allowed | {same}:
        headers += [('Access-Control-Allow-Origin', origin), ('Vary','Origin'),
                    ('Access-Control-Allow-Headers','Authorization, Content-Type, X-Voyager-Request'),
                    ('Access-Control-Allow-Methods','GET, POST, OPTIONS')]
    try:
        method = environ.get('REQUEST_METHOD','GET'); path = environ.get('PATH_INFO','/')
        if origin and origin.rstrip('/') not in allowed | {same}:
            raise APIError(403, 'ORIGIN_NOT_ALLOWED')
        owner = login_auth()
        if method == 'OPTIONS':
            status, body, mime = 204, b'', 'text/plain'
        elif path == '/api/health' and method == 'GET':
            status, body, mime = 200, canonical({'status':'ok', 'web_version':'0.3.0',
                'login_required': owner is not None}).encode(), 'application/json'
        elif path == '/api/auth/status' and method == 'GET':
            signed_in = bool(owner and owner.authenticated(environ))
            result = {'mode': 'password' if owner else 'token', 'authenticated': signed_in}
            if signed_in: result['username'] = owner.credentials['username']
            status, body, mime = 200, canonical(result).encode(), 'application/json'
        elif path == '/api/auth/login' and method == 'POST' and owner:
            check_session_request(environ)
            try: session = owner.login(read_json(environ))
            except LoginError as ex: raise APIError(ex.status, ex.code) from None
            headers.append(('Set-Cookie', session_cookie(environ, session)))
            status, body, mime = 200, b'{"authenticated":true}', 'application/json'
        else:
            protected = path.startswith('/api/') or path == '/snapshot.json'
            if protected:
                if owner:
                    if not owner.authenticated(environ): raise APIError(401, 'AUTH_REQUIRED')
                    if method not in ('GET', 'HEAD'): check_session_request(environ)
                else:
                    token = os.environ.get('VOYAGER_ACCESS_TOKEN','')
                    supplied = environ.get('HTTP_AUTHORIZATION','')
                    if len(token) < 32:
                        raise APIError(503, 'SERVER_ACCESS_TOKEN_NOT_CONFIGURED')
                    if not hmac.compare_digest(supplied, 'Bearer ' + token):
                        raise APIError(401, 'AUTH_REQUIRED')
            if path == '/api/auth/logout' and method == 'POST' and owner:
                owner.logout(environ)
                headers.append(('Set-Cookie', session_cookie(environ, clear=True)))
                status, body, mime = 200, b'{"authenticated":false}', 'application/json'
            elif path.startswith('/api/'):
                game = service()
                if method == 'GET' and path == '/api/status':
                    result = {'model_configured': game.model.configured,
                              'model': game.model.model if game.model.configured else None,
                              'engine': '2.74.0', 'web_version': '0.3.0', 'model_settings_supported': True,
                              'login_required': owner is not None}
                elif method == 'GET' and path == '/api/model-settings': result = game.model_settings()
                elif method == 'GET' and path == '/api/state': result = game.bridge.state()
                elif method == 'GET' and path == '/api/turns': result = [game.public(j) for j in reversed(game.store.list())]
                elif method == 'GET' and path == '/api/export':
                    body = game.export(); status = 200; mime = 'application/zip'
                    headers.append(('Content-Disposition','attachment; filename="VOYAGER_WEB_SAVE.zip"'))
                    result = None
                elif method == 'POST':
                    data = read_json(environ)
                    if path == '/api/model-settings': result = game.configure_model(data)
                    elif path == '/api/turns': result = game.create(data)
                    else:
                        match = re.fullmatch(r'/api/turns/(WEB-[A-Za-z0-9-]+)/(?P<action>confirm|cancel|recover)', path)
                        if not match: raise APIError(404, 'NOT_FOUND')
                        if match['action'] == 'confirm': result = game.confirm(match[1], data.get('plan_hash'))
                        elif match['action'] == 'cancel': result = game.cancel(match[1])
                        else:
                            with game.transition_lock:
                                job = game.store.get(match[1])
                                if not job or job['status'] != 'RECOVERY_REQUIRED' or not job.get('envelope'):
                                    raise APIError(409, 'TURN_NOT_RECOVERABLE')
                                game.bridge.recover()
                                if not game.reject_unchanged_setup(job):
                                    job['status'] = 'COMMITTING'; game.store.save(job); game.signal.set()
                                result = game.public(job)
                else: raise APIError(404, 'NOT_FOUND')
                if result is not None:
                    status, body, mime = 200, canonical(result).encode(), 'application/json; charset=utf-8'
            elif method == 'GET':
                # Deliberate whitelist: seed, database, source code and env files are never served.
                name = 'index.html' if path == '/' else path.removeprefix('/')
                if owner and name in ('index.html','login'):
                    name = 'index.html' if owner.authenticated(environ) else 'login.html'
                if name not in {'index.html','login.html','login.js','styles.css','app.js','manifest.webmanifest','sw.js','icon.svg','snapshot.json'}:
                    raise APIError(404, 'NOT_FOUND')
                file = BASE / 'dist' / name
                if not file.is_file(): raise APIError(404, 'NOT_FOUND')
                status, body = 200, file.read_bytes()
                mime = mimetypes.guess_type(str(file))[0] or 'application/octet-stream'
                if name in ('index.html','login.html'):
                    headers.append(('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' https: http://localhost:* http://127.0.0.1:*; object-src 'none'; base-uri 'none'; frame-ancestors 'self'"))
            else: raise APIError(405, 'METHOD_NOT_ALLOWED')
    except APIError as ex:
        status, body, mime = ex.status, canonical({'error':ex.code,'detail':ex.detail}).encode(), 'application/json'
    except Exception as ex:
        status, body, mime = 500, canonical({'error':safe_error(ex)}).encode(), 'application/json'
    if status == 429: headers.append(('Retry-After','300'))
    labels = {200:'OK',204:'No Content',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',405:'Method Not Allowed',409:'Conflict',413:'Content Too Large',415:'Unsupported Media Type',429:'Too Many Requests',500:'Internal Server Error',503:'Service Unavailable'}
    start_response(f'{status} {labels.get(status,"Error")}', headers + [('Content-Type',mime),('Content-Length',str(len(body)))])
    return [body]
