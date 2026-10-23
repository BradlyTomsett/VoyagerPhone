"""Run the original engine in one browser worker; IndexedDB is the commit boundary."""
import sys, os, types
if sys.platform == 'emscripten':
    # There are no OS processes here. The outer Web Lock owns the entire save,
    # and worker requests are serialized. A memory fsync is NOT a durable save;
    # only the acknowledged IndexedDB snapshot is reported as saved to the user.
    fcntl = types.ModuleType('fcntl')
    fcntl.LOCK_EX, fcntl.LOCK_SH, fcntl.LOCK_UN, fcntl.LOCK_NB = 2, 1, 8, 4
    fcntl.flock = lambda *args: None
    sys.modules['fcntl'] = fcntl
    resource = types.ModuleType('resource')
    resource.RUSAGE_SELF = 0
    resource.getrusage = lambda *args: types.SimpleNamespace(ru_maxrss=0)
    sys.modules['resource'] = resource
    os.fsync = lambda fd: None
    if not hasattr(os,'link'):
        def unavailable_link(*args,**kwargs):raise OSError(95,'Hard links unavailable')
        os.link=unavailable_link
    os.environ['VOYAGER_DISABLE_SNAPSHOT_DEDUP'] = '1'

import copy, hashlib, io, json, shutil, sqlite3, time, uuid, zipfile
from pathlib import Path
from backend.app import GameService, ACTIVE, safe_error
from backend.engine import EngineBridge, canonical, digest, module
from backend.model import CRITERIA, WRAPPER, REVIEW, matches_output
from backend.source_library import SourceLibrary
from backend.fleet_archive import FleetArchive
from backend.world_archive import WorldArchive

COMMANDER_ID = 'PER-COMMANDER-01'


def commander_identity(state):
    role = state.get('key_personnel_current_roles', {}).get(COMMANDER_ID)
    if not isinstance(role, str) or not role.strip(): return None
    return {'id': COMMANDER_ID, 'name': '指挥官', 'role': role,
            'basis_ref': 'state:key_personnel_current_roles.' + COMMANDER_ID}


# Guard uses one subprocess solely for its version binding gate. WebAssembly
# has no processes: execute that same trusted engine source in an isolated module.
if sys.platform == 'emscripten':
    import subprocess
    def browser_version_run(args, **kwargs):
        if len(args)!=3 or args[2]!='--version-info':
            raise OSError('BROWSER_PROCESS_UNSUPPORTED')
        path=Path(args[1]).resolve()
        trusted=Path(__file__).resolve().parents[1]/'seed/engine.py'
        if path.name!='engine.py' or path.read_bytes()!=trusted.read_bytes():
            raise ValueError('BROWSER_ENGINE_SOURCE_UNTRUSTED')
        a=module(path,'browser_version_binding')
        return subprocess.CompletedProcess(args,0,json.dumps({
            'engine_version':a.ENGINE_VERSION,'engine_protocol':a.ENGINE_PROTOCOL,
            'guard_protocol':a.GUARD_PROTOCOL}), '')
    subprocess.run=browser_version_run


