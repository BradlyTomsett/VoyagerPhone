# === VOYAGER_DEV_MODULE: mobile_read_cache ===
_mobile_read_scope=contextvars.ContextVar('voyager_mobile_read_scope',default=None)
_mobile_read_json=_v1403_previous_read_json
_mobile_validate_authority=_v1403_previous_validate_authority_set
_mobile_query_intent_key=_v1403_previous__query_intent_key
_mobile_query_intent=_v1403_previous_query_intent_packet
_mobile_cold_start=_v1403_previous_cold_start_packet
_mobile_source_sync=_v1403_previous__component_transport_sync_status
_mobile_atomic_save=_v1403_previous__native_atomic_save_unlocked
_mobile_query_packet=_v1403_previous_query_packet
_PATROL_TASK_ID='TSK-SHADOW-XIANYUE-ASTEROID-PATROL'
_PATROL_SLOT='world_state_overrides.intelligence_and_security.xianyue_asteroid_shadow_patrol_current.current_local_event'

def _read_validation_fingerprint(base:Path,manifest:dict)->dict:
    """Actual content digests, including every declared cold archive."""
    names=['manifest.json',*COMPONENT_FILES[1:],*_component_cold_archives(manifest).keys()]
    return {name:sha256_file(base/name) for name in names}

def _cached_mobile_validate_authority(base:Path)->Optional[dict]:
    """Reuse a successful semantic check only for the same exact byte set."""
    base=Path(base).resolve()
    if base!=ROOT.resolve():return _mobile_validate_authority(base)
    try:
        manifest=_component_manifest_read(base)
        fingerprint=_read_validation_fingerprint(base,manifest)
        expected={**(manifest.get('components') or {}),
                  **{rel:row.get('file_sha256') for rel,row in _component_cold_archives(manifest).items()}}
        if any(fingerprint.get(fn)!=digest for fn,digest in expected.items()):return None
        key=sha256_bytes(json.dumps(fingerprint,sort_keys=True,separators=(',',':')).encode())
        cache=base/'.runtime'/'validated_read.json'
        if cache.is_file():
            row=strict_json_load(cache);proof=row.get('integrity_sha256')
            body={k:v for k,v in row.items() if k!='integrity_sha256'}
            if (row.get('schema')=='VOYAGER_VALIDATED_READ_V1' and row.get('key')==key and
                row.get('save_set_id')==manifest.get('save_set_id') and row.get('engine_version')==ENGINE_VERSION and
                proof==sha256_bytes(json.dumps(body,sort_keys=True,separators=(',',':')).encode())):
                ver=parse_version(str(manifest['save_version']))
                index={'version':ver,'save_set_id':manifest['save_set_id'],'parent_save_set_id':manifest.get('parent_save_set_id'),
                       'engine_version':manifest.get('engine_version'),'engine_sha256':(manifest.get('tool_bindings') or {}).get('engine.py'),
                       'save_guard_sha256':(manifest.get('tool_bindings') or {}).get('guard.py'),'hashes':manifest.get('authority_components') or {},
                       'bundle':manifest.get('authority_bundle_sha256') or manifest.get('component_bundle_sha256')}
                return {'base':base,'version':ver,'bundle':index['bundle'],'save_set_id':manifest['save_set_id'],
                        'manifest':manifest.get('authority_components') or {},'index':index,
                        'index_sha256':fingerprint['manifest.json'],'component_manifest':manifest}
    except Exception:pass
    authority=_mobile_validate_authority(base)
    if authority:
        try:
            # Recheck bytes after the semantic pass before publishing the receipt.
            if _read_validation_fingerprint(base,authority['component_manifest'])==fingerprint:
                body={'schema':'VOYAGER_VALIDATED_READ_V1','key':key,'save_set_id':authority['save_set_id'],'engine_version':ENGINE_VERSION}
                body['integrity_sha256']=sha256_bytes(json.dumps(body,sort_keys=True,separators=(',',':')).encode())
                target=base/'.runtime'/'validated_read.json';target.parent.mkdir(parents=True,exist_ok=True)
                _atomic_replace_bytes(target,(json.dumps(body,sort_keys=True,separators=(',',':'))+'\n').encode())
        except Exception:pass
    return authority

