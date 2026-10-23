# === VOYAGER_DEV_MODULE: performance_context ===
# All caches below are request/transaction owned, never authority or persisted proof.
_stage2_tx_scope=contextvars.ContextVar('voyager_transaction_validation_v1',default=None)
_stage2_presentation_scope=contextvars.ContextVar('voyager_presentation_v1',default='compact')
_stage2_budget_scope=contextvars.ContextVar('voyager_output_budget_v1',default=16384)
_stage2_previous_sourcecheck=component_source_check
_stage2_previous_main=main
_stage2_previous_turn=turn_packet
_stage2_previous_plan=routineplan_packet
_stage2_previous_report=reportframe_packet
_stage2_previous_session=turn_session
_stage2_previous_domain=domain_command_packet
_stage2_previous_atomic=atomic_save
_stage2_previous_checks=run_checks
_stage2_previous_changes=_event_v3_field_changes


class _ReadOnlyDict(dict):
    __slots__=('_sealed',)
    def __init__(self,*args,**kwargs):
        if hasattr(self,'_sealed'):raise EngineError('IMMUTABLE_INTERNAL_VIEW')
        dict.__init__(self,*args,**kwargs);self._sealed=True
    def _deny(self,*args,**kwargs):raise EngineError('IMMUTABLE_INTERNAL_VIEW')
    __setitem__=__delitem__=clear=pop=popitem=setdefault=update=__ior__=_deny
    def __deepcopy__(self,memo):return {copy.deepcopy(k,memo):copy.deepcopy(v,memo) for k,v in self.items()}


class _ReadOnlyList(list):
    __slots__=('_sealed',)
    def __init__(self,*args,**kwargs):
        if hasattr(self,'_sealed'):raise EngineError('IMMUTABLE_INTERNAL_VIEW')
        list.__init__(self,*args,**kwargs);self._sealed=True
    def _deny(self,*args,**kwargs):raise EngineError('IMMUTABLE_INTERNAL_VIEW')
    __setitem__=__delitem__=append=extend=insert=pop=remove=clear=reverse=sort=__iadd__=__imul__=_deny
    def __deepcopy__(self,memo):return [copy.deepcopy(v,memo) for v in self]


def _stage2_freeze(value):
    if isinstance(value,(_ReadOnlyDict,_ReadOnlyList)):return value
    if isinstance(value,dict):return _ReadOnlyDict({k:_stage2_freeze(v) for k,v in value.items()})
    if isinstance(value,list):return _ReadOnlyList(_stage2_freeze(v) for v in value)
    if isinstance(value,tuple):return tuple(_stage2_freeze(v) for v in value)
    return value


def _stage2_cache_owner():
    return _stage2_tx_scope.get() or _snapshot_scope.get()


def _stage2_memo():
    if os.environ.get('VOYAGER_DISABLE_VALIDATION_REUSE')=='1':return None
    owner=_stage2_cache_owner()
    if owner is None:return None
    if not hasattr(owner,'proofs'):owner.proofs={}
    return owner.proofs


def _stage2_count(name):
    owner=_stage2_cache_owner()
    if owner is not None:owner.metrics[name]=owner.metrics.get(name,0)+1


_stage2_epoch_process_cache=collections.OrderedDict()
_stage2_epoch_process_lock=threading.RLock()
_STAGE2_EPOCH_PROCESS_BYTES=64*1024*1024
_STAGE2_EPOCH_PROCESS_ENTRIES=32


def _stage2_epoch_process_get(key):
    with _stage2_epoch_process_lock:
        row=_stage2_epoch_process_cache.get(key)
        if row is not None:_stage2_epoch_process_cache.move_to_end(key);return row[1]
    return None


def _stage2_epoch_process_put(key,value):
    size=sum(len(raw) for raw in value[1])
    if size>_STAGE2_EPOCH_PROCESS_BYTES:return
    with _stage2_epoch_process_lock:
        _stage2_epoch_process_cache[key]=(size,value);_stage2_epoch_process_cache.move_to_end(key)
        while len(_stage2_epoch_process_cache)>_STAGE2_EPOCH_PROCESS_ENTRIES or sum(row[0] for row in _stage2_epoch_process_cache.values())>_STAGE2_EPOCH_PROCESS_BYTES:
            _stage2_epoch_process_cache.popitem(last=False)