class BrowserBridge(EngineBridge):
    def source_library(self):
        identity = json.loads((self.root / 'manifest.json').read_bytes())['save_set_id']
        if getattr(self, '_library_identity', None) != identity:
            self._library = SourceLibrary(self.root)
            self._library_identity = identity
        return self._library

    def context(self, intent='', scene_id=None, actor_id=None):
        result = super().context(intent, scene_id, actor_id)
        if intent.strip(): result['source_library'] = self.source_library().context(intent)
        return result

    def contracts(self, kind):
        result = super().contracts(kind)
        if kind == 'setup':
            result['notes'].append('PER-COMMANDER-01 is the existing player commander in state:key_personnel_current_roles.PER-COMMANDER-01. If absent from the person registry, the browser prepends its exact identity registration to the reviewed setup. Do not emit entity_register yourself. Prepare life_profile, life_control and scene setup as usual; do not invent past experiences or physical location.')
        return result

    def normalize(self, plan, job, context):
        payload = super().normalize(plan, job, context)
        if plan['kind'] == 'setup' and job['request']['actor_id'] == COMMANDER_ID:
            state = json.loads((self.root / 'state.json').read_text())
            identity = commander_identity(state)
            if identity and COMMANDER_ID not in state.get('entity_registry', {}).get('entities', {}):
                if len(payload['actions']) >= 20: raise ValueError('SETUP_ACTIONS_INVALID')
                # Exact existing identity only. This is reviewed and confirmed with
                # the rest of the setup; choosing a name never mutates the save.
                payload['actions'].insert(0, {'type': 'entity_register',
                    'entity_id': COMMANDER_ID, 'name': identity['name'],
                    'aliases': [], 'role': identity['role']})
        return payload

    def recover(self):
        guard = module(self.root / 'guard.py', 'browser_trusted_guard')
        with guard.guard_lock(self.root):
            guard.recover_consistency_repair(self.root)
            if (self.root / '.runtime' / guard.COMMIT_JOURNAL).exists():
                _, errors = guard.recover_interrupted_commit(self.root)
                if errors: raise ValueError('GUARD_RECOVERY_FAILED')
            manifest, errors = guard.validate_dir(self.root, strict=True)
            if errors or not manifest: raise ValueError('SAVE_INTEGRITY_FAILED')
            _, errors = guard.verify_cold_archives(self.root, manifest)
            if errors: raise ValueError('COLD_ARCHIVE_VERIFY_FAILED')
            if not guard.development_intact(self.root, manifest):
                raise ValueError('DEVELOPMENT_INTEGRITY_FAILED')


class BrowserModel:
    configured = True  # Calls occur in the browser network adapter, never in Python.
    model = 'browser-configured-model'


