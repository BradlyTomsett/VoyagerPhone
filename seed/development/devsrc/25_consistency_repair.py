# === VOYAGER_DEV_MODULE: consistency_repair ===
# Explicit, evidence-only repair. No gameplay command, arbitrary patch or authorization.
CONSISTENCY_REPAIR_SCHEMA='VOYAGER_CONSISTENCY_REPAIR_PLAN_V1'
CONSISTENCY_REPAIR_JOURNAL='consistency_repair_journal.json'
_consistency_previous_main=main


def _repair_digest(obj)->str:
    return sha256_bytes(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())


def _repair_tokens(path:str)->list:
    if not path.startswith('/'):raise EngineError('REPAIR_POINTER_REQUIRED')
    return [part.replace('~1','/').replace('~0','~') for part in path[1:].split('/')]


def _repair_pointer(parts)->str:
    return '/'+'/'.join(str(p).replace('~','~0').replace('/','~1') for p in parts)


def _repair_get(doc,path):
    value=doc
    for part in _repair_tokens(path):value=value[int(part)] if isinstance(value,list) else value[part]
    return value


def _repair_set(doc,path,value):
    parts=_repair_tokens(path);parent=doc
    for part in parts[:-1]:parent=parent[int(part)] if isinstance(parent,list) else parent[part]
    key=int(parts[-1]) if isinstance(parent,list) else parts[-1]
    if isinstance(parent,dict) and key not in parent:raise EngineError('REPAIR_CANNOT_CREATE_AUTHORITY_FIELD')
    parent[key]=copy.deepcopy(value)


def _repair_guard_module(base:Path):
    gp=base/'guard.py'
    raw=gp.read_bytes()
    if sha256_bytes(raw)!=BUNDLED_GUARD_SHA256:raise EngineError('REPAIR_GUARD_HASH_BINDING')
    spec=importlib.util.spec_from_file_location('voyager_repair_guard_'+uuid.uuid4().hex,gp)
    module=importlib.util.module_from_spec(spec)
    # Execute exactly the verified Guard source, never an unrelated/stale pyc.
    # Compilation here is an independent load boundary, not an engine PASS.
    exec(compile(raw,str(gp),'exec',dont_inherit=True),module.__dict__)
    if module.GUARD_VERSION!=BUNDLED_GUARD_VERSION or module.GUARD_PROTOCOL!=GUARD_PROTOCOL:
        raise EngineError('REPAIR_GUARD_PROTOCOL_BINDING')
    return module


def _repair_fingerprint(base:Path,manifest:dict)->dict:
    names={'manifest.json',*COMPONENT_DATA_FILES,'engine.py','guard.py',*_component_cold_archives(manifest)}
    if (base/'development').exists():
        if not (base/'development').is_dir() or (base/'development').is_symlink():raise EngineError('REPAIR_DEVELOPMENT_PATH_INVALID')
        names.update((manifest.get('development_sources') or {}).get('files') or {})
    result={}
    for name in sorted(names):
        path=base/name
        if path.is_symlink() or not path.resolve().is_relative_to(base) or not path.is_file():
            raise EngineError('REPAIR_SOURCE_PATH_INVALID:'+name)
        result[name]=sha256_file(path)
    return result