def _stage2_epoch_value(rec,lineno=0,base=None,_archive_bytes=None):
    memo=_stage2_memo()
    if memo is None:return _batch_b_epoch_decode(rec,lineno,base,_archive_bytes=_archive_bytes)
    archive=None
    if rec.get('archive_ref'):
        rel=str(rec['archive_ref'])
        if base is None or rel.startswith('/') or '..' in Path(rel).parts:raise EngineError('HISTORY_ARCHIVE_REFERENCE_INVALID:'+rel)
        _archive_bytes=(Path(base)/rel).read_bytes() if _archive_bytes is None else _archive_bytes
        archive=sha256_bytes(_archive_bytes);snapshot=_snapshot_scope.get()
        if snapshot and snapshot.base==Path(base).resolve() and snapshot.fingerprint.get(rel)!=archive:raise EngineError('SNAPSHOT_ARCHIVE_READ_NOT_BOUND')
    key=('epoch-v2',ENGINE_VERSION,sys.version,sys.flags.optimize,_repair_digest(rec),archive)
    if key in memo:_stage2_count('epoch_cache_hits');return memo[key]
    value=_stage2_epoch_process_get(key)
    if value is not None:
        memo[key]=value;_stage2_count('epoch_process_hits');return value
    _stage2_count('epoch_cache_misses');_stage2_count('history_decodes')
    value=_stage2_freeze(_batch_b_epoch_decode(rec,lineno,base,_archive_bytes=_archive_bytes));memo[key]=value
    _stage2_epoch_process_put(key,value)
    return value


def _stage2_history_value(path,validate_metadata=True,_raw_bytes=None):
    path=Path(path).resolve();memo=_stage2_memo()
    data=path.read_bytes() if _raw_bytes is None else _raw_bytes;digest=sha256_bytes(data);deps=[];archives={}
    snapshot=_snapshot_scope.get()
    if snapshot and snapshot.base==path.parent and path.name in snapshot.fingerprint and digest!=snapshot.fingerprint[path.name]:raise EngineError('SNAPSHOT_HISTORY_READ_NOT_BOUND')
    # Actual JSON keys (including legal unicode escapes), never substring guesses.
    refkey=('history-archive-refs-v2',digest);refs=memo.get(refkey) if memo is not None else None
    if refs is None:
        refs=[]
        for raw in data.splitlines():
            if not raw.strip():continue
            rec=strict_json_loads(raw.decode('utf-8'))
            if rec.get('record_type')=='history_epoch' and rec.get('archive_ref'):refs.append(str(rec['archive_ref']))
        refs=tuple(refs)
        if memo is not None:memo[refkey]=refs
    for rel in refs:
        if rel.startswith('/') or '..' in Path(rel).parts:raise EngineError('HISTORY_ARCHIVE_REFERENCE_INVALID:'+rel)
        if rel not in archives:archives[rel]=(path.parent/rel).read_bytes()
        deps.append((rel,sha256_bytes(archives[rel])))
    key=('history-v2',str(path),ENGINE_VERSION,validate_metadata,digest,tuple(deps))
    if memo is not None and key in memo:_stage2_count('history_cache_hits');return memo[key]
    _stage2_count('history_cache_misses')
    value=_stage2_freeze(_batch_b_history_read(path,validate_metadata,_raw_bytes=data,_archive_bytes_by_ref=archives))
    if memo is not None:memo[key]=value
    return value


def read_history_view(path,_raw_bytes=None):
    """Internal immutable events/raw bytes, independently mutable small metadata.
    Public read_history_raw returns isolated mutable data, never this shared tree.
    No-scope callers receive the same read-only ownership contract.
    """
    meta,events,raws=_stage2_history_value(path,True,_raw_bytes)
    return copy.deepcopy(meta),events,raws


_stage2_static_cache={}
_STAGE2_COMPILE_RULE_VERSION='compile-success-v2'
_STAGE2_AST_RULE_VERSION='ast-structure-v2'


def _stage2_static_key(kind,raw,rule,flags=0,dont_inherit=True,optimize=-1):
    return (kind,rule,sys.implementation.name,sys.implementation.cache_tag,sys.version,
            sys.flags.optimize,flags,dont_inherit,optimize,sha256_bytes(raw))


def _stage2_static_store(key,value):
    if len(_stage2_static_cache)>=32:_stage2_static_cache.pop(next(iter(_stage2_static_cache)))
    _stage2_static_cache[key]=copy.deepcopy(value)


