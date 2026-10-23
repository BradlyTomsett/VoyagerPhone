# === VOYAGER_DEV_MODULE: reliable_runtime ===
# Batch A: exact diagnostic layers, evidence-bound temporal coverage and host intents.
READINESS_SCHEMA='VOYAGER_READINESS_V1'
_host_intent_scope=contextvars.ContextVar('voyager_host_intent_scope',default=None)
_readiness_scope=contextvars.ContextVar('voyager_readiness_scope',default=False)


def _risk_clock_gap_valid(state,cid,clock):
    now=parse_iso(state.get('game_time'));last=parse_iso(clock.get('last_evaluated'))
    if now is None or last is None:return False
    if last==now:return True
    er=state.get('engine_runtime') or {};gaps=er.get('risk_gap_registry_v1') or {}
    row=gaps.get(clock.get('evaluation_epoch_id'))
    if not isinstance(row,dict) or row.get('schema')!='RISK_GAP_WINDOW_V1' or row.get('status')!='acknowledged_unsimulated':return False
    if row.get('policy')!='preserve_no_replay_resume_at_end' or not row.get('decision_evidence_ref'):return False
    prior=(row.get('clocks') or {}).get(cid)
    if not isinstance(prior,dict) or row.get('end')!=state.get('game_time') or clock.get('evaluation_cursor')!=row['end']:return False
    if prior.get('last_evaluated')!=clock.get('last_evaluated') or row.get('start')!=clock.get('last_evaluated'):return False
    for key in ('cycle','cumulative_hazard','cumulative_hazard_numerator','risk_multiplier','cooldown_until','profile_id'):
        if prior.get(key)!=clock.get(key):return False
    return row.get('seed_sha256')==_repair_digest(er.get('seed_anchor'))


def _risk_window_report(state):
    clocks=((state.get('engine_runtime') or {}).get('long_horizon') or {}).get('hazard_clocks')
    if not isinstance(clocks,dict):return {'status':'FAIL','errors':['HAZARD_CLOCKS_MISSING'],'acknowledged_gaps':[]}
    errors=[];covered=[]
    for cid,c in clocks.items():
        if not isinstance(c,dict) or not _risk_clock_gap_valid(state,cid,c):errors.append('UNCOVERED_CLOCK:'+cid)
        elif c.get('last_evaluated')!=state.get('game_time'):covered.append(cid)
    gaps=state.get('engine_runtime',{}).get('risk_gap_registry_v1') or {}
    return {'status':'FAIL' if errors else 'PASS_WITH_GAPS' if gaps else 'PASS','errors':errors,
            'acknowledged_gaps':[{'gap_id':gid,'start':g.get('start'),'end':g.get('end'),'status':g.get('status'),'policy':g.get('policy')} for gid,g in gaps.items()],
            'coverage':'current cursor validated; acknowledged historical windows were not simulated','clock_count':len(clocks)}


def _location_coverage_valid(state):
    loc=state.get('shadow_fleet',{}).get('current_location') or {};sem=loc.get('time_semantics') or {}
    return (sem.get('schema')=='LOCATION_TIME_SEMANTICS_V1' and sem.get('observed_at')==loc.get('as_of') and
            sem.get('verified_through')==state.get('game_time') and bool(sem.get('source_event_ids')) and
            sem.get('basis')=='accepted_continuation_explicit_no_redeployment' and
            parse_iso(sem.get('observed_at')) is not None and parse_iso(sem.get('observed_at'))<=parse_iso(state['game_time']))


def _active_runtime_journal(base,name):
    if not (Path(base)/'.runtime'/name).exists():return False
    return _repair_guard_module(Path(base)).active_journal(Path(base),name)