def _mobile_stats(base:Path,manifest:dict)->dict:
    names=['manifest.json',*COMPONENT_FILES[1:],*(r['path'] for r in (manifest.get('cold_archives') or {}).values())]
    out={}
    for name in names:
        st=(base/name).stat();out[name]=(st.st_size,st.st_mtime_ns,st.st_ino)
    return out

def _mobile_read_guard(scope:dict)->None:
    if _mobile_stats(scope['base'],scope['manifest'])!=scope['stats']:
        raise EngineError('MOBILE_SOURCE_CHANGED_DURING_READ')

def validate_authority_set(base:Path)->Optional[dict]:
    if _active_runtime_journal(Path(base),'consistency_repair_journal.json'):raise EngineError('CONSISTENCY_REPAIR_RECOVERY_REQUIRED_RUN_GUARD')
    scope=_mobile_read_scope.get()
    if scope and Path(base).resolve()==scope['base']:
        _mobile_read_guard(scope)
        return scope['authority']
    return _cached_mobile_validate_authority(base)

def read_json(path:Path)->Any:
    scope=_mobile_read_scope.get();path=Path(path).resolve()
    if scope and path.parent==scope['base'] and path.name in ('state.json','tasks.json'):
        _mobile_read_guard(scope)
        return copy.deepcopy(scope[path.name])
    return _mobile_read_json(path)

def _mobile_scope_from_authority(base:Path,authority:dict)->dict:
    manifest=authority['component_manifest'];scope={'base':base,'authority':authority,'manifest':manifest,
      'stats':_mobile_stats(base,manifest)}
    scope['state.json']=_mobile_read_json(base/'state.json');scope['tasks.json']=_mobile_read_json(base/'tasks.json')
    _mobile_read_guard(scope)
    return scope

def _mobile_guard_receipt(base:Path)->Optional[dict]:
    raw=os.environ.pop('VOYAGER_GUARD_RECEIPT_FD',None)
    if raw is None:return None
    try:
        fd=int(raw)
        with os.fdopen(fd,'rb') as stream:receipt=json.loads(stream.read(65536))
        if receipt.get('root')!=str(base) or receipt.get('guard_validated') is not True:
            raise EngineError('GUARD_RECEIPT_ROOT_INVALID')
        manifest=_mobile_read_json(base/'manifest.json')
        if sha256_file(base/'manifest.json')!=receipt.get('manifest_sha256') or manifest.get('save_set_id')!=receipt.get('save_set_id'):
            raise EngineError('GUARD_RECEIPT_MANIFEST_CHANGED')
        actual=_mobile_stats(base,manifest)
        if {k:list(v) for k,v in actual.items()}!=receipt.get('stats'):
            raise EngineError('GUARD_RECEIPT_COMPONENT_CHANGED')
        if sha256_file(Path(__file__).resolve())!=(manifest.get('components') or {}).get('engine.py'):
            raise EngineError('GUARD_RECEIPT_ENGINE_CHANGED')
        data=manifest.get('authority_components') or {}
        version=parse_version(str(manifest.get('save_version')))
        index={'version':version,'save_set_id':manifest['save_set_id'],'parent_save_set_id':manifest.get('parent_save_set_id'),
          'engine_version':manifest.get('engine_version'),'engine_sha256':(manifest.get('tool_bindings') or {}).get('engine.py'),
          'save_guard_sha256':(manifest.get('tool_bindings') or {}).get('guard.py'),'hashes':data,
          'bundle':manifest.get('authority_bundle_sha256') or manifest.get('component_bundle_sha256')}
        authority={'base':base,'version':version,'bundle':index['bundle'],'save_set_id':manifest['save_set_id'],
          'manifest':data,'index':index,'index_sha256':receipt['manifest_sha256'],'component_manifest':manifest}
        return {'authority':authority,'selected_source':receipt.get('selected_source') or {},'stats':actual}
    except EngineError:raise
    except Exception as ex:raise EngineError('GUARD_RECEIPT_INVALID:'+type(ex).__name__+':'+str(ex)) from ex