def _repair_preflight(base:Path)->dict:
    # Ordinary semantic loading can fail. This gate verifies bytes, tools, archives
    # and logical continuity independently; it relaxes only next_seq comparison.
    if _active_runtime_journal(base,NATIVE_COMMIT_JOURNAL_FILENAME):raise EngineError('REPAIR_NATIVE_RECOVERY_REQUIRED')
    if _active_runtime_journal(base,CONSISTENCY_REPAIR_JOURNAL):raise EngineError('REPAIR_RECOVERY_REQUIRED')
    manifest=strict_json_load(base/'manifest.json')
    declared=manifest.get('cold_archives') or {}
    if not isinstance(declared,dict):raise EngineError('REPAIR_COLD_REGISTRY_SHAPE')
    declared_paths=set()
    for row in declared.values():
        if not isinstance(row,dict) or not isinstance(row.get('path'),str):raise EngineError('REPAIR_COLD_REGISTRY_ENTRY')
        rel=row['path'].strip().replace('\\','/')
        if not rel or rel.startswith('/') or '..' in Path(rel).parts or rel in declared_paths:
            raise EngineError('REPAIR_COLD_REGISTRY_PATH_INVALID_OR_DUPLICATE')
        declared_paths.add(rel)
    before=_repair_fingerprint(base,manifest)
    module=_repair_guard_module(base);bound,errors=module.validate_dir(base,strict=True)
    if errors or not bound:raise EngineError('REPAIR_INPUT_BINDING:'+json.dumps(errors,ensure_ascii=False))
    if manifest.get('engine_version')!=ENGINE_VERSION or before['engine.py']!=sha256_file(Path(__file__).resolve()):
        raise EngineError('REPAIR_RUNNING_ENGINE_BINDING')
    _,errors=module.verify_cold_archives(base,manifest)
    if errors:raise EngineError('REPAIR_ARCHIVE_EVIDENCE:'+json.dumps(errors,ensure_ascii=False))
    if (base/'development').exists() and not module.development_intact(base,manifest):raise EngineError('REPAIR_DEVELOPMENT_BINDING')
    meta,events,raws=_history_read_verified(base/'events.jsonl',validate_metadata=False)
    expected=_history_expected_next_seq(events)
    ids=[e.get('event_id') for e in events]
    if not all(isinstance(v,str) and v.strip() for v in ids) or len(set(ids))!=len(ids):
        raise EngineError('REPAIR_HISTORY_EVENT_IDS_INVALID')
    # Match each external history reference to the manifest declaration and range.
    archives=_component_cold_archives(manifest);seen=set()
    for raw in (base/'events.jsonl').read_bytes().splitlines():
        if not raw.strip():continue
        row=strict_json_loads(raw.decode())
        if row.get('record_type')!='history_epoch' or not row.get('archive_ref'):continue
        rel=row['archive_ref'];declaration=archives.get(rel)
        if not declaration or rel in seen:raise EngineError('REPAIR_HISTORY_ARCHIVE_UNREGISTERED_OR_REPEATED:'+rel)
        seen.add(rel)
        for field in ('seq_start','seq_end','event_count'):
            if type(row.get(field)) is not int or type(declaration.get(field)) is not int or row[field]!=declaration[field]:
                raise EngineError('REPAIR_HISTORY_ARCHIVE_RANGE:'+rel+':'+field)
    declared_history={rel for rel,row in archives.items() if 'seq_start' in row}
    if declared_history!=seen:raise EngineError('REPAIR_HISTORY_ARCHIVE_COVERAGE')
    state=strict_json_load(base/'state.json');tasks=strict_json_load(base/'tasks.json')
    if state.get('game_time')!=tasks.get('game_time') or state.get('game_time')!=manifest.get('game_time'):
        raise EngineError('REPAIR_GAME_TIME_AUTHORITY_DISAGREEMENT')
    if _repair_fingerprint(base,manifest)!=before:raise EngineError('REPAIR_SOURCE_CHANGED_DURING_PREFLIGHT')
    return {'manifest':manifest,'fingerprint':before,'state':state,'tasks':tasks,'meta':meta,
            'events':events,'event_raw':raws,'next_seq':expected}


def _repair_add_change(changes,file,path,old,new,kind,evidence):
    if type(old)==type(new) and old==new:return
    candidate={'file':file,'path':path,'old':copy.deepcopy(old),'new':copy.deepcopy(new),
               'kind':kind,'evidence':copy.deepcopy(evidence)}
    previous=next((x for x in changes if x['file']==file and x['path']==path),None)
    if previous is not None and previous!=candidate:raise EngineError('REPAIR_CONFLICTING_EVIDENCE:'+file+path)
    if previous is None:changes.append(candidate)