def readiness_report(base:Path=ROOT)->dict:
    """Read-only diagnostic; never equates byte integrity with executable readiness."""
    base=Path(base).resolve();layers={};errors=[];manifest={};state={};tasks={}
    try:start_fingerprint=_read_validation_fingerprint(base,strict_json_load(base/'manifest.json'))
    except Exception:start_fingerprint=None
    ctx=_stage2_tx_scope.get()
    try:reuse=ctx.readiness_reuse(base) if ctx is not None else None
    except Exception:reuse=None
    reused_layers=(reuse or {}).get('layers',{})
    recovery=[]
    for name in (NATIVE_COMMIT_JOURNAL_FILENAME,CONSISTENCY_REPAIR_JOURNAL):
        try:
            if _active_runtime_journal(base,name):recovery.append(name)
        except Exception as ex:recovery.append(name+':'+str(ex))
    layers['recovery']={'status':'FAIL' if recovery else 'PASS','errors':['RECOVERY_REQUIRED'] if recovery else []}
    try:
        manifest=strict_json_load(base/'manifest.json')
        g=_repair_guard_module(base);bound,errs=g.validate_dir(base,strict=False)
        if bound and (base/'development').exists() and not g.development_intact(base,manifest):errs.append('DEVELOPMENT_BINDING')
        layers['integrity']={'status':'FAIL' if errs else 'PASS','errors':errs,'checks':['component/tool hashes','protocol binding','cold file hashes','materialized development hashes']}
    except Exception as ex:layers['integrity']={'status':'FAIL','errors':['INTEGRITY:'+str(ex)]}
    try:
        if 'history' in reused_layers:layers['history']=copy.deepcopy(reused_layers['history'])
        else:
            meta,events,_=read_history_view(base/'events.jsonl')
            ids=[e.get('event_id') for e in events]
            if len(set(ids))!=len(ids) or not all(isinstance(x,str) and x for x in ids):raise EngineError('HISTORY_EVENT_ID_INVALID')
            layers['history']={'status':'PASS','errors':[],'logical_events':len(events),'next_seq':meta['next_seq'],'checks':['logical continuity','epoch payloads','unique event IDs','metadata tail']}
    except Exception as ex:layers['history']={'status':'FAIL','errors':[str(ex)]}
    try:
        state=strict_json_load(base/'state.json');tasks=strict_json_load(base/'tasks.json')
        cc=copy.deepcopy(reused_layers['current_consistency']) if 'current_consistency' in reused_layers else _current_authority_consistency_report(base);scene={'errors':[]} if 'current_consistency' in reused_layers else _scene_integrity_report(state,tasks)
        errs=list(cc.get('errors') or [])+list(scene.get('errors') or [])
        if state.get('game_time')!=tasks.get('game_time') or state.get('game_time')!=manifest.get('game_time'):errs.append('CURRENT_TIME_MISMATCH')
        if state.get('shadow_fleet',{}).get('current_location',{}).get('as_of')!=state.get('game_time') and not _location_coverage_valid(state):errs.append('LOCATION_TIME_UNCOVERED')
        layers['current_consistency']={'status':'FAIL' if errs else 'PASS','errors':errs}
        layers['runtime_clock']=copy.deepcopy(reused_layers['runtime_clock']) if 'runtime_clock' in reused_layers else _risk_window_report(state)
    except Exception as ex:
        layers['current_consistency']={'status':'FAIL','errors':[str(ex)]};layers['runtime_clock']={'status':'NOT_RUN','errors':[]}
    # Source check catches executable rules/reference/domain invariants outside the above layers.
    if layers['integrity']['status']=='PASS' and layers['history']['status']=='PASS':
        try:
            cc=reuse['source_contract'] if reuse is not None and reuse.get('source_contract') is not None else component_source_check(base,strict_fileset=False)
            layers['source_contract']={'status':cc['status'],'errors':cc.get('errors',[])}
        except Exception as ex:layers['source_contract']={'status':'FAIL','errors':[str(ex)]}
    else:layers['source_contract']={'status':'NOT_RUN','errors':[]}
    if state:
        for name,check in [('accounts',lambda:accounts_integrity_report(state)),('content',lambda:content_integrity_report(base)),('memory',lambda:memory_integrity_report(base)),('story',lambda:_story_source_report(base))]:
            try:layers[name]=copy.deepcopy(reused_layers[name]) if name in reused_layers else check()
            except Exception as ex:layers[name]={'status':'FAIL','errors':[str(ex)]}
        try:
            layers['business']=copy.deepcopy(reused_layers['business']) if 'business' in reused_layers else business_integrity_report(state,tasks,base)
            if 'execution_coverage' in reused_layers:layers['execution_coverage']=copy.deepcopy(reused_layers['execution_coverage'])
            else:
                coverage=_scheduler_coverage(state,tasks,manifest.get('save_set_id'))
                layers['execution_coverage']={'status':'PASS_WITH_LIMITATIONS' if coverage['status']=='ACTION_REQUIRED' else 'PASS','errors':[],'coverage_status':coverage['status'],'next_blocker':coverage['next_blocker'],'can_advance_through_24h':coverage['can_advance_through_24h']}
        except Exception as ex:layers['business']={'status':'FAIL','errors':[str(ex)]}
    for layer,row in layers.items():errors.extend(layer+':'+str(e) for e in row.get('errors',[]))
    try:end_fingerprint=_read_validation_fingerprint(base,strict_json_load(base/'manifest.json'))
    except Exception:end_fingerprint=None
    if start_fingerprint!=end_fingerprint:
        layers['snapshot_stability']={'status':'FAIL','errors':['SOURCE_CHANGED_DURING_READINESS']};errors.append('snapshot_stability:SOURCE_CHANGED_DURING_READINESS')
    blocked=any(r['status'] in ('FAIL','NOT_RUN') for r in layers.values())
    status='BLOCKED' if blocked else ('READY_WITH_LIMITATIONS' if layers['runtime_clock']['status']=='PASS_WITH_GAPS' or layers.get('execution_coverage',{}).get('status')=='PASS_WITH_LIMITATIONS' else 'READY')
    capabilities={'read':not blocked,'typed_write':not blocked,'advance':not blocked,'advance_requires_barrier_handling':layers.get('execution_coverage',{}).get('coverage_status')=='ACTION_REQUIRED','original_images':'requires external original ZIP','authorization':'trusted host intent or verified standing grant'}
    layers['capabilities']={'status':'PASS' if not blocked else 'BLOCKED','value':capabilities,'errors':[]}
    return {'schema':READINESS_SCHEMA,'status':status,'save_set_id':manifest.get('save_set_id'),'game_time':state.get('game_time'),
            'validator_version':ENGINE_VERSION,'authority_digest':manifest.get('authority_bundle_sha256'),
            'coverage':'integrity + history + current contracts + clock coverage + recovery; full release audit is separate',
            'layers':layers,'capabilities':capabilities,'errors':errors}


