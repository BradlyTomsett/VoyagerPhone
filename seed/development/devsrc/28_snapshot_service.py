# === VOYAGER_DEV_MODULE: snapshot_service ===
_snapshot_scope=contextvars.ContextVar('voyager_snapshot_context',default=None)


def _derived_key(base):
    path=Path(base)/'.runtime'/'derived_cache.key';path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink():raise EngineError('CACHE_KEY_PATH_INVALID')
    if not path.exists():
        # Readers share the source lock: publish a fully written inode atomically,
        # never expose the empty O_EXCL file to another initializing reader.
        fd,name=tempfile.mkstemp(prefix='.derived_cache.key.',dir=path.parent);tmp=Path(name)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(os.urandom(32));stream.flush();os.fsync(stream.fileno())
            try:os.link(tmp,path);_native_sync_dir(path.parent)
            except FileExistsError:pass
        finally:tmp.unlink(missing_ok=True)
    if path.is_symlink():raise EngineError('CACHE_KEY_PATH_INVALID')
    key=path.read_bytes()
    if len(key)!=32:raise EngineError('CACHE_KEY_INVALID')
    return key


def _derived_read(base,name,binding):
    import hmac
    if os.environ.get('VOYAGER_DISABLE_DERIVED_CACHE')=='1':return None
    path=Path(base)/'.runtime'/name
    if not path.is_file() or path.is_symlink():return None
    try:
        wrapper=json.loads(path.read_text('utf-8'));body=wrapper['body'];keypath=Path(base)/'.runtime'/'derived_cache.key'
        if not keypath.is_file() or keypath.is_symlink():return None
        key=keypath.read_bytes()
        if len(key)!=32:return None
        expected=hmac.new(key,json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode(),'sha256').hexdigest()
        if not hmac.compare_digest(expected,wrapper['mac']) or body.get('binding')!=binding:return None
        return body['value']
    except Exception:return None


def _derived_write(base,name,binding,value):
    import hmac
    if os.environ.get('VOYAGER_DISABLE_DERIVED_CACHE')=='1':return
    body={'binding':binding,'value':value}
    try:
        mac=hmac.new(_derived_key(base),json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode(),'sha256').hexdigest()
        _native_atomic_json(Path(base)/'.runtime'/name,{'body':body,'mac':mac})
    except (OSError,EngineError):return False  # Optional derived data must not block healthy authority.
    return True