def _repair_time_mirrors(facts,changes,diagnostics):
    state=facts['state'];now=parse_iso(state['game_time'])
    # This is a registered derived-view contract, not a per-save object lookup.
    for bucket in ('active_tasks','queued_tasks'):
        for index,task in enumerate(facts['tasks'].get(bucket,[])):
            view=task.get('view_rule') or {};data=task.get('task_data') or {}
            if view.get('schema')!='DERIVED_VIEW_RULE_V1' or task.get('status')!='active':continue
            mon=(task.get('runtime_policy') or {}).get('monitor') or {}
            if mon.get('mode')!='scheduled' or not view.get('next_source'):continue
            sources=[]
            for ref in view.get('status_sources',[]):
                try:
                    path=resolve_state_ref(state,ref);value=get_by_path(state,path)
                except KeyError:
                    diagnostics.append({'code':'REGISTERED_VIEW_SOURCE_MISSING','task_id':task.get('task_id'),'source_ref':ref});continue
                if isinstance(value,dict):sources.append((path,value))
            receipts=[(path,obj) for path,obj in sources if obj.get('status')=='booked' and parse_iso(obj.get('at'))]
            mirrors=[(path,obj) for path,obj in sources if all(k in obj for k in ('as_of','last_settlement_at','next_settlement_at','unified_daily_gold','unified_daily_grey'))]
            for mpath,mirror in mirrors:
                if len(receipts)!=1:
                    diagnostics.append({'code':'SETTLEMENT_RECEIPT_NOT_UNIQUE','source_ref':mpath});continue
                rpath,receipt=receipts[0];at=receipt['at']
                try:nxt=get_by_path(task,view['next_source'])
                except KeyError:continue
                if (not now or not parse_iso(nxt) or parse_iso(at)>now or parse_iso(nxt)<=now or
                    data.get('last_settlement_at')!=at or mon.get('last_reviewed_at')!=at or
                    data.get('next_settlement_at')!=nxt or mon.get('next_review_at')!=nxt):
                    diagnostics.append({'code':'SETTLEMENT_TIME_EVIDENCE_INSUFFICIENT','source_ref':mpath});continue
                pairs=[(receipt.get('total_'+c),data.get('last_total_'+c),data.get('daily_'+c),mirror.get('unified_daily_'+c)) for c in ('gold','grey')]
                if any(any(v is None or isinstance(v,bool) for v in values) or len({_price_decimal(v) for v in values})!=1 for values in pairs):
                    diagnostics.append({'code':'SETTLEMENT_AMOUNT_EVIDENCE_DISAGREES','source_ref':mpath});continue
                # Never infer capacity or ownership; these facts must already agree.
                if any(mirror.get(mk)!=data.get(tk) for mk,tk in (('mining_base_count','mining_bases'),('fixed_salvage_base_count','fixed_salvage_bases'))):
                    diagnostics.append({'code':'SETTLEMENT_ASSET_EVIDENCE_DISAGREES','source_ref':mpath});continue
                evidence={'task_id':task.get('task_id'),'task_source':f'tasks:{bucket}[{index}]',
                          'receipt_source':'state:'+rpath,'receipt_sha256':_repair_digest(receipt),
                          'task_sha256':_repair_digest(task),'mirror_source':'state:'+mpath,
                          'contract':'DERIVED_VIEW_RULE_V1 + booked receipt + identical existing amounts and counts'}
                for field,new in (('as_of',at),('last_settlement_at',at),('next_settlement_at',nxt)):
                    old=mirror[field]
                    if old==new:continue
                    if not parse_iso(old) or parse_iso(old)>=parse_iso(new):
                        diagnostics.append({'code':'SETTLEMENT_MIRROR_NOT_PROVEN_STALE','source_ref':mpath+'.'+field});continue
                    _repair_add_change(changes,'state.json',_repair_pointer(mpath.split('.')+[field]),old,new,'derived_settlement_time',evidence)


def _repair_flattened_candidates(doc,parts,prefix=()):
    if not parts:return [(prefix,doc)]
    if not isinstance(doc,dict):return []
    key=parts[0];out=[]
    if key in doc:out.extend(_repair_flattened_candidates(doc[key],parts[1:],prefix+(key,)))
    # Exact underscore decomposition only; no substring, fuzzy or amount lookup.
    for nested,value in doc.items():
        if isinstance(value,dict) and key.startswith(nested+'_'):
            out.extend(_repair_flattened_candidates(value,[key[len(nested)+1:]]+parts[1:],prefix+(nested,)))
    return out


def _repair_registered_references(doc,old,new,file,changes,evidence,parts=(),registered=False):
    if isinstance(doc,dict):
        for key,value in doc.items():
            enabled=registered or key in {'state_refs','mirrors','retrieval_route','view_rule','price_registry'}
            if value==old and (enabled or key in {'source_ref','value_ref','policy_ref','state_current_path','current_event_state_path'}):
                _repair_add_change(changes,file,_repair_pointer(parts+(key,)),old,new,'registered_reference_migration',evidence)
            else:_repair_registered_references(value,old,new,file,changes,evidence,parts+(key,),enabled)
    elif isinstance(doc,list):
        for index,value in enumerate(doc):
            if value==old and registered:_repair_add_change(changes,file,_repair_pointer(parts+(str(index),)),old,new,'registered_reference_migration',evidence)
            else:_repair_registered_references(value,old,new,file,changes,evidence,parts+(str(index),),registered)