def _reliable_ensure_source_ready(base:Path,allow_cache:bool=True)->dict:
    report=readiness_report(base)
    if report['status']=='BLOCKED':raise EngineError('READINESS_BLOCKED:'+json.dumps(report,ensure_ascii=False,separators=(',',':')))
    return _batch_a_ensure_ready(base,allow_cache)


def _reliable_cold_start_packet(base:Path=ROOT)->dict:
    report=readiness_report(base)
    if report['status']=='BLOCKED':return {'packet':COLD_START_PACKET_SCHEMA,'readiness':report,'save_set_id':report['save_set_id'],'game_time':report['game_time'],'current_scene':None,'next_layers':[]}
    packet=_batch_a_cold_start(base);packet['readiness']=report
    packet['context_bytes']=len(json.dumps(packet,ensure_ascii=False,separators=(',',':')).encode())
    packet['budget_exceeded']=packet['context_bytes']>packet.get('context_budget_bytes',4096)
    return packet


def _reliable_query_packet(base:Path,topic:str,history_limit:int=5,task_limit:int=5,detail:str='compact')->dict:
    report=readiness_report(base)
    if report['status']=='BLOCKED':return {'packet':'QUERY_RESULT_V1','status':'BLOCKED','topic':topic,'readiness':report,'value':None}
    packet=_batch_a_query(base,topic,history_limit,task_limit,detail);packet['readiness']=report
    return packet