def _stage2_validate_tool_compile(raw,filename,flags=0,dont_inherit=True,optimize=-1):
    # SUCCESS is path independent. Failures are raised afresh with this filename.
    key=_stage2_static_key('compile',raw,_STAGE2_COMPILE_RULE_VERSION,flags,dont_inherit,optimize)
    if os.environ.get('VOYAGER_DISABLE_VALIDATION_REUSE')!='1' and _stage2_static_cache.get(key) is True:
        _stage2_count('compile_proof_hits');return
    _stage2_count('compile_executions')
    compile(raw,filename,'exec',flags=flags,dont_inherit=dont_inherit,optimize=optimize)
    if os.environ.get('VOYAGER_DISABLE_VALIDATION_REUSE')!='1':_stage2_static_store(key,True)


def _stage2_dependencies(base):
    base=Path(base).resolve();m=_batch_b_strict_json(base/'manifest.json')
    names=['manifest.json',*m.get('components',{}),*_component_cold_archives(m)]
    if (base/'development').exists():names+=list(m.get('development_sources',{}).get('files',{}))
    names += ['.runtime/'+n for n in (NATIVE_COMMIT_JOURNAL_FILENAME,CONSISTENCY_REPAIR_JOURNAL)]
    modes={};files=[]
    for name in sorted(set(names)):
        parts=Path(name).parts
        if not parts or Path(name).is_absolute() or '..' in parts:raise EngineError('SNAPSHOT_PATH_INVALID')
        links=[]
        for i in range(len(parts),0,-1):
            rel=str(Path(*parts[:i]))
            if rel not in modes:
                try:modes[rel]=(base/rel).lstat().st_mode
                except OSError:modes[rel]=None
            if modes[rel] is not None and stat.S_ISLNK(modes[rel]):links.append(rel)
        path=base/name
        try:mode=path.stat().st_mode
        except FileNotFoundError:mode=None
        files.append((name,_snapshot_file_fingerprint(path),tuple(links),mode))
    shape=tuple(sorted((p.name,p.is_file(),p.is_dir(),p.is_symlink()) for p in base.iterdir() if not p.name.startswith('.')))
    return (ENGINE_VERSION,sys.version,str(base),tuple(files),shape)


class TransactionValidationContext:
    """Own the write lock and byte-bound immutable proofs for ONE operation.

    Working state remains an independently mutable load; snapshots never span a
    publication. Nested same-root operations reuse this scope and the lock depth.
    """
    def __init__(self,base):
        self.base=Path(base).resolve();self.proofs={};self.metrics={};self.identities={};self.changed_paths=[];self.validation_results=[];self.stage_evidence=None;self.published_evidence=None;self.supplement_evidence=None;self.source_evidence={}
    def __enter__(self):
        existing=_stage2_tx_scope.get()
        if existing and existing.base==self.base:self.reused=existing;return existing
        self.reused=None;self.lock=engine_lock(self.base,exclusive=True);self.lock.__enter__();self.token=_stage2_tx_scope.set(self)
        try:
            self.parent=_batch_b_strict_json(self.base/'manifest.json');self.identities['parent']={'save_set_id':self.parent.get('save_set_id'),'manifest_sha256':_snapshot_sha_file(self.base/'manifest.json')}
            return self
        except BaseException:_stage2_tx_scope.reset(self.token);self.lock.__exit__(*sys.exc_info());raise
    def __exit__(self,*exc):
        if self.reused:return False
        try:
            if (self.base/'manifest.json').is_file():
                m=_batch_b_strict_json(self.base/'manifest.json');self.identities['target']={'save_set_id':m.get('save_set_id'),'manifest_sha256':_snapshot_sha_file(self.base/'manifest.json')}
        finally:
            self.proofs.clear();self.stage_evidence=None;self.published_evidence=None;self.supplement_evidence=None;self.source_evidence.clear();_stage2_tx_scope.reset(self.token);self.lock.__exit__(*exc)

    @staticmethod
    def source_binding(dependencies):
        version,python,root,files,shape=dependencies
        return (version,python,root,tuple(r for r in files if not r[0].startswith('.runtime/')),shape)

    @staticmethod
    def semantic_binding(dependencies):
        return tuple((r[0],r[1]) for r in dependencies[3] if not r[0].startswith(('development/','.runtime/')))

    def readiness_reuse(self,base):
        supplement=self.supplement_evidence
        if (os.environ.get('VOYAGER_DISABLE_VALIDATION_REUSE')!='1' and supplement is not None
                and Path(base).resolve()==supplement['base'] and _stage2_dependencies(base)==supplement['dependencies']):
            _stage2_count('run_checks_readiness_layer_hits')
            return {'layers':copy.deepcopy(supplement['layers']),'source_contract':None}
        proof=self.published_evidence
        if os.environ.get('VOYAGER_DISABLE_VALIDATION_REUSE')=='1' or proof is None or Path(base).resolve()!=self.base:return None
        if any(_active_runtime_journal(self.base,n) for n in (NATIVE_COMMIT_JOURNAL_FILENAME,CONSISTENCY_REPAIR_JOURNAL)):return None
        current=_stage2_dependencies(self.base)
        if self.semantic_binding(current)!=proof['semantic_binding']:return None
        local=self.source_evidence.get(self.source_binding(current))
        if local is None or local.get('status')!='PASS':return None
        _stage2_count('published_readiness_proof_hits')
        return {'layers':copy.deepcopy(proof['readiness']['layers']),
                'source_contract':{'status':local['status'],'errors':copy.deepcopy(local.get('errors',[]))}}