def _repair_price_references(base,facts,changes,diagnostics):
    docs={k:strict_json_load(base/(k+'.json')) for k in ('rules','catalog')};docs.update(state=facts['state'],manifest=facts['manifest'])
    rows=_price_records(docs);runtime=(facts['state'].get('engine_runtime') or {}).get('pricing_runtime') or {}
    for mirror in runtime.get('mirrors',[]):
        old=mirror.get('path');price=rows.get(mirror.get('price_id'))
        if not isinstance(old,str) or not old.startswith('state:') or not price:continue
        try:_pricing_source_value(docs,old);continue
        except EngineError as ex:
            if not str(ex).startswith('PRICE_SOURCE_MISSING:'):raise
        parts=old.split(':',1)[1].split('.')
        candidates=_repair_flattened_candidates(facts['state'],parts)
        try:lo,hi=_price_anchor_value(price,docs)
        except EngineError as ex:
            diagnostics.append({'code':'PRICE_AUTHORITY_UNVERIFIED','source_ref':old,'error':str(ex)});continue
        compatible=[]
        for path,value in candidates:
            try:
                if lo==hi and _price_decimal(value)==lo:compatible.append((path,value))
            except EngineError:continue
        contract='unique exact nested-key decomposition + unchanged registered sealed price'
        if len(candidates)==1 and len(compatible)==1:
            new='state:'+'.'.join(compatible[0][0]);value=compatible[0][1]
        elif not candidates and isinstance(price.get('value_ref'),str) and price['value_ref'].startswith('state:') and price.get('price_kind')=='fixed_price':
            # A missing derived price field may reference its already registered
            # value authority directly. Do not recreate a second numeric authority.
            new=price['value_ref'];value=_pricing_source_value(docs,new)
            if lo!=hi or _price_decimal(value)!=lo:
                diagnostics.append({'code':'PRICE_VALUE_AUTHORITY_DISAGREES','source_ref':old});continue
            contract='missing derived mirror redirects to this price_id registered fixed-price value_ref'
        else:
            diagnostics.append({'code':'PRICE_REFERENCE_MAPPING_NOT_UNIQUE','source_ref':old,'candidate_count':len(candidates)});continue
        evidence={'old_source_ref':old,'current_source_ref':new,'price_id':price['price_id'],
                  'price_authority_sha256':_repair_digest(price),'value':value,'contract':contract}
        for file in ('state.json','tasks.json'):
            _repair_registered_references(facts[file[:-5]],old,new,file,changes,evidence)


def _repair_event_stages(facts,changes,diagnostics):
    for bucket in ('active_tasks','queued_tasks'):
        for index,task in enumerate(facts['tasks'].get(bucket,[])):
            data=task.get('task_data') or {};path=data.get('current_event_state_path');eid=data.get('current_event_id')
            if not path or not eid:continue
            try:resolved=resolve_state_ref(facts['state'],path);event=get_by_path(facts['state'],resolved)
            except KeyError:
                diagnostics.append({'code':'TASK_EVENT_REFERENCE_MISSING','task_id':task.get('task_id'),'source_ref':path});continue
            if not isinstance(event,dict) or event.get('event_id')!=eid:
                diagnostics.append({'code':'TASK_EVENT_ID_DISAGREEMENT','task_id':task.get('task_id')});continue
            if 'current_event_stage' not in data:continue
            stage=authoritative_event_stage(event)
            if not isinstance(stage,str) or not stage:continue
            evidence={'event_source':'state:'+resolved,'event_id':eid,'event_sha256':_repair_digest(event),
                      'contract':'event.phase preferred; legacy event.status fallback; task.phase independent'}
            _repair_add_change(changes,'tasks.json',_repair_pointer([bucket,str(index),'task_data','current_event_stage']),
                               data['current_event_stage'],stage,'event_stage_mirror',evidence)