def _query_intent_key(topic:str)->tuple[Optional[str],Optional[str]]:
    q=topic.strip();match=re.fullmatch(r'(task|event|scene):([A-Za-z0-9_.:-]+)',q,re.I)
    if match:return {'task':'task_status','event':'open_event','scene':'current_scene'}[match.group(1).lower()],match.group(2)
    normalized=_normalize_search_text(q)
    if any(x in normalized for x in ('暗反1组当前状态','暗反一组当前状态','暗反1组状态','小行星带巡逻当前状态')):
        return 'patrol_status',_PATROL_TASK_ID
    if normalized in ('当前场景','开放事件','当前开放事件'):
        return ('current_scene' if '场景' in normalized else 'open_event'),_PATROL_TASK_ID
    return _mobile_query_intent_key(topic)

def _mobile_task_packet(base:Path,topic:str,intent:str,task_id:str)->dict:
    ready=ensure_source_ready(base);state=read_json_view(base/'state.json');tasks=read_json_view(base/'tasks.json')
    rows=[t for t in tasks.get('active_tasks',[]) if isinstance(t,dict) and t.get('task_id')==task_id]
    task=rows[0] if len(rows)==1 else None;now=state.get('game_time');refs=['tasks:active_tasks.task_id='+task_id]
    missing=[];value=None;status='NOT_FOUND';event=None
    if not task:missing=['task_id']
    else:
        data=task.get('task_data') or {};event_id=data.get('current_event_id')
        if task_id==_PATROL_TASK_ID:
            dossier=(((state.get('world_state_overrides') or {}).get('intelligence_and_security') or {}).get('xianyue_asteroid_shadow_patrol_current') or {})
            event=dossier.get('current_local_event');refs.append('state:'+_PATROL_SLOT)
            if event is not None and (not isinstance(event,dict) or event.get('event_id')!=event_id or data.get('current_event_stage')!=(authoritative_event_stage(event))):
                missing.append('event_id_or_stage_consistency')
            if event is None and event_id is not None:missing.append('current_local_event')
        elif event_id:missing.append('authoritative_event_slot')
        if intent=='task_status':
            value={'task_id':task_id,'status':task.get('status'),'phase':task.get('phase'),
                   'open_event_id':event_id,'decision_gate_open':_task_player_decision_gate_open(task),
                   'trigger_condition':task.get('trigger_condition'),'as_of':now}
            missing += [k for k in ('status','phase','as_of') if value.get(k) is None]
        elif intent=='patrol_status':
            value={'task_id':task_id,'status':task.get('status'),'phase':task.get('phase'),
                   'event_id':event_id,'event_stage':(authoritative_event_stage(event)) if isinstance(event,dict) else None,
                   'open_event':copy.deepcopy(event),'decision_gate_open':_task_player_decision_gate_open(task),'as_of':now}
            missing += [k for k in ('status','phase','as_of') if value.get(k) is None]
        elif intent in ('open_event','current_scene'):
            if event is None:
                missing.append('current_local_event')
            else:
                value={'task_id':task_id,'event_id':event.get('event_id'),'stage':authoritative_event_stage(event),
                       'event':copy.deepcopy(event),'as_of':now}
                missing += [k for k in ('event_id','stage','as_of') if value.get(k) is None]
        if intent=='open_event' and topic.startswith('event:') and value is not None and topic[6:]!=value['event_id']:
            value=None;missing.append('requested_event_id')
        status='UNKNOWN' if missing and value is not None else ('NOT_FOUND' if value is None else 'COMPLETE')
    return {'packet':'QUERY_INTENT_V5','engine_version':ENGINE_VERSION,'save_set_id':ready['save_set_id'],
      'topic':topic,'intent':intent,'entity_id':task_id,'status':status,'missing_fields':sorted(set(missing)),
      'value':copy.deepcopy(value),'source_refs':refs,'as_of':now,'truncated':False}