def _stage2_sourcecheck(root=COMPONENT_ROOT,strict_fileset=True):
    memo=_stage2_memo()
    if memo is None:return _stage2_previous_sourcecheck(root,strict_fileset)
    try:binding=_stage2_dependencies(root)
    except Exception:return _stage2_previous_sourcecheck(root,strict_fileset)
    key=('component-source-v1',strict_fileset,binding)
    if key in memo:
        _stage2_count('component_proof_hits');return copy.deepcopy(memo[key])
    _stage2_count('component_check_executions');result=_stage2_previous_sourcecheck(root,strict_fileset)
    if binding!=_stage2_dependencies(root):raise EngineError('SOURCE_CHANGED_DURING_COMPONENT_CHECK')
    if result['status']=='PASS':
        memo[key]=copy.deepcopy(result);ctx=_stage2_tx_scope.get()
        if ctx is not None and Path(root).resolve()==ctx.base:ctx.source_evidence[ctx.source_binding(binding)]=copy.deepcopy(result)
    return result


def _stage2_changes(parent,current,changed):
    result=_stage2_previous_changes(parent,current,changed);ctx=_stage2_tx_scope.get()
    if ctx is not None:ctx.changed_paths=copy.deepcopy(result)
    return result


def _stage2_checks(base,full=False,expected_version=None,require_manifest=True,parent_snapshot=None,validation_cache=None):
    ctx=_stage2_tx_scope.get()
    if (_snapshot_scope.get() is None or _snapshot_scope.get().base!=Path(base).resolve()) and (Path(base)/'manifest.json').is_file():
        snapshot=SnapshotContext(base)
        try:snapshot.__enter__()
        except Exception:return _stage2_previous_checks(base,full,expected_version,require_manifest,parent_snapshot,validation_cache)
        try:result=_stage2_checks(base,full,expected_version,require_manifest,parent_snapshot,validation_cache)
        except BaseException:snapshot.__exit__(*sys.exc_info());raise
        snapshot.__exit__(None,None,None);return result
    before=_stage2_dependencies(base) if ctx is not None else None
    result=_stage2_previous_checks(base,full,expected_version,require_manifest,parent_snapshot,validation_cache)
    if ctx is not None:
        after=_stage2_dependencies(base)
        if before!=after:raise EngineError('SOURCE_CHANGED_DURING_TRANSACTION_VALIDATION')
        ctx.identities['working']={'root':str(Path(base).resolve()),'dependencies':after}
        record={'phase':'parent' if Path(base).resolve()==ctx.base else 'staged_target','root':str(Path(base).resolve()),'dependencies':after,'validator_version':ENGINE_VERSION,'full':full,'require_manifest':require_manifest,'expected_version':expected_version,'parent_save_set_id':(parent_snapshot or {}).get('save_set_id'),'result':copy.deepcopy(result)}
        ctx.validation_results.append(record)
        if (os.environ.get('VOYAGER_DISABLE_VALIDATION_REUSE')!='1' and full and require_manifest and result.get('status')=='PASS'
                and Path(base).resolve()!=ctx.base and (parent_snapshot or {}).get('save_set_id')==ctx.parent.get('save_set_id')):
            _stage2_count('staged_readiness_executions')
            # Same five pure validators/arguments as readiness; no inferred READY.
            ctx.supplement_evidence={'base':Path(base).resolve(),'dependencies':after,
                'layers':{k:copy.deepcopy(result[k]) for k in ('accounts','content','memory','story','business') if isinstance(result.get(k),dict)}}
            try:ready=_batch_b_readiness(Path(base).resolve())
            finally:ctx.supplement_evidence=None
            if after!=_stage2_dependencies(base):raise EngineError('SOURCE_CHANGED_DURING_STAGED_READINESS')
            if ready.get('status')!='BLOCKED':ctx.stage_evidence={'phase':'staged_target','record':record,'semantic_binding':ctx.semantic_binding(after),'save_set_id':ready.get('save_set_id'),'readiness':copy.deepcopy(ready)}
    return result