class BrowserHost:
    def __init__(self, directory='/voyager'):
        self.directory = Path(directory)
        self.seed = Path(__file__).resolve().parents[1] / 'seed'
        self.baseline = {str(p.relative_to(self.seed)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in self.seed.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        self.game = GameService(self.directory, BrowserModel(), BrowserBridge, start=False)
        self.prepared = {}
        # A durable COMMITTING intent is replayed only under its original ID.
        for job in self.game.store.list():
            if job['status'] == 'COMMITTING': self.game.commit(job)

    def state(self): return self.game.bridge.state()
    def jobs(self): return [self.game.public(j) for j in reversed(self.game.store.list())]

    def choices(self):
        state = json.loads((self.game.bridge.root / 'state.json').read_text())
        entities = state.get('entity_registry', {}).get('entities', {})
        # Names/IDs from public registry metadata; no GM profiles or hidden facts.
        actors, places = [], []
        for eid, rec in entities.items():
            if not isinstance(rec, dict): continue
            if rec.get('visibility') in ('gm', 'secret', 'hidden'): continue
            item = {'id': eid, 'name': rec.get('canonical_name') or ('未命名人物' if eid.startswith('PER-') else '未命名地点')}
            if eid.startswith('PER-'): actors.append(item)
            if eid.startswith(('LOC-', 'PLACE-', 'STA-', 'SYS-', 'REG-')): places.append(item)
        commander = commander_identity(state)
        if commander:
            actors = [{'id': COMMANDER_ID, 'name': commander['name']}] + [a for a in actors if a['id'] != COMMANDER_ID]
        return {'actors': actors[:150], 'places': places[:200]}

    def begin(self, request):
        job = self.game.create(request)
        stored = self.game.store.get(job['id'])
        if stored['status'] != 'QUEUED': return {'job':job, 'packet':None}
        req = stored['request']
        context = self.game.bridge.context(req['intent'], req.get('scene_id'), req.get('actor_id'))
        stored.update(status='GENERATING', base_identity=context['prepare']['base_identity'])
        packet = {'mode':req['mode'], 'original_intent':req['intent'],
                  'selected_actor':req.get('actor_id'), 'context':context}
        if req.get('actor_id') == COMMANDER_ID:
            identity = commander_identity(json.loads((self.game.bridge.root / 'state.json').read_text()))
            if identity: packet['selected_actor_identity'] = identity
        prior = [j for j in reversed(self.game.store.list()) if j['id'] != stored['id']][-6:]
        packet['recent_dialogue'] = [
            {'intent':j['request']['intent'][:1000], 'message':j.get('message','')[:1500],
             'status':j['status'], 'world_effects_committed':j['status']=='SAVED'} for j in prior]
        if req['mode'] == 'action':
            packet['native_schema'] = self.game.bridge.contracts('setup' if context['status']=='NO_OPEN_SCENE' else 'turn')
        self.prepared[stored['id']] = context
        self.game.store.save(stored)
        return {'job':self.game.public(stored), 'packet':packet}

    def accept_plan(self, job_id, plan, usage):
        if not matches_output(plan, WRAPPER): raise ValueError('MODEL_SCHEMA_INVALID')
        if any(len(x)>500 for x in plan['choices']):raise ValueError('MODEL_CHOICES_INVALID')
        job = self.game.store.get(job_id)
        if not job or job['status'] != 'GENERATING': raise ValueError('TURN_NOT_GENERATING')
        context = self.prepared[job_id]
        kind = plan['kind']
        if job['request']['mode'] == 'query' and kind not in ('answer','needs_information'):
            raise ValueError('QUERY_CANNOT_WRITE')
        job.update(kind=kind, message=plan['message'], choices=plan['choices'][:6])
        job['usage'].append(usage)
        if kind in ('answer','needs_information'):
            job['status'] = 'ANSWERED' if kind=='answer' else 'NEEDS_INFORMATION'
            self.prepared.pop(job_id, None)
            packet = None
        else:
            job['payload'] = self.game.bridge.normalize(plan, job, context)
            job['status'] = 'REVIEWING'
            packet = {'context':context,'exact_payload':job['payload'],
                      'original_intent':job['request']['intent'],'kind':kind}
        self.game.store.save(job)
        return {'job':self.game.public(job), 'review_packet':packet}

    def accept_review(self, job_id, verdict, usage):
        if not matches_output(verdict, REVIEW): raise ValueError('MODEL_SCHEMA_INVALID')
        job = self.game.store.get(job_id)
        if not job or job['status'] != 'REVIEWING': raise ValueError('TURN_NOT_REVIEWING')
        job['usage'].append(usage)
        job['review'] = {**verdict, 'criteria':CRITERIA}
        if verdict['status'] != 'PASS':
            job.update(status='BLOCKED', error='INDEPENDENT_REVIEW_FAILED')
        else:
            payload = job['payload']; job['review_payload_hash'] = digest(payload)
            if job['kind'] == 'turn':
                job['validation'] = self.game.bridge.validate(payload, job['review'])
                if job['validation'].get('status') not in ('VALID','NEEDS_AUTHORIZATION'):
                    job.update(status='BLOCKED', error=job['validation'].get('code','NATIVE_VALIDATION_FAILED'))
            if job['status'] != 'BLOCKED':
                job.update(plan_hash=digest(payload), status='AWAITING_CONFIRMATION')
        self.game.store.save(job); self.prepared.pop(job_id,None)
        return self.game.public(job)

    def fail(self, job_id, code):
        job = self.game.store.get(job_id)
        if job and job['status'] in ('QUEUED','GENERATING','REVIEWING'):
            job.update(status='FAILED', error=code)
            self.game.store.save(job)
        self.prepared.pop(job_id,None)
        return self.game.public(job) if job else None

    def confirm_prepare(self, job_id, plan_hash):
        return self.game.confirm(job_id,plan_hash)

    def confirm_commit(self, job_id):
        job = self.game.store.get(job_id)
        if not job: raise ValueError('TURN_NOT_FOUND')
        if job['status'] == 'COMMITTING': self.game.process(job)
        return self.game.public(self.game.store.get(job_id))

    def recover_job(self, job_id):
        job=self.game.store.get(job_id)
        if not job or job['status']!='RECOVERY_REQUIRED' or not job.get('envelope'):
            raise ValueError('TURN_NOT_RECOVERABLE')
        self.game.bridge.recover()
        job['status']='COMMITTING';self.game.store.save(job)
        return self.game.public(job)

    def snapshot(self):
        root=self.game.bridge.root
        # Normal snapshots are deltas over the immutable bundled seed. Native
        # transaction directories are needed only for an unresolved native commit.
        dirty=any(j['status']=='RECOVERY_REQUIRED' for j in self.game.store.list())
        deleted=[]; records=[]
        for rel in self.baseline:
            if not (root/rel).is_file(): deleted.append(rel)
        for p in root.rglob('*'):
            if not p.is_file(): continue
            rel=p.relative_to(root)
            if '__pycache__' in rel.parts or p.suffix=='.pyc':continue
            if any(part.startswith('.') for part in rel.parts) and not dirty:continue
            data=p.read_bytes()
            if hashlib.sha256(data).hexdigest()!=self.baseline.get(str(rel)):
                records.append(('game/'+str(rel),data,p.stat().st_mode&0o777))
        backup=self.directory/'jobs-snapshot.sqlite3'
        backup.unlink(missing_ok=True)
        with self.game.store.db() as source:
            target=sqlite3.connect(backup)
            try:source.backup(target)
            finally:target.close()
        records.append(('web.sqlite3',backup.read_bytes(),0o600));backup.unlink()
        meta={'schema':'VOYAGER_BROWSER_SNAPSHOT_V1','deleted':deleted,'dirty':dirty,
              'save_set_id':self.game.bridge.identity()['save_set_id']}
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
            z.writestr('browser-snapshot.json',json.dumps(meta))
            for name,data,mode in records:
                info=zipfile.ZipInfo(name);info.external_attr=(mode|0o100000)<<16
                info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,data,compresslevel=1)
        return output.getvalue()

    def checkpoint_ack(self):
        if any(j['status'] in ('COMMITTING','RECOVERY_REQUIRED') for j in self.game.store.list()):return
        runtime=self.game.bridge.root/'.runtime'
        if runtime.exists():shutil.rmtree(runtime)

    def export(self):return self.game.export()

    def dispatch(self, method, data):
        try:return self._dispatch(method,data)
        except Exception as ex:raise ValueError(getattr(ex,'code',safe_error(ex))) from None

    def _dispatch(self, method, data):
        if method=='state':return self.state()
        if method=='jobs':return self.jobs()
        if method=='choices':return self.choices()
        if method in ('library_topics','library_topic','library_browse','fleet_domain'):
            library=self.game.bridge.source_library()
            if getattr(self,'_world_library',None) is not library:
                self._world_library=library;self._world_archive=WorldArchive(library)
            world=self._world_archive
            if method=='library_topics':return world.topics()
            if method=='library_topic':return world.topic(data.get('topic'))
            if method=='fleet_domain':return world.topic(data.get('domain'))
            return world.browse(data.get('query',''),data.get('offset',0),data.get('limit',16),data.get('history') is True,data.get('category','all'))
        if method=='library_summary':return self.game.bridge.source_library().summary()
        if method=='library_search':return self.game.bridge.source_library().search(
            data.get('query',''),data.get('offset',0),data.get('limit',16),
            data.get('history') is True,data.get('category','all'))
        if method in ('fleet_overview','fleet_ship','fleet_inventory','fleet_records','fleet_equipment'):
            archive=FleetArchive(self.game.bridge.source_library())
            if method=='fleet_overview':return archive.overview(data.get('fleet'))
            if method=='fleet_ship':return archive.ship(data.get('fleet'),data.get('vessel'))
            if method=='fleet_inventory':return archive.inventory(data.get('fleet'))
            if method=='fleet_records':return archive.records(data.get('fleet'))
            return archive.equipment(data.get('query',''),data.get('offset',0))
        if method=='begin':return self.begin(data)
        if method=='plan':return self.accept_plan(data['id'],data['plan'],data.get('usage',{}))
        if method=='review':return self.accept_review(data['id'],data['verdict'],data.get('usage',{}))
        if method=='fail':return self.fail(data['id'],data['code'])
        if method=='confirm_prepare':return self.confirm_prepare(data['id'],data['plan_hash'])
        if method=='confirm_commit':return self.confirm_commit(data['id'])
        if method=='cancel':return self.game.cancel(data['id'])
        if method=='recover':return self.recover_job(data['id'])
        if method=='ack':self.checkpoint_ack();return True
        raise ValueError('BROWSER_METHOD_UNKNOWN')


def checked_members(z, limit=96*1024*1024):
    total=0;seen=set()
    for info in z.infolist():
        path=Path(info.filename)
        if path.is_absolute() or '..' in path.parts or '\\' in info.filename or info.filename in seen:
            raise ValueError('IMPORT_PATH_INVALID')
        if (info.external_attr>>16)&0o170000==0o120000:raise ValueError('IMPORT_SYMLINK_INVALID')
        seen.add(info.filename);total+=info.file_size
        if total>limit or len(seen)>12000:raise ValueError('IMPORT_TOO_LARGE')
    return z.infolist()


def restore_snapshot(raw, directory='/voyager', seed='/app/seed'):
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        checked_members(z)
        meta=json.loads(z.read('browser-snapshot.json'))
        if meta.get('schema')!='VOYAGER_BROWSER_SNAPSHOT_V1':raise ValueError('SNAPSHOT_FORMAT_INVALID')
        root=out/'game';shutil.copytree(seed,root)
        for rel in meta.get('deleted',[]):
            path=Path(rel)
            if path.is_absolute() or '..' in path.parts:raise ValueError('IMPORT_PATH_INVALID')
            (root/path).unlink(missing_ok=True)
        for info in z.infolist():
            if info.is_dir() or info.filename=='browser-snapshot.json':continue
            if not (info.filename.startswith('game/') or info.filename=='web.sqlite3'):
                raise ValueError('SNAPSHOT_FILE_INVALID')
            data=z.read(info)
            if info.filename.startswith('game/') and info.filename.endswith('.py'):
                trusted=Path(seed)/Path(info.filename).relative_to('game')
                if not trusted.is_file() or data!=trusted.read_bytes():raise ValueError('SNAPSHOT_ENGINE_UNTRUSTED')
            dest=out/info.filename;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
            mode=(info.external_attr>>16)&0o777
            if mode:dest.chmod(mode)


def import_save(raw, directory='/voyager', seed='/app/seed'):
    stage=Path('/tmp/voyager-import-'+uuid.uuid4().hex);stage.mkdir()
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            members=checked_members(z)
            for info in members:
                if info.is_dir():continue
                rel=Path(info.filename)
                if any(x.startswith('.') or x=='__pycache__' for x in rel.parts):continue
                dest=stage/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(info))
        # Imported executable code is never accepted from an untrusted archive.
        baseline=Path(seed)
        for p in stage.rglob('*.py'):
            rel=p.relative_to(stage)
            if not (baseline/rel).is_file() or p.read_bytes()!=(baseline/rel).read_bytes():
                raise ValueError('IMPORT_ENGINE_VERSION_UNSUPPORTED')
        guard=module(baseline/'guard.py','browser_import_guard')
        manifest,errors=guard.validate_dir(stage,strict=True)
        if errors or not manifest or not guard.development_intact(stage,manifest):
            raise ValueError('IMPORT_INTEGRITY_FAILED')
        _,errors=guard.verify_cold_archives(stage,manifest)
        if errors:raise ValueError('IMPORT_ARCHIVES_INVALID')
        target=Path(directory)/'game'
        if target.exists():shutil.rmtree(target)
        stage.rename(target)
        for p in Path(directory).glob('web.sqlite3*'):p.unlink()
    finally:
        if stage.exists():shutil.rmtree(stage)