def query_intent_packet(base:Path,topic:str)->Optional[dict]:
    intent,arg=_query_intent_key(topic)
    if intent in ('task_status','patrol_status','open_event','current_scene'):
        task_id=arg if intent!='open_event' or not topic.startswith('event:') else _PATROL_TASK_ID
        return _mobile_task_packet(Path(base).resolve(),topic,intent,task_id or _PATROL_TASK_ID)
    old=_mobile_query_intent(base,topic)
    if old:
        exact={'finance':'state:summary.funds','active_tasks':'tasks:active_tasks','queued_tasks':'tasks:queued_tasks',
               'next_event':'engine:routineplan.deterministic_events','decision_gates':'tasks:active_tasks'}
        if old.get('intent') in exact:old['source_refs']=[exact[old['intent']]]
        old['as_of']=old.get('game_time')
    return old

def query_packet(base:Path,topic:str,history_limit:int=5,task_limit:int=5,detail:str="compact")->dict:
    intent=query_intent_packet(base,topic)
    if intent:return intent
    key=_exact_alias_key(topic)
    direct={'gold':'summary.funds.gold','grey':'summary.funds.grey','game_time':'game_time',
            'voyager_ships':'summary.ships.voyager','jinchuan_ships':'summary.ships.jinchuan',
            'shadow_ships':'summary.ships.shadow_active','jinchuan_resource_network':'world_state_overrides.mining_and_industry.jinchuan_resource_network_current',
            'jinchuan_latest_settlement':'jinchuan_fleet.latest_daily_financial_settlement'}
    if key in direct:
        base=Path(base).resolve();ready=ensure_source_ready(base);state=read_json_view(base/'state.json');path=direct[key]
        try:value=get_by_path(state,path);status='COMPLETE';missing=[]
        except KeyError:value=None;status='NOT_FOUND';missing=[path]
        return {'packet':'EXACT_QUERY_V1','status':status,'engine_version':ENGINE_VERSION,'topic':topic,
                'path':path,'value':copy.deepcopy(value),'missing_fields':missing,'source_ref':'state:'+path,
                'as_of':state.get('game_time'),'save_set_id':ready['save_set_id']}
    return _mobile_query_packet(base,topic,history_limit,task_limit,detail)

def _assert_authority_bytes_unchanged(base:Path,authority:dict,scope:dict)->None:
    """Closing read barrier for one already validated manifest and its payloads."""
    manifest=authority['component_manifest']
    if sha256_file(base/'manifest.json')!=authority['index_sha256']:
        raise EngineError('READ_SOURCE_CHANGED:manifest')
    for fn,digest in (manifest.get('components') or {}).items():
        if sha256_file(base/fn)!=digest:raise EngineError('READ_SOURCE_CHANGED:'+fn)
    for rel,row in _component_cold_archives(manifest).items():
        if sha256_file(base/rel)!=row.get('file_sha256'):raise EngineError('READ_SOURCE_CHANGED:'+rel)
    if _mobile_stats(base,manifest)!=scope['stats']:
        raise EngineError('READ_SOURCE_CHANGED:stats')