def _stage2_session(*args,**kwargs):
    presentation=kwargs.pop('presentation',_stage2_presentation_scope.get())
    if presentation not in ('compact','full'):raise EngineError('PRESENTATION_OPTIONS_INVALID')
    with TransactionValidationContext(ROOT):
        result=_stage2_previous_session(*args,**kwargs)
        return _stage2_present_write(result,ROOT,presentation)



def _stage2_domain(base,*args,**kwargs):
    presentation=kwargs.pop('presentation',_stage2_presentation_scope.get())
    if presentation not in ('compact','full'):raise EngineError('PRESENTATION_OPTIONS_INVALID')
    with TransactionValidationContext(base):
        result=_stage2_previous_domain(base,*args,**kwargs)
        return _stage2_present_write(result,base,presentation)



def _stage2_atomic(staging,version,scope,root=ROOT,*args,**kwargs):
    with TransactionValidationContext(root) as ctx:
        result=_stage2_previous_atomic(staging,version,scope,root,*args,**kwargs);proof=ctx.stage_evidence
        if (result.get('committed') and proof is not None and result.get('save_set_id')==proof['save_set_id']
                and ctx.semantic_binding(_stage2_dependencies(root))==proof['semantic_binding']):ctx.published_evidence={**proof,'phase':'published_target'}
        return result


def _stage2_turn(base,*args,**kwargs):
    with SnapshotContext(base):return _stage2_previous_turn(base,*args,**kwargs)


def _stage2_plan(base,*args,**kwargs):
    with SnapshotContext(base):return _stage2_previous_plan(base,*args,**kwargs)


def _stage2_report(base,*args,**kwargs):
    with SnapshotContext(base):return _stage2_previous_report(base,*args,**kwargs)


component_source_check=_stage2_sourcecheck
_event_v3_field_changes=_stage2_changes
run_checks=_stage2_checks
turn_session=_stage2_session
domain_command_packet=_stage2_domain
atomic_save=_stage2_atomic
turn_packet=_stage2_turn
routineplan_packet=_stage2_plan
reportframe_packet=_stage2_report
TransactionService.context=staticmethod(TransactionValidationContext)


def _stage2_report_history(base,start,since_seq):
    ctx=_snapshot_scope.get();binding={'schema':'REPORT_HISTORY_SUMMARY_V1','binding':ctx.binding if ctx and ctx.base==Path(base).resolve() else _stage2_dependencies(base)}
    summary=_derived_read(base,'report_history_summary_v1.json',binding)
    if summary is None:
        meta,events,raws=read_history_view(Path(base)/'events.jsonl')
        times=[e['game_time'] for e in events if e.get('finance') is not None and parse_iso(e.get('game_time')) is not None]
        summary={'through_seq':max((int(e.get('seq') or 0) for e in events),default=0),'structured_start':min(times) if times else None}
        _derived_write(base,'report_history_summary_v1.json',binding,summary)
    else:meta=events=raws=None
    state=read_json(Path(base)/'state.json');end=state.get('game_time')
    if since_seq is not None and (isinstance(since_seq,bool) or since_seq<0 or since_seq>summary['through_seq']):raise EngineError('REPORT_CURSOR_INVALID')
    if (since_seq is None and parse_iso(start)==parse_iso(end)) or since_seq==summary['through_seq']:
        _stage2_count('report_zero_interval_hits');return [],summary
    if events is None:_,events,_=read_history_view(Path(base)/'events.jsonl')
    return events,summary


def _stage2_reference(snapshot,viewer='player'):
    return {'schema':'SNAPSHOT_DIAGNOSTIC_REF_V1','save_set_id':snapshot.manifest['save_set_id'],'manifest_sha256':snapshot.fingerprint['manifest.json'],'engine_sha256':snapshot.fingerprint.get('engine.py'),'viewer':viewer,'query':'diagnostics --ref <this object>'}


def _stage2_readiness_brief(report,reference):
    layers=report.get('layers',{});limits={}
    for key in ('runtime_clock','execution_coverage'):
        row=layers.get(key,{})
        if row.get('status') not in (None,'PASS'):limits[key]=copy.deepcopy(row)
    return {'schema':'READINESS_COMPACT_V1','status':report.get('status'),'save_set_id':report.get('save_set_id'),'game_time':report.get('game_time'),'errors':copy.deepcopy(report.get('errors',[])),'capabilities':copy.deepcopy(report.get('capabilities',{})),'limitations':limits,'diagnostic_ref':reference}