def _handoff_projection(state,tasks,save_set_id):
    old=copy.deepcopy((state.get('world_state_overrides') or {}).get('current_handoff_snapshot') or {})
    old.update(projection_schema='CURRENT_HANDOFF_PROJECTION_V1',projection_only=True,save_set_id=save_set_id,
               game_time=state.get('game_time'),as_of=state.get('game_time'),ships=copy.deepcopy(state['summary']['ships']),
               personnel=copy.deepcopy(state['summary']['personnel']),active_tasks_count=len(tasks.get('active_tasks',[])),queued_tasks_count=len(tasks.get('queued_tasks',[])))
    funds=state['engine_runtime']['finance_runtime']['funds_units']
    old.setdefault('funds',{}).update(main_gold=_price_text(Decimal(funds['gold'])/10000),main_grey=_price_text(Decimal(funds['grey'])/10000))
    old['authority_refs']={'funds':'state:engine_runtime.finance_runtime.funds_units','ships':'state:summary.ships','personnel':'state:summary.personnel','location':'state:shadow_fleet.current_location','tasks':'tasks:active_tasks'}
    return old


def _reliable_write_authority_json(path:Path,obj:Any)->None:
    # Current mirrors are output projections, rebuilt at the write boundary.
    path=Path(path)
    if path.name=='state.json' and isinstance(obj,dict) and obj.get('engine_runtime',{}).get('authority_map_v1'):
        tasks=strict_json_load(path.parent/'tasks.json')
        obj=copy.deepcopy(obj)
        # Bind to the logical version, avoiding a circular dependency on state SHA.
        old=obj['world_state_overrides'].get('current_handoff_snapshot') or {}
        obj['world_state_overrides']['current_handoff_snapshot']=_handoff_projection(obj,tasks,old.get('save_set_id'))
    _batch_a_write_json(path,obj)


def _reliable_component_write_manifest_native(root:Path,save_version:str,parent_sid:Optional[str],migration_lineage:Optional[dict]=None,frozen_development_sources:Optional[dict]=None)->dict:
    # Projection binds to parent authority plus new save version; storing its own
    # final SAVESET would introduce a hash cycle. Readers expose current sid.
    return _batch_a_manifest(root,save_version,parent_sid,migration_lineage,frozen_development_sources)


def _reliable_phase2_domain_authorization(state:dict,payload:dict,consume:bool=False)->dict:
    if payload.get('authorization')!='host_intent':return _batch_a_auth(state,payload,consume)
    env=_host_intent_scope.get()
    if not isinstance(env,dict) or env.get('schema')!='HOST_COMMAND_INTENT_V1':raise EngineError('HOST_INTENT_TRUSTED_BOUNDARY_REQUIRED')
    command=env.get('command')
    if command!=payload or env.get('decision')!='approved':raise EngineError('HOST_INTENT_COMMAND_MISMATCH')
    if env.get('subject_id')!=payload.get('actor_id'):raise EngineError('HOST_INTENT_SUBJECT_MISMATCH')
    if env.get('parent_save_set_id')!=payload.get('base_save_set_id'):raise EngineError('HOST_INTENT_PARENT_MISMATCH')
    if not isinstance(env.get('instruction_text'),str) or not env['instruction_text'].strip() or not env.get('evidence_ref'):raise EngineError('HOST_INTENT_USER_EVIDENCE_REQUIRED')
    now=parse_iso(state.get('game_time'));lo=parse_iso(env.get('valid_from'));hi=parse_iso(env.get('valid_until'))
    if now is None or lo is None or hi is None or not lo<=now<=hi:raise EngineError('HOST_INTENT_EXPIRED')
    if env.get('targets')!=_domain_command_targets(payload):raise EngineError('HOST_INTENT_TARGET_MISMATCH')
    cost=_domain_authorization_cost(payload)
    for key in ('uses','gold_units','grey_units','quantity'):
        limit=env.get('limits',{}).get(key)
        if isinstance(limit,bool) or not isinstance(limit,(str,int)) or _price_decimal(limit)<0 or _price_decimal(cost[key])>_price_decimal(limit):raise EngineError('HOST_INTENT_LIMIT_EXCEEDED:'+key)
    return {'schema':DOMAIN_AUTHORIZATION_SCHEMA,'status':'verified','authority':'host_intent','subject_id':payload['actor_id'],
            'authorization_ref':payload['authorization_ref'],'targets':env['targets'],'cost':cost,
            'evidence_ref':env['evidence_ref'],'instruction_sha256':sha256_bytes(env['instruction_text'].encode()),'decision_sha256':_repair_digest(env),'user_intent':copy.deepcopy(env)}