def query_batch_packet(base,topics,detail='compact'):
    if not isinstance(topics,list) or not 1<=len(topics)<=8 or any(not isinstance(t,str) or not t.strip() for t in topics):
        raise EngineError('QUERY_BATCH_REQUIRES_1_TO_8_TOPICS')
    base=Path(base).resolve()
    with engine_lock(base,exclusive=True):
        before=_cached_mobile_validate_authority(base)
        if not before:raise EngineError('COMPONENT_AUTHORITY_INVALID')
        scope=_mobile_scope_from_authority(base,before);token=_mobile_read_scope.set(scope)
        try:
            results=[query_packet(base,t,detail=detail) for t in topics]
            _mobile_read_guard(scope)
        finally:_mobile_read_scope.reset(token)
        _assert_authority_bytes_unchanged(base,before,scope)
        return {'packet':'QUERY_BATCH_V2','save_set_id':before['save_set_id'],'results':results,'source_checks':2}

def _component_transport_sync_status(current_save_set_id,component_root=None,honor_transport_env=True):
    scope=_mobile_read_scope.get()
    if scope and scope.get('selected_source') is not None:
        selected=scope['selected_source']
        return {'status':'LOCAL_SOURCE_SELECTED','current_save_set_id':current_save_set_id,
                'selected_source':selected,'local_sync':selected.get('local_sync'),'project_upload_verified':False}
    return _mobile_source_sync(current_save_set_id,component_root,honor_transport_env)

def _mobile_resume_cursor(state:dict,tasks:dict,decisions:list,base:Path)->dict:
    active=[t for t in tasks.get('active_tasks',[]) if isinstance(t,dict) and t.get('task_id')]
    by_id={t['task_id']:t for t in active};runtime=state.get('engine_runtime') or {};pending=runtime.get('pending_turn') or {}
    explicit=runtime.get('resume_focus') or {};focus_id=explicit.get('task_id') or pending.get('task_id')
    if not focus_id and len(decisions)==1:focus_id=decisions[0].get('task_id')
    task=by_id.get(focus_id);cursor={'status':'NO_FOCUS','task_id':None,'event_id':None,'phase':None,
                                    'last_reported_seq':runtime.get('last_reported_seq'),'pending_gate':None}
    with (base/'events.jsonl').open('rb') as history:meta=json.loads(history.readline())
    last=cursor['last_reported_seq']
    if not isinstance(last,int) or not 0<=last<int(meta.get('next_seq') or 1):cursor['last_reported_seq']=None
    if task:
        cursor.update(status='FOCUSED',task_id=focus_id,phase=task.get('phase'))
        if focus_id==_PATROL_TASK_ID:
            dossier=(((state.get('world_state_overrides') or {}).get('intelligence_and_security') or {}).get('xianyue_asteroid_shadow_patrol_current') or {})
            event=dossier.get('current_local_event');ref=(task.get('task_data') or {}).get('current_event_id')
            if event is None and ref is None:pass
            elif isinstance(event,dict) and event.get('event_id')==ref and 'closed' not in str(event.get('status')).lower():cursor['event_id']=ref
            else:cursor.update(status='INVALIDATED',event_id=None)
        gate=next((d for d in decisions if d.get('task_id')==focus_id),None)
        if gate:cursor['pending_gate']={'task_id':focus_id,'status':gate.get('status')}
    else:
        cursor['candidates']=[{'task_id':t['task_id'],'phase':t.get('phase')} for t in active[:3]]
    return cursor