def _stage2_finalize_size(packet,budget=None):
    if not isinstance(packet,dict):return packet
    if budget is not None:
        packet['context_budget_bytes']=budget;packet['budget_exceeded']=False
        packet['budget_status']='WITHIN_BUDGET'
    packet['context_bytes']=0
    for _ in range(12):
        size=len(json.dumps(packet,ensure_ascii=False,separators=(',',':'),default=str).encode('utf-8'))
        if budget is not None:
            exceeded=size>budget;packet['budget_exceeded']=exceeded;packet['budget_status']='EXCEEDED_REQUIRES_PAGINATION' if exceeded else 'WITHIN_BUDGET'
        if packet['context_bytes']==size:break
        packet['context_bytes']=size
    return packet


def compact_packet(packet,snapshot,viewer='player',budget_bytes=16384):
    """V1 presentation projection. All domain values/constraints remain intact.

    Only repeated diagnostic containers are replaced. Legacy full returns are
    available with --presentation full. byte counts measure the final JSON body.
    """
    out=copy.deepcopy(packet)
    if out.get('packet') in ('STORY_PREPARE_V1','STORY_TURN_COMMIT_RESULT_V1') and str(out.get('viewer','')).startswith('npc:'):viewer=out['viewer']
    ref=_stage2_reference(snapshot,viewer);report=snapshot.validated_report()
    brief=_stage2_readiness_brief(report,ref)
    if viewer.startswith(('observer:','npc:')):
        # Integrity diagnostics describe commander-private business/clock state.
        # They are never an observer's knowledge, including on denied/full/error routes.
        brief={'schema':'READINESS_COMPACT_V1','status':report.get('status'),'save_set_id':report.get('save_set_id'),'game_time':report.get('game_time'),'errors':['SOURCE_NOT_READY'] if report.get('status')=='BLOCKED' else [],'capabilities':{'read':report.get('capabilities',{}).get('read',False)},'limitations':{'visibility':'observer scope only; private diagnostics unavailable'},'diagnostic_ref':ref}
        if out.get('error'):out['error']=str(out['error']).split(':',1)[0]
    if out.get('packet')==COLD_START_PACKET_SCHEMA and out.get('presentation_version') in ('compact_v1','compact_v2'):
        # Keep the established startup summary and its 3500-byte protection.
        # It already includes limitations, pending decisions and the next blocker.
        out['presentation_version']='compact_v2'
        out['source_context']={'diagnostic_ref':ref}
        return _stage2_finalize_size(out,min(budget_bytes,3500))
    def project(value):
        if isinstance(value,dict):
            for key,row in list(value.items()):
                if key in ('source_ready','readiness') and isinstance(row,dict) and (
                    row.get('schema') in (READINESS_SCHEMA,'READINESS_COMPACT_V1') or
                    (isinstance(row.get('component_manifest'),dict) and row['component_manifest'].get('schema') in (COMPONENT_SET_SCHEMA,COMPONENT_SET_SCHEMA_LEGACY) and 'index_sha256' in row) or
                    (value.get('packet')==COLD_START_PACKET_SCHEMA and key=='readiness' and row.get('details')=='readiness')):value[key]=copy.deepcopy(brief)
                else:project(row)
        elif isinstance(value,list):
            for row in value:project(row)
    project(out)
    out['presentation_version']='compact_v2'
    out['source_context']={'save_set_id':snapshot.manifest['save_set_id'],'game_time':snapshot.manifest['game_time'],'viewer':viewer,'integrity_status':report['status'],'diagnostic_ref':ref}
    # Some legacy projections omit readiness altogether; preserve limitations once.
    out.setdefault('readiness',brief)
    return _stage2_finalize_size(out,budget_bytes)


def round_context_packet(base=ROOT,topics=None,audience='player',observer_id=None,gm_context=None,budget_bytes=16384):
    """Default one-request batch; no full state/rules/history is exported."""
    topics=['五项余额','任务','当前场景'] if topics is None else topics
    with SnapshotContext(base) as snapshot:
        packet=visible_query_batch_packet(base,topics,audience=audience,observer_id=observer_id,gm_context=gm_context)
        return compact_packet(packet,snapshot,_scene_viewer(audience,observer_id,gm_context),budget_bytes)