class SnapshotContext:
    """One cooperative shared lock and one verified byte set per read request.
    Cached semantics are keyed by actual hashes and authenticated locally; every
    request still hashes every declared archive and checks active recovery intent.
    """
    def __init__(self,base):
        self.base=Path(base).resolve();self.json={};self.views={};self.histories={};self.report=None;self.authority=None
        self.metrics={'json_parses':0,'history_decodes':0,'sha_calls':0,'bytes_hashed':0,'semantic_cache_hits':0,'full_semantic_checks':0,'history_index_incremental':0}
    def __enter__(self):
        existing=_snapshot_scope.get()
        if existing and existing.base==self.base:self.reused=existing;return existing
        self.reused=None;self.lock=engine_lock(self.base,exclusive=False);self.lock.__enter__();self.token=_snapshot_scope.set(self)
        try:
            manifest_bytes=(self.base/'manifest.json').read_bytes();self.manifest=strict_json_loads(manifest_bytes.decode('utf-8'))
            names=['manifest.json',*self.manifest.get('components',{}),*_component_cold_archives(self.manifest)]
            if (self.base/'development').exists():names+=list(self.manifest.get('development_sources',{}).get('files',{}))
            self.fingerprint={n:_snapshot_file_fingerprint(self.base/n) for n in dict.fromkeys(names)}
            if sha256_bytes(manifest_bytes)!=self.fingerprint['manifest.json']:raise EngineError('SNAPSHOT_MANIFEST_READ_NOT_BOUND')
            self.layout=self.boundary_layout()
            self.binding={'schema':'SNAPSHOT_SEMANTICS_V3','engine_version':ENGINE_VERSION,'fingerprint':self.fingerprint,'layout':self.layout}
            self.json['manifest.json']=self.manifest
            return self
        except BaseException:_snapshot_scope.reset(self.token);self.lock.__exit__(*sys.exc_info());raise
    def __exit__(self,*exc):
        if self.reused:return False
        try:
            if exc[0] is None:
                after={n:_snapshot_file_fingerprint(self.base/n) for n in self.fingerprint}
                if after!=self.fingerprint or self.boundary_layout()!=self.layout:raise EngineError('SNAPSHOT_CHANGED_DURING_READ')
                if any(_active_runtime_journal(self.base,n) for n in (NATIVE_COMMIT_JOURNAL_FILENAME,CONSISTENCY_REPAIR_JOURNAL)):raise EngineError('RECOVERY_INTENT_DURING_READ')
        finally:_snapshot_scope.reset(self.token);self.lock.__exit__(*exc)
    def boundary_layout(self):
        # Build lexical ancestors once. lstat and directory shape are still read
        # at BOTH boundaries; no mtime/stat tuple substitutes for content hashes.
        if not hasattr(self,'layout_paths'):
            paths={}
            for name in self.fingerprint:
                parts=Path(name).parts
                if not parts or Path(name).is_absolute() or '..' in parts:raise EngineError('SNAPSHOT_PATH_INVALID')
                for i in range(1,len(parts)+1):
                    rel=str(Path(*parts[:i]));paths[rel]=self.base/rel
            self.layout_paths=sorted(paths.items())
        rows=[]
        for rel,path in self.layout_paths:
            try:mode=path.lstat().st_mode
            except OSError:mode=None
            rows.append([rel,mode,stat.S_ISLNK(mode) if mode is not None else False])
        shape=sorted([p.name,p.is_file(),p.is_dir(),p.is_symlink()] for p in self.base.iterdir() if not p.name.startswith('.'))
        return {'paths':rows,'shape':shape}

    def _read_value(self,path):
        name=path.name
        if path.parent!=self.base:return _batch_b_strict_json(path)
        if name not in self.json:
            data=path.read_bytes()
            if name in self.fingerprint and sha256_bytes(data)!=self.fingerprint[name]:raise EngineError('SNAPSHOT_READ_BYTES_NOT_BOUND')
            self.metrics['json_parses']+=1;self.json[name]=strict_json_loads(data.decode('utf-8'))
        return self.json[name]
    def read(self,path):
        path=Path(path).resolve();self.metrics['json_mutable_copies']=self.metrics.get('json_mutable_copies',0)+1
        if path.name=='state.json':self.metrics['state_mutable_copies']=self.metrics.get('state_mutable_copies',0)+1
        return copy.deepcopy(self._read_value(path))
    def read_view(self,path):
        path=Path(path).resolve();value=self._read_value(path)
        if path.parent!=self.base:return _stage2_freeze(value)
        if path.name not in self.views:
            self.views[path.name]=_stage2_freeze(value);self.metrics['json_view_builds']=self.metrics.get('json_view_builds',0)+1
        return self.views[path.name]
    def validated_report(self):
        if self.report is not None:return copy.deepcopy(self.report)
        for name in (NATIVE_COMMIT_JOURNAL_FILENAME,CONSISTENCY_REPAIR_JOURNAL):
            if _active_runtime_journal(self.base,name):
                self.report=_batch_b_readiness(self.base);return copy.deepcopy(self.report)
        if any(v is None for v in self.fingerprint.values()):
            self.metrics['full_semantic_checks']+=1;self.report=_batch_b_readiness(self.base);return copy.deepcopy(self.report)
        value=_derived_read(self.base,'read_semantics_v2.json',self.binding)
        if value is not None:
            self.report=value;self.metrics['semantic_cache_hits']+=1
        else:
            self.metrics['full_semantic_checks']+=1;self.report=_batch_b_readiness(self.base)
            if self.report['status']!='BLOCKED':_derived_write(self.base,'read_semantics_v2.json',self.binding,self.report)
        if self.report['status']!='BLOCKED':self.authority=_snapshot_authority(self.base,self.manifest,self.fingerprint)
        return copy.deepcopy(self.report)


def _snapshot_authority(base,manifest,fingerprint):
    ver=parse_version(manifest['save_version']);data=manifest['authority_components'];bundle=manifest['authority_bundle_sha256']
    index={'version':ver,'save_set_id':manifest['save_set_id'],'parent_save_set_id':manifest.get('parent_save_set_id'),'engine_version':manifest['engine_version'],'engine_sha256':manifest['tool_bindings']['engine.py'],'save_guard_sha256':manifest['tool_bindings']['guard.py'],'hashes':data,'bundle':bundle}
    return {'base':base,'version':ver,'bundle':bundle,'save_set_id':manifest['save_set_id'],'manifest':data,'index':index,'index_sha256':fingerprint['manifest.json'],'component_manifest':manifest}


def _snapshot_file_fingerprint(path):
    try:return _snapshot_sha_file(path)
    except OSError:return None  # Absence/unreadability is a blocking validation input.


def _snapshot_sha_file(path):
    ctx=_stage2_cache_owner()
    if ctx:
        ctx.metrics['sha_calls']=ctx.metrics.get('sha_calls',0)+1
        try:ctx.metrics['bytes_hashed']=ctx.metrics.get('bytes_hashed',0)+Path(path).stat().st_size
        except OSError:pass
    return _batch_b_sha_file(path)


def _snapshot_json_read(path):
    ctx=_snapshot_scope.get();path=Path(path).resolve()
    return ctx.read(path) if ctx and path.parent==ctx.base and path.suffix=='.json' else _batch_b_strict_json(path)


def _snapshot_history_read(path,validate_metadata=True):
    if _stage2_memo() is None:return _batch_b_history_read(Path(path),validate_metadata)
    _stage2_count('history_full_copies')
    return copy.deepcopy(_stage2_history_value(path,validate_metadata))


def _snapshot_epoch_decode(rec,lineno=0,base=None,_archive_bytes=None):
    return _stage2_epoch_value(rec,lineno,base,_archive_bytes)