def cold_start_packet_v1408(base:Path=ROOT)->dict:
    base=Path(base).resolve();receipt=_mobile_guard_receipt(base)
    authority=_cached_mobile_validate_authority(base)
    if not authority:raise EngineError('COMPONENT_AUTHORITY_INVALID')
    scope=_mobile_scope_from_authority(base,authority)
    scope['selected_source']=(receipt['selected_source'] if receipt else {'kind':'directory','path':str(base),'local_sync':'current_directory'})
    token=_mobile_read_scope.set(scope)
    try:
        packet=_mobile_cold_start(base);state=scope['state.json'];tasks=scope['tasks.json']
        packet['resume_cursor']=_mobile_resume_cursor(state,tasks,packet.get('pending_decisions') or [],base)
        packet['selected_source']=scope['selected_source'];packet['local_sync']=scope['selected_source'].get('local_sync')
        packet['project_upload_verified']=False
        packet['command_contract']={'invoke':'engine.py invoke --input <JSON>','catalog':'engine.py commandcatalog','legacy_alias':'domaincommand','verified_grant_required':True}
        # Candidates are an optional navigation hint. Keep required decisions,
        # recovery facts and restrictions in full even if the requested budget
        # is small; subsequent layers are paged explicitly.
        packet['context_bytes']=len(json.dumps(packet,ensure_ascii=False,separators=(',',':')).encode())
        packet['context_budget_bytes']=4096
        packet['budget_exceeded']=packet['context_bytes']>4096
        _mobile_read_guard(scope)
    finally:_mobile_read_scope.reset(token)
    # The opening validation checked semantics; the closing barrier verifies bytes
    # against the same manifest, with no second deep validation pass.
    _assert_authority_bytes_unchanged(base,authority,scope)
    return packet

def _mobile_handoff(root:Path,save_set_id:str,package:Optional[dict]=None)->dict:
    package=package or _component_package(root);zip_path=Path(package['path'])
    if package['save_set_id']!=save_set_id:raise EngineError('HANDOFF_SAVESET_MISMATCH')
    zip_check=_component_zip_check(zip_path)
    if zip_check.get('status')!='PASS':raise EngineError('HANDOFF_ZIP_INVALID:'+str(zip_check.get('errors')))
    guard_name='guard_'+str(_component_manifest_read(root)['save_version'])+'.py';external=zip_path.parent/guard_name
    _native_durable_copy(root/'guard.py',external)
    with tempfile.TemporaryDirectory(prefix='voyager_commit_handoff_') as td:
        cold=Path(td);shutil.copy2(zip_path,cold/zip_path.name);shutil.copy2(external,cold/guard_name)
        env=os.environ.copy();env['VOYAGER_ROOT']=str(cold)
        env.pop('VOYAGER_TRANSPORT_PATH',None);env.pop('VOYAGER_GUARD_RECEIPT_FD',None)
        cp=subprocess.run([sys.executable,str(cold/guard_name),'--resume'],cwd=cold,env=env,text=True,capture_output=True,timeout=90)
        try:boot=json.loads(cp.stdout)
        except Exception:boot={}
        if cp.returncode or boot.get('save_set_id')!=save_set_id or boot.get('packet')!=COLD_START_PACKET_SCHEMA:
            raise EngineError('HANDOFF_COLD_BOOT_FAILED:'+str(cp.stderr[-300:])+str(cp.stdout[-300:]))
    journal=_native_commit_journal_path(root)
    if journal.is_file():
        record=strict_json_load(journal);parent=(root/str(record.get('parent_snapshot') or '')).resolve()
        if record.get('target_save_set_id')!=save_set_id or (root/'.runtime'/'snapshots').resolve() not in parent.parents:
            raise EngineError('HANDOFF_COMMIT_JOURNAL_MISMATCH')
        pm=strict_json_load(parent/'manifest.json')
        if pm.get('save_set_id')!=record.get('parent_save_set_id'):
            raise EngineError('HANDOFF_PARENT_SNAPSHOT_ID_INVALID')
        for name,digest in (pm.get('components') or {}).items():
            if not (parent/name).is_file() or sha256_file(parent/name)!=digest:
                raise EngineError('HANDOFF_PARENT_SNAPSHOT_INVALID:'+name)
        for rel,rec in _component_cold_archives(pm).items():
            if not (parent/rel).is_file() or sha256_file(parent/rel)!=rec.get('file_sha256'):
                raise EngineError('HANDOFF_PARENT_ARCHIVE_INVALID:'+rel)
        if component_source_check(root,strict_fileset=False).get('status')!='PASS':
            raise EngineError('HANDOFF_COMMIT_TARGET_INVALID')
        _native_clear_journal(journal)
    return {'status':'READY','save_set_id':save_set_id,'zip':str(zip_path),'guard':str(external),
            'sha256':package['sha256'],'cold_boot':'PASS'}