def snapshot_diagnostics(base,reference,audience='player',observer_id=None,gm_context=None):
    viewer=_scene_viewer(audience,observer_id,gm_context)
    with SnapshotContext(base) as snapshot:
        expected=_stage2_reference(snapshot,viewer)
        if not isinstance(reference,dict) or any(reference.get(k)!=expected[k] for k in ('schema','save_set_id','manifest_sha256','engine_sha256','viewer')):raise EngineError('DIAGNOSTIC_REFERENCE_STALE_OR_WRONG_VIEWER')
        if viewer.startswith('observer:'):raise EngineError('VISIBILITY_OBSERVER_DIAGNOSTICS_DENIED')
        return {'packet':'SNAPSHOT_DIAGNOSTICS_V1','reference':expected,'readiness':snapshot.validated_report()}


def _stage2_present_write(result,base,presentation):
    # Enter a FRESH read scope only AFTER the write finishes, while retaining the
    # transaction's existing exclusive lock. Optional presentation cannot turn an
    # already committed operation into an apparent uncommitted failure.
    if presentation=='full' or not isinstance(result,dict):return result
    try:
        with SnapshotContext(base) as snapshot:
            sid=result.get('save_set_id') or result.get('commit',{}).get('save_set_id') or result.get('save',{}).get('save_set_id') or result.get('source_context',{}).get('save_set_id')
            if sid and sid!=snapshot.manifest['save_set_id']:
                fallback=copy.deepcopy(result);fallback['presentation_status']='RESULT_VERSION_ALREADY_ADVANCED';return fallback
            viewer=result.get('viewer','player') if result.get('packet') in ('STORY_PREPARE_V1','STORY_TURN_COMMIT_RESULT_V1') and str(result.get('viewer','')).startswith('npc:') else 'player'
            context=result.get('source_context',{});reference=context.get('diagnostic_ref',{})
            expected=_stage2_reference(snapshot,viewer)
            if (result.get('presentation_version')=='compact_v2' and context.get('save_set_id')==snapshot.manifest['save_set_id'] and context.get('viewer')==viewer and all(reference.get(k)==expected[k] for k in ('schema','save_set_id','manifest_sha256','engine_sha256','viewer'))):
                return _stage2_finalize_size(copy.deepcopy(result),_stage2_budget_scope.get())
            return compact_packet(result,snapshot,viewer,_stage2_budget_scope.get())
    except Exception as ex:
        fallback=copy.deepcopy(result);fallback['presentation_status']='FULL_FALLBACK';fallback['presentation_error']=str(ex).split(':',1)[0] if str(result.get('viewer','')).startswith(('npc:','observer:')) else str(ex)
        return fallback


def _stage2_writes_main(args):
    import io,contextlib
    presentation='compact';budget=16384
    try:
        args=list(args)
        for option in ('--presentation','--budget-bytes'):
            if option in args:
                i=args.index(option);value=args[i+1];del args[i:i+2]
                if option=='--presentation':presentation=value
                else:budget=int(value)
        if presentation not in ('compact','full') or not 512<=budget<=1048576:raise EngineError('PRESENTATION_OPTIONS_INVALID')
        token=_stage2_presentation_scope.set(presentation);btoken=_stage2_budget_scope.set(budget)
        try:
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream):result=_stage2_previous_main(args)
            raw=stream.getvalue()
            if result==0 and presentation=='compact':
                try:
                    packet=json.loads(raw)
                    base=Path(args[args.index('--base')+1]) if '--base' in args else ROOT
                    with SnapshotContext(base) as snapshot:
                        sid=packet.get('save_set_id') or packet.get('commit',{}).get('save_set_id') or packet.get('save',{}).get('save_set_id')
                        if sid and sid!=snapshot.manifest['save_set_id']:
                            packet['presentation_status']='RESULT_VERSION_ALREADY_ADVANCED'
                        elif (packet.get('presentation_version')=='compact_v2' and packet.get('source_context',{}).get('save_set_id')==snapshot.manifest['save_set_id'] and packet.get('source_context',{}).get('diagnostic_ref',{}).get('manifest_sha256')==snapshot.fingerprint['manifest.json'] and packet.get('source_context',{}).get('diagnostic_ref',{}).get('engine_sha256')==snapshot.fingerprint.get('engine.py')):packet=_stage2_finalize_size(packet,budget)
                        else:packet=compact_packet(packet,snapshot,'player',budget)
                    raw=json.dumps(packet,ensure_ascii=False,separators=(',',':'),default=str)+'\n'
                except Exception as ex:
                    # The old transaction result stays authoritative on display failure.
                    try:
                        packet=json.loads(raw);packet['presentation_status']='FULL_FALLBACK';packet['presentation_error']=str(ex)
                        raw=json.dumps(packet,ensure_ascii=False,separators=(',',':'),default=str)+'\n'
                    except Exception:pass
            print(raw,end='');return result
        finally:_stage2_budget_scope.reset(btoken);_stage2_presentation_scope.reset(token)
    except Exception as ex:
        print(json.dumps({'status':'FAIL','error':str(ex)},ensure_ascii=False));return 1