def host_intent_command(base:Path,envelope:dict,version:Optional[str],dry_run=False)->dict:
    # This API is host-only, not an ordinary invoke payload. The CLI reads its
    # envelope from an inherited pipe created by the human interaction gateway.
    token=_host_intent_scope.set(copy.deepcopy(envelope))
    try:return domain_command_packet(base,envelope['command'],version,'verified host user intent',dry_run)
    finally:_host_intent_scope.reset(token)


def _reliable_domain_command_catalog(base:Path=ROOT)->dict:
    packet=_batch_a_catalog(base);state=read_json(Path(base)/'state.json')
    packet['authorization_bridge']={'entry':'development/interaction_gateway.py','boundary':'human TTY or authenticated embedding host API; ordinary model payload cannot approve itself','host_api':'host_intent_command'}
    grants=[g for g in state.get('standing_authorizations',{}).values() if g.get('status')=='active' and g.get('machine_grant')]
    for row in packet.get('kinds',{}).values():row['availability']='needs_authorization' if not grants else 'requires_scope_check'
    return packet


def _native_make_commit_journal(root,stage,current,target_manifest,snapshot,engine_upgrade=False):
    """Freeze complete declared target before publishing the durable intent."""
    token=uuid.uuid4().hex;home=root/'.runtime'/'transactions'/token;target=home/'target'
    _repair_snapshot_copy(stage,target,target_manifest)
    # Staging intentionally has no development tree; freeze it from the bound
    # active root (or explicit candidate directory) before any write to authority.
    dev=target_manifest.get('development_sources') or {};files=dev.get('files') or {}
    candidates=[stage,Path(os.environ.get('VOYAGER_DEV_SOURCE_DIR',str(root))),root]
    for rel,digest in files.items():
        dest=target/rel
        if dest.is_file() and sha256_file(dest)==digest:continue
        src=next((base/rel for base in candidates if (base/rel).is_file() and sha256_file(base/rel)==digest),None)
        if src is None:raise EngineError('TRANSACTION_FROZEN_SOURCE_MISSING:'+rel)
        dest.parent.mkdir(parents=True,exist_ok=True);_native_durable_copy(src,dest)
    names=['manifest.json',*COMPONENT_DATA_FILES,'engine.py','guard.py']
    j={'schema':'VOYAGER_NATIVE_COMMIT_JOURNAL_V2','status':'PREPARED','transaction_id':token,'root':str(root),
       'parent_save_set_id':current['save_set_id'],'target_save_set_id':target_manifest['save_set_id'],
       'parent_snapshot':str(snapshot.relative_to(root)),'target_snapshot':str(target.relative_to(root)),
       'parent_hashes':{n:sha256_file(snapshot/n) for n in names},'target_hashes':{n:sha256_file(target/n) for n in names},'engine_upgrade':engine_upgrade}
    _native_atomic_json(_native_commit_journal_path(root),j)
    return j


def _reliable_native_recover_interrupted_commit(root:Path)->Optional[dict]:
    root=Path(root).resolve()
    if not _native_commit_journal_path(root).is_file():return None
    module=_repair_guard_module(root);manifest,errors=module.recover_interrupted_commit(root)
    if errors:raise EngineError('COMMIT_RECOVERY_FAILED:'+','.join(errors))
    return {'status':'RECOVERED','save_set_id':manifest['save_set_id']}