def _native_atomic_save_unlocked(staging:Path,version:str,scope:str,root:Path=ROOT,make_export:bool=False,make_project:bool=False,**kwargs)->dict:
    return _mobile_atomic_save(staging,version,scope,root,False,False,**kwargs)


def export_save_set(root:Path,save_set_id:str)->dict:
    """Freeze one committed SAVESET under the transaction lock before transport work."""
    root=Path(root).resolve()
    if not save_set_id:raise EngineError('EXPORT_SAVESET_REQUIRED')
    frozen=None;package=None
    try:
        with engine_lock(root,exclusive=True):
            current=component_source_check(root,strict_fileset=False)
            source=root if current.get('status')=='PASS' and current.get('save_set_id')==save_set_id else _native_snapshot_dir(root,save_set_id)
            check=_native_historical_source_check(source,root/'guard.py')
            if check.get('status')!='PASS' or check.get('save_set_id')!=save_set_id:
                raise EngineError('EXPORT_SAVESET_UNAVAILABLE:'+save_set_id)
            frozen=Path(tempfile.mkdtemp(prefix='voyager_export_frozen_'))
            manifest=_component_manifest_read(source)
            for fn in COMPONENT_FILES:_native_durable_copy(source/fn,frozen/fn)
            _copy_declared_cold_archives(source,frozen,manifest)
            for rel,digest in _development_source_files(manifest).items():
                candidates=[source/rel,root/rel]
                src=next((p for p in candidates if p.is_file() and not p.is_symlink() and sha256_file(p)==digest),None)
                if src is None:raise EngineError('EXPORT_FROZEN_DEVELOPMENT_MISSING:'+rel)
                dest=frozen/rel;dest.parent.mkdir(parents=True,exist_ok=True);_native_durable_copy(src,dest)
        if _native_historical_source_check(frozen,root/'guard.py').get('status')!='PASS':raise EngineError('EXPORT_FROZEN_SOURCE_INVALID')
        _native_test_failpoint('export')
        delivery=Path(os.environ.get(_COMPONENT_DELIVERY_ROOT_ENV,str(root.parent))).resolve()
        package=_component_package(frozen,delivery)
        handoff=_mobile_handoff(frozen,save_set_id,package)
        return {'status':'READY','committed':True,'save_set_id':save_set_id,'export_status':'VERIFIED',
                'package_generated':True,'package_verified':True,'external_persistence_confirmed':False,
                'path':package['path'],'sha256':package['sha256'],'cold_boot':handoff['cold_boot'],'retry_action':None}
    except Exception as ex:
        return {'status':'EXPORT_FAILED','committed':True,'save_set_id':save_set_id,'export_status':'FAILED',
                'package_generated':bool(package),'package_verified':False,'external_persistence_confirmed':False,
                'path':package.get('path') if package else None,
                'error':f'{type(ex).__name__}:{ex}','retry_action':'export_only'}
    finally:
        if frozen:shutil.rmtree(frozen,ignore_errors=True)

# === V14.09 scene lifecycle, visibility, and layered cold start ===
SCENE_REGISTRY_SCHEMA='SCENE_REGISTRY_V1'
SCENE_PHASES={'proposed','open','investigating','resolved','closed'}
SCENE_TRANSITIONS={'proposed':{'open'},'open':{'investigating','resolved'},'investigating':{'resolved'},'resolved':{'closed'},'closed':set()}
SCENE_PATROL_PATH='world_state_overrides.intelligence_and_security.xianyue_asteroid_shadow_patrol_current'
SCENE_ID_RE=re.compile(r'^[A-Za-z0-9_.:-]{1,160}$')