def _stage2_main(argv=None):
    import io,contextlib
    args=list(sys.argv[1:] if argv is None else argv);cmd=args[0] if args else ''
    reads={'readiness','query','querybatch','startup','boot','accountquery','contentquery','memoryread','historylookup','turn','routineplan','reportframe','businessquery','schedulercoverage','startupfull','knowledgequery','narrativecontext','narrativevalidate','narrativereport','experience','storyprojection','sceneindex','scenequery','assetquery','commandcatalog','pricequery','roundcontext','diagnostics'}
    if cmd not in reads:
        if cmd in {'session','autoadvance','invoke','domaincommand','hostinvoke'}:return _stage2_writes_main(args)
        return _stage2_previous_main(args)
    viewer='player'
    try:
        presentation='compact';budget=16384
        for option in ('--presentation','--budget-bytes'):
            if option in args:
                i=args.index(option)
                if i+1>=len(args):raise EngineError('PRESENTATION_OPTION_MISSING_VALUE')
                val=args[i+1];del args[i:i+2]
                if option=='--presentation':presentation=val
                else:budget=int(val)
        if presentation not in ('compact','full') or not 512<=budget<=1048576:raise EngineError('PRESENTATION_OPTIONS_INVALID')
        base=Path(args[args.index('--base')+1]) if '--base' in args else ROOT
        audience=args[args.index('--audience')+1] if '--audience' in args else 'player'
        observer=args[args.index('--observer-id')+1] if '--observer-id' in args else None
        gm=args[args.index('--gm-context')+1] if '--gm-context' in args else None
        viewer=_scene_viewer(audience,observer,gm)
        if viewer.startswith('observer:'):
            if cmd not in {'query','querybatch','roundcontext','scenequery','sceneindex','knowledgequery','narrativecontext','reportframe'}:raise EngineError('VISIBILITY_OBSERVER_PRIVATE_ROUTE_DENIED')
            if cmd in {'knowledgequery','narrativecontext'}:
                if '--viewer' in args:
                    if args[args.index('--viewer')+1]!=viewer:raise EngineError('KNOWLEDGE_REQUESTED_VIEWER_NOT_AUTHORIZED')
                else:args+=['--viewer',viewer]
        stream=io.StringIO()
        with SnapshotContext(base) as snapshot:
            if cmd in ('roundcontext','diagnostics'):
                parser=argparse.ArgumentParser();parser.add_argument('--base',default=str(base));parser.add_argument('--audience',default='player');parser.add_argument('--observer-id');parser.add_argument('--gm-context')
                if cmd=='roundcontext':parser.add_argument('--topics')
                else:parser.add_argument('--ref',required=True)
                ns=parser.parse_args(args[1:])
                if cmd=='roundcontext':out=round_context_packet(base,json.loads(ns.topics) if ns.topics else None,audience,observer,gm,budget)
                else:out=snapshot_diagnostics(base,json.loads(ns.ref),audience,observer,gm)
                result=0
            else:
                with contextlib.redirect_stdout(stream):result=_stage2_previous_main(args)
                raw=stream.getvalue()
                try:out=json.loads(raw)
                except json.JSONDecodeError:out=None
            # Construct and buffer every observable result before the final byte check.
            if out is not None:
                if ((presentation=='compact' and result==0) or viewer.startswith('observer:')) and cmd not in ('readiness','diagnostics','startupfull'):
                    out=compact_packet(out,snapshot,viewer,budget)
                elif isinstance(out,dict) and 'context_bytes' in out:
                    out=_stage2_finalize_size(out,out.get('requested_budget_bytes',out.get('context_budget_bytes')))
                if os.environ.get('VOYAGER_METRICS')=='1':
                    out['read_metrics']=snapshot.metrics
                    if 'context_bytes' in out:_stage2_finalize_size(out,out.get('context_budget_bytes'))
                raw=json.dumps(out,ensure_ascii=False,separators=(',',':'),default=str)+'\n'
        print(raw,end='');return result
    except Exception as ex:
        print(json.dumps({'status':'FAIL','error':str(ex).split(':',1)[0] if viewer.startswith('observer:') else str(ex)},ensure_ascii=False,separators=(',',':')));return 1


main=_stage2_main
SnapshotReader.round_context=staticmethod(round_context_packet)
SnapshotReader.diagnostics=staticmethod(snapshot_diagnostics)

TransactionService.commit=staticmethod(_stage2_atomic)