def consistency_repair_plan(base:Path=ROOT)->dict:
    base=Path(base).resolve()
    with engine_lock(base):
        facts=_repair_preflight(base);changes=[];diagnostics=[];meta=facts['meta']
        if type(meta.get('next_seq')) is not int or meta['next_seq']!=facts['next_seq']:
            _repair_add_change(changes,'events.jsonl','/next_seq',meta.get('next_seq'),facts['next_seq'],'history_metadata',
                               {'last_logical_seq':facts['events'][-1]['seq'] if facts['events'] else None,
                                'logical_event_count':len(facts['events']),'events_raw_sha256':sha256_bytes(b'\n'.join(facts['event_raw'])+b'\n'),
                                'checks':['cold file/wrapper/payload hashes','epoch compressed/decoded/event hashes','epoch ranges/counts','strict cross-epoch continuity']})
        _repair_time_mirrors(facts,changes,diagnostics);_repair_price_references(base,facts,changes,diagnostics);_repair_event_stages(facts,changes,diagnostics)
        changes.sort(key=lambda row:(row['file'],row['path']))
        # This remains a full audit, with original errors retained. It grants no READY.
        audit=run_checks(base,full=True,require_manifest=True)
        if _repair_fingerprint(base,facts['manifest'])!=facts['fingerprint']:raise EngineError('REPAIR_SOURCE_CHANGED_DURING_PLAN')
        plan={'schema':CONSISTENCY_REPAIR_SCHEMA,'status':'PLAN_AVAILABLE' if changes else 'NO_PROVEN_REPAIR',
              'save_set_id':facts['manifest']['save_set_id'],'fingerprint':facts['fingerprint'],
              'checks':['input bytes','executed tool/protocol binding','complete archive evidence','logical event continuity','registered repair evidence'],
              'development_verification':'actual member hashes' if (base/'development').exists() else 'not materialized; declared binding preserved, executable tool bytes verified','changes':changes,'diagnostics':diagnostics,'full_audit_status':audit['status'],'full_audit_errors':audit.get('errors',[]),
              'affected_files':sorted({row['file'] for row in changes}|({'manifest.json','events.jsonl'} if changes else set())),
              'limitations':['No new settlement, time advance, random evaluation, price or authorization changes.',
                             'Unproven audit errors remain unresolved. Repair availability is not full business readiness.']}
        plan['plan_sha256']=_repair_digest(plan)
        return plan


def consistency_repair_recover(base:Path=ROOT)->dict:
    base=Path(base).resolve()
    with engine_lock(base):
        try:result=_repair_guard_module(base).recover_consistency_repair(base)
        except Exception as ex:raise EngineError('REPAIR_RECOVERY_FAILED:'+str(ex)) from ex
        return result or {'status':'NO_PENDING_REPAIR'}


def _repair_snapshot_copy(base:Path,dest:Path,manifest:dict):
    dest.mkdir(parents=True,exist_ok=False)
    names={'manifest.json',*COMPONENT_DATA_FILES,'engine.py','guard.py',*_component_cold_archives(manifest)}
    if (base/'development').exists():names.update((manifest.get('development_sources') or {}).get('files') or {})
    for name in sorted(names):
        target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);_native_durable_copy(base/name,target)
    _native_sync_dir(dest);_native_sync_dir(dest.parent)