def _snapshot_readiness(base=ROOT):
    ctx=_snapshot_scope.get()
    if ctx and Path(base).resolve()==ctx.base:return ctx.validated_report()
    try:
        with SnapshotContext(base) as snapshot:return snapshot.validated_report()
    except (OSError,json.JSONDecodeError):return _batch_b_readiness(Path(base).resolve())


def _snapshot_validate_authority(base):
    ctx=_snapshot_scope.get()
    if ctx and Path(base).resolve()==ctx.base and ctx.authority is not None:return copy.deepcopy(ctx.authority)
    return _batch_b_validate_authority(base)


def _history_locator_binding(base):
    m=strict_json_load(Path(base)/'manifest.json')
    return {'schema':'HISTORY_LOCATORS_V2','engine':sha256_file(Path(base)/'engine.py'),'history':sha256_file(Path(base)/'events.jsonl'),'cold':{n:r['file_sha256'] for n,r in _component_cold_archives(m).items() if 'seq_start' in r}}


def history_locator_index(base):
    base=Path(base).resolve();binding=_history_locator_binding(base);cached=_derived_read(base,'history_locator_v2.json',binding)
    if cached is not None:return cached
    data=(base/'events.jsonl').read_bytes();rows=data.splitlines(keepends=True);body=b''.join(rows[1:]);prior=_derived_read(base,'history_locator_incremental.json',{'engine':binding['engine'],'cold':binding['cold']})
    locators={};commands={};offset=0;start_line=0;last_seq=0
    if prior and len(body)>=prior['body_bytes'] and sha256_bytes(body[:prior['body_bytes']])==prior['body_sha256']:
        locators=copy.deepcopy(prior['events']);commands=prior['commands'];last_seq=prior['last_seq'];start_line=prior['physical_lines'];offset=sum(len(x) for x in rows[:start_line]);ctx=_snapshot_scope.get()
        shift=len(rows[0])-prior['header_bytes']
        for loc in locators.values():
            if 'offset' in loc:loc['offset']+=shift
        if ctx:ctx.metrics['history_index_incremental']+=1
    for i,raw in enumerate(rows):
        if i<start_line:continue
        if not raw.strip():offset+=len(raw);continue
        rec=strict_json_loads(raw.decode())
        if rec.get('record_type')=='metadata':offset+=len(raw);continue
        if rec.get('record_type')=='history_epoch':
            events,raws=_decode_history_epoch_record(rec,i+1,base)
            pairs=[(ev,{'epoch':copy.deepcopy(rec),'index':j,'raw_sha256':sha256_bytes(eraw)}) for j,(ev,eraw) in enumerate(zip(events,raws))]
        else:pairs=[(rec,{'offset':offset,'length':len(raw),'raw_sha256':sha256_bytes(raw.rstrip(b'\r\n'))})]
        for ev,loc in pairs:
            if ev.get('seq')!=last_seq+1 or ev.get('event_id') in locators:raise EngineError('HISTORY_LOCATOR_SEQUENCE')
            last_seq=ev['seq'];locators[ev['event_id']]=loc
            if ev.get('command_id'):
                # A transaction may also contain a changeset; authoritative command
                # receipts are the unique domain commit event, not the audit diff.
                if ev.get('subtype')=='domain_command_commit':
                    if ev['command_id'] in commands:raise EngineError('HISTORY_COMMAND_RECEIPT_DUPLICATE')
                    commands[ev['command_id']]=ev['event_id']
        offset+=len(raw)
    meta=strict_json_loads(rows[0].decode())
    if meta['next_seq']!=last_seq+1:raise EngineError('HISTORY_LOCATOR_METADATA_TAIL')
    index={'header_bytes':len(rows[0]),'events':locators,'commands':commands,'last_seq':last_seq,'body_bytes':len(body),'body_sha256':sha256_bytes(body),'physical_lines':len(rows)}
    _derived_write(base,'history_locator_v2.json',binding,index)
    _derived_write(base,'history_locator_incremental.json',{'engine':binding['engine'],'cold':binding['cold']},index)
    return index


def history_lookup(base,event_id=None,command_id=None):
    base=Path(base).resolve();index=history_locator_index(base)
    if command_id:event_id=index['commands'].get(command_id)
    loc=index['events'].get(event_id)
    if loc is None:return None
    if 'epoch' in loc:
        events,raws=_decode_history_epoch_record(loc['epoch'],0,base);raw=raws[loc['index']];ev=events[loc['index']]
    else:
        with (base/'events.jsonl').open('rb') as stream:stream.seek(loc['offset']);raw=stream.read(loc['length']).rstrip(b'\r\n')
        ev=strict_json_loads(raw.decode())
    if sha256_bytes(raw)!=loc['raw_sha256'] or ev.get('event_id')!=event_id:raise EngineError('HISTORY_LOCATOR_PAYLOAD_CHANGED')
    return ev


def read_json_view(path):
    """Internal immutable ownership; a matching snapshot remains mandatory."""
    path=Path(path).resolve();ctx=_snapshot_scope.get()
    if not ctx or ctx.base!=path.parent:return _stage2_freeze(_batch_b_strict_json(path))
    return ctx.read_view(path)