def _reliable_main(argv:Optional[List[str]]=None)->int:
    args=list(sys.argv[1:] if argv is None else argv)
    try:
        if args and args[0]=='readiness':
            p=argparse.ArgumentParser();p.add_argument('--base',default=str(ROOT));ns=p.parse_args(args[1:]);out=readiness_report(Path(ns.base));print(json.dumps(out,ensure_ascii=False));return 1 if out['status']=='BLOCKED' else 0
        if args and args[0]=='query':
            p=argparse.ArgumentParser();p.add_argument('topic');p.add_argument('--base',default=str(ROOT));p.add_argument('--history-limit',type=int,default=5);p.add_argument('--detail',default='compact');p.add_argument('--audience',default='player');p.add_argument('--observer-id');p.add_argument('--gm-context');ns=p.parse_args(args[1:])
            report=readiness_report(Path(ns.base))
            out={'status':'BLOCKED'} if report['status']=='BLOCKED' else visible_query_packet(Path(ns.base),ns.topic,ns.history_limit,ns.detail,ns.audience,ns.observer_id,ns.gm_context)
            out['readiness']=report;print(json.dumps(out,ensure_ascii=False));return 1 if report['status']=='BLOCKED' else 0
        if args and args[0]=='hostinvoke':
            p=argparse.ArgumentParser();p.add_argument('--intent-fd',type=int,required=True);p.add_argument('--version');p.add_argument('--dry-run',action='store_true');ns=p.parse_args(args[1:])
            if not stat.S_ISFIFO(os.fstat(ns.intent_fd).st_mode):raise EngineError('HOST_INTENT_INHERITED_PIPE_REQUIRED')
            with os.fdopen(ns.intent_fd,'rb') as stream:env=json.loads(stream.read(262144))
            # Local gateway key is outside game authority and outside exported ZIPs.
            # This boundary protects ordinary invoke payloads, not hostile code
            # running with the operator's filesystem permissions.
            import hmac
            proof=env.pop('_gateway_proof',None);keypath=ROOT/'.runtime'/'host_gateway.key'
            if not isinstance(proof,str) or not keypath.is_file() or keypath.is_symlink():raise EngineError('HOST_INTENT_GATEWAY_SIGNATURE_REQUIRED')
            expected=hmac.new(keypath.read_bytes(),json.dumps(env,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode(),'sha256').hexdigest()
            if not hmac.compare_digest(proof,expected) or abs(time.time()-env.get('received_at_unix',0))>300:raise EngineError('HOST_INTENT_GATEWAY_SIGNATURE_INVALID_OR_EXPIRED')
            gateway=ROOT/'development'/'interaction_gateway.py';manifest=strict_json_load(ROOT/'manifest.json')
            if sha256_file(gateway)!=(manifest.get('development_sources',{}).get('files') or {}).get('development/interaction_gateway.py'):raise EngineError('HOST_INTENT_GATEWAY_BINDING')
            out=host_intent_command(ROOT,env,ns.version,ns.dry_run);print(json.dumps(out,ensure_ascii=False));return 0
        if args and args[0] in ('boot','startup'):
            # Structured block report is available even when ordinary loading fails.
            base=Path(args[args.index('--base')+1]) if '--base' in args else ROOT
            report=readiness_report(base)
            if report['status']=='BLOCKED':print(json.dumps({'status':'BLOCKED','readiness':report},ensure_ascii=False));return 1
        return _batch_a_main(args)
    except Exception as ex:
        print(json.dumps({'status':'FAIL','error':str(ex)},ensure_ascii=False));return 1

# Publish service interfaces once; retain explicit captured previous contracts.
ensure_source_ready=_reliable_ensure_source_ready
cold_start_packet=_reliable_cold_start_packet
query_packet=_reliable_query_packet
_write_authority_json=_reliable_write_authority_json
_component_write_manifest_native=_reliable_component_write_manifest_native
_phase2_domain_authorization=_reliable_phase2_domain_authorization
domain_command_catalog=_reliable_domain_command_catalog
_native_recover_interrupted_commit=_reliable_native_recover_interrupted_commit
main=_reliable_main

# Immutable captures for the Batch B service adapters.
_batch_b_strict_json=strict_json_load
_batch_b_sha_file=sha256_file
_batch_b_readiness=readiness_report
_batch_b_validate_authority=validate_authority_set
_batch_b_history_read=_history_read_verified
_batch_b_epoch_decode=_decode_history_epoch_record
_batch_b_run_checks=run_checks
_batch_b_query_packet=query_packet
_batch_b_query_batch=query_batch_packet