def consistency_repair_apply(base:Path,approved_plan:dict)->dict:
    base=Path(base).resolve()
    if not isinstance(approved_plan,dict) or approved_plan.get('schema')!=CONSISTENCY_REPAIR_SCHEMA:
        raise EngineError('REPAIR_PLAN_SCHEMA_REQUIRED')
    with engine_lock(base):
        consistency_repair_recover(base)
        current=consistency_repair_plan(base)
        # Exact rederivation prevents turning this endpoint into an arbitrary patch.
        if approved_plan!=current:raise EngineError('REPAIR_PLAN_STALE_OR_UNPROVEN')
        if not current['changes']:return {'status':'NO_CHANGE','save_set_id':current['save_set_id'],'event_appended':False}
        token=current['plan_sha256'];home=base/'.runtime'/'consistency_repairs'/token
        if home.exists():
            # Previous rolled-back attempts keep snapshots. Use a fresh attempt directory.
            token=_repair_digest({'plan':token,'attempt':uuid.uuid4().hex});home=home.with_name(token)
        home.mkdir(parents=True,exist_ok=False);parent=home/'parent';target=home/'target'
        manifest=strict_json_load(base/'manifest.json')
        _repair_snapshot_copy(base,parent,manifest);_repair_snapshot_copy(base,target,manifest)
        docs={name:strict_json_load(target/name) for name in ('state.json','tasks.json')}
        metadata,old_events,old_raws=_history_read_verified(target/'events.jsonl',validate_metadata=False)
        for row in current['changes']:
            doc=metadata if row['file']=='events.jsonl' else docs[row['file']]
            old=doc.get('next_seq') if row['kind']=='history_metadata' else _repair_get(doc,row['path'])
            if type(old)!=type(row['old']) or old!=row['old']:raise EngineError('REPAIR_ORIGINAL_VALUE_CHANGED')
            if row['kind']=='history_metadata':metadata['next_seq']=row['new']
            else:_repair_set(doc,row['path'],row['new'])
        for name,doc in docs.items():
            if any(row['file']==name for row in current['changes']):_native_durable_replace_bytes(target/name,_authority_json_bytes(doc))
        _native_durable_replace_bytes(target/'events.jsonl',_history_replace_metadata_bytes((target/'events.jsonl').read_bytes(),metadata))
        # Existing normalization and append mechanisms; one small zero-time audit event.
        event={'event_id':'EVT-CONSISTENCY-REPAIR-'+current['plan_sha256'][:24],
               'game_time':docs['state.json']['game_time'],'type':'system','subtype':'consistency_repair',
               'summary':'Evidence-backed metadata, reference and derived mirror consistency repair.',
               'source':'GAME ENGINE '+ENGINE_VERSION+' CONSISTENCY_REPAIR_V1','zero_time':True,
               'authority_files':sorted({row['file'] for row in current['changes']}),
               'changes':[{'target':('events' if row['file']=='events.jsonl' else row['file'][:-5])+':'+row['path'],'action':'evidence_backed_repair'} for row in current['changes']],
               'repair_plan':{'plan_sha256':current['plan_sha256'],'changes':current['changes']},
               'source_refs':['state:self','tasks:self','events:self','manifest:self']}
        _append_engine_history(target/'events.jsonl',event)
        v=parse_version(manifest['save_version']);version=version_text((v[0],v[1]+1))
        lineage=copy.deepcopy(manifest.get('migration_lineage') or {});lineage.update(from_save_set_id=manifest['save_set_id'],game_time_advanced=False,consistency_repair_plan_sha256=current['plan_sha256'])
        target_manifest=_component_write_manifest_native(target,version,manifest['save_set_id'],lineage,frozen_development_sources=manifest.get('development_sources') or {})
        # Existing full audit may still fail, but no novel failure is accepted.
        before_audit=run_checks(parent,full=True,require_manifest=True)
        after_audit=run_checks(target,full=True,require_manifest=True)
        before_errors=set(before_audit.get('errors',[]));before_codes={e.split(':',1)[0] for e in before_errors}
        after_errors=set(after_audit.get('errors',[]));after_codes={e.split(':',1)[0] for e in after_errors}
        if not after_errors.issubset(before_errors):
            # Stale metadata may hide original errors behind PARSE. Audit an evidence-
            # corrected parent copy without adding any event to establish its errors.
            if any(row['kind']=='history_metadata' for row in current['changes']) and any(e.startswith('PARSE: HISTORY metadata next_seq mismatch') for e in before_errors):
                audit_copy=home/'audit_parent';_repair_snapshot_copy(parent,audit_copy,manifest)
                m,ee,_=_history_read_verified(audit_copy/'events.jsonl',False);m['next_seq']=_history_expected_next_seq(ee)
                _native_durable_replace_bytes(audit_copy/'events.jsonl',_history_replace_metadata_bytes((audit_copy/'events.jsonl').read_bytes(),m))
                _component_write_manifest_native(audit_copy,manifest['save_version'],manifest.get('parent_save_set_id'),frozen_development_sources=manifest.get('development_sources') or {})
                before_errors=set(run_checks(audit_copy,full=True,require_manifest=True).get('errors',[]))
            if not after_errors.issubset(before_errors):raise EngineError('REPAIR_NEW_BUSINESS_AUDIT_ERROR:'+json.dumps(after_audit.get('errors',[]),ensure_ascii=False))
        # Assert exact allowlisted changes and byte-preserved history before commit.
        for name in ('state.json','tasks.json'):
            expected=strict_json_load(parent/name)
            for row in current['changes']:
                if row['file']==name:_repair_set(expected,row['path'],row['new'])
            if _repair_digest(expected)!=_repair_digest(strict_json_load(target/name)):raise EngineError('REPAIR_IMMUTABLE_BUSINESS_MISMATCH:'+name)
        _,new_events,new_raws=read_history_view(target/'events.jsonl')
        if new_raws[:-1]!=old_raws or len(new_events)!=len(old_events)+1:raise EngineError('REPAIR_HISTORICAL_BYTES_CHANGED')
        if _repair_fingerprint(base,manifest)!=current['fingerprint']:raise EngineError('REPAIR_SOURCE_CHANGED_BEFORE_COMMIT')
        module=_repair_guard_module(base);bound,errors=module.validate_dir(target,strict=True)
        if errors or not bound:raise EngineError('REPAIR_TARGET_BINDING:'+json.dumps(errors,ensure_ascii=False))
        names={'manifest.json',*COMPONENT_DATA_FILES,'engine.py','guard.py'}
        journal={'schema':'VOYAGER_CONSISTENCY_REPAIR_JOURNAL_V1','root':str(base),'transaction_id':token,
                 'plan_sha256':current['plan_sha256'],'development_materialized':(base/'development').exists(),'parent_hashes':{n:sha256_file(parent/n) for n in sorted(names)},
                 'target_hashes':{n:sha256_file(target/n) for n in sorted(names)}}
        _native_atomic_json(home/'plan.json',current);_native_atomic_json(home/'audit_results.json',{'before':before_audit,'after':after_audit})
        jp=base/'.runtime'/CONSISTENCY_REPAIR_JOURNAL;_native_atomic_json(jp,journal)
        try:
            _native_test_failpoint('repair_after_journal')
            for name in sorted(names-{'manifest.json'}):
                if journal['parent_hashes'][name]!=journal['target_hashes'][name]:_native_durable_copy(target/name,base/name)
                _native_test_failpoint('repair_after_'+name)
            _native_test_failpoint('repair_before_manifest')
            _native_durable_copy(target/'manifest.json',base/'manifest.json')
            _native_test_failpoint('repair_after_manifest')
            _native_atomic_json(home/'commit_receipt.json',{'status':'COMMITTED','save_set_id':target_manifest['save_set_id'],'plan_sha256':current['plan_sha256']})
            _native_test_failpoint('repair_after_receipt')
            _native_clear_journal(jp)
        except BaseException:
            # Process death leaves the journal. Exceptions recover under this lock.
            module.recover_consistency_repair(base);raise
        return {'status':'COMMITTED','save_set_id':target_manifest['save_set_id'],'parent_save_set_id':manifest['save_set_id'],
                'changed_fields':len(current['changes']),'plan_sha256':current['plan_sha256'],'event_appended':True,
                'full_audit_status':after_audit['status'],'unresolved_errors':after_audit.get('errors',[]),
                'game_time':docs['state.json']['game_time'],'export_status':'NOT_REQUESTED','external_save_confirmed':False}


def _consistency_main(argv:Optional[List[str]]=None)->int:
    argv=list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in {'repairplan','repairapply','repairrecover'}:
        return _consistency_previous_main(argv)
    parser=argparse.ArgumentParser(prog='engine '+argv[0]);parser.add_argument('--base',default=str(ROOT))
    if argv[0]=='repairapply':parser.add_argument('--plan',required=True)
    args=parser.parse_args(argv[1:])
    try:
        if os.environ.get('VOYAGER_DEVELOPER_MODE')!='1' or os.environ.get('VOYAGER_DIAGNOSTIC_CONTEXT')!='gm':raise EngineError('REPAIR_EXPLICIT_DEVELOPER_CONTEXT_REQUIRED')
        if argv[0]=='repairplan':result=consistency_repair_plan(Path(args.base))
        elif argv[0]=='repairrecover':result=consistency_repair_recover(Path(args.base))
        else:result=consistency_repair_apply(Path(args.base),strict_json_load(Path(args.plan)))
        print_json(result);return 0
    except Exception as ex:
        print_json({'status':'FAIL','error':str(ex),'operation':argv[0]});return 1

main=_consistency_main


_batch_a_main=main
_batch_a_ensure_ready=ensure_source_ready
_batch_a_cold_start=cold_start_packet
_batch_a_query=query_packet
_batch_a_manifest=_component_write_manifest_native
_batch_a_auth=_phase2_domain_authorization
_batch_a_write_json=_write_authority_json
_batch_a_catalog=domain_command_catalog
