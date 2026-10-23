# === VOYAGER_DEV_MODULE: p2_contracts ===
# === VOYAGER P2 AUDIT/QUERY/REFERENCE CONTRACTS ===
EVENT_SCHEMA_VERSION='EVENT_V3'
QUERY_CONTRACT_VERSION='QUERY_CONTRACT_V4'
REFERENCE_GRAPH_SCHEMA='REFERENCE_GRAPH_V1'

def _v130_layer__event_v2_normalize_01(event:dict)->dict:
    ev=copy.deepcopy(event)
    ev['schema_version']=EVENT_SCHEMA_VERSION
    ev['event_schema']=EVENT_SCHEMA_VERSION  # read compatibility only
    ev.setdefault('game_time',None)
    ev.setdefault('recorded_at',ev.get('game_time'))
    ev.setdefault('command_id',None)
    ev.setdefault('actor','system:engine')
    ev.setdefault('authorization',{'status':'system_authorized','source':'engine_contract'})
    ev.setdefault('causes',[])
    ev.setdefault('related_entities',[])
    ev.setdefault('rule_versions',[])
    ev.setdefault('before',{})
    if 'effects' not in ev: ev['effects']=copy.deepcopy(ev.get('changes') or [])
    ev.setdefault('after',{})
    ev.setdefault('narrative',ev.get('summary') or '')
    ev.setdefault('knowledge_scope','current_authority')
    ev.setdefault('source_refs',copy.deepcopy(ev.get('authority_files') or []))
    return ev

_append_engine_history_p2_base=_v130_layer__append_engine_history_01
def _v130_layer__append_engine_history_02(path:Path,event:dict)->None:
    _append_engine_history_p2_base(path,_event_v2_normalize(event))

def _query_contract_packet(intent,arg,value,ready,state,topic,source_refs):
    missing=_intent_required_missing(intent,arg,value)
    required=[]
    if intent=='fleet_location': required={'voyager':['as_of','base.ships','deployments','transit.ships'],'jinchuan':['as_of','commercial_guard_sites','development_groups','status'],'shadow':['as_of','homeport','base.ships','deployments']}.get(arg or '',[])
    elif intent in {'active_tasks','queued_tasks','decision_gates','obligations'}: required=['value:list']
    elif intent=='finance': required=['gold','grey']
    elif intent=='core': required=['fleet_core','locations']
    elif intent=='fleet_status': required=['fleet','display_name','ships','personnel','location']
    elif value is not None: required=['value']
    returned=[]
    if isinstance(value,dict): returned=sorted(value.keys())
    elif isinstance(value,list): returned=['value:list']
    elif value is not None: returned=['value']
    status='UNKNOWN' if value is None else ('MISSING' if missing else 'COMPLETE')
    return {'packet':'QUERY_INTENT_V4','registry':QUERY_INTENT_REGISTRY_SCHEMA,'contract':QUERY_CONTRACT_VERSION,
      'engine_version':ENGINE_VERSION,'save_set_id':ready.get('save_set_id'),'game_time':state.get('game_time'),'topic':topic,
      'intent':intent,'entity_id':arg,'required_fields':required,'returned_fields':returned,'missing_fields':missing,
      'value':value,'source_refs':source_refs,'freshness':{'as_of_game_time':state.get('game_time'),'save_set_id':ready.get('save_set_id')},
      'confidence':'authoritative' if value is not None else 'unknown','completeness':'COMPLETE' if not missing and value is not None else ('MISSING' if missing else 'UNKNOWN'),
      'status':status,'truncated':False}

_query_intent_packet_p2_base=_v130_layer_query_intent_packet_01
def _v1403_previous_query_intent_packet(base:Path,topic:str)->Optional[dict]:
    old=_query_intent_packet_p2_base(base,topic)
    if old is None:return None
    ready=ensure_source_ready(base);state=read_json_view(base/'state.json')
    intent=old.get('intent');arg=old.get('argument');value=old.get('value')
    refs=['state:game_time']
    if intent in {'active_tasks','queued_tasks','decision_gates','obligations'}:refs.append('tasks:self')
    elif intent=='next_event':refs.append('events:next_deterministic')
    else:refs.append('state:'+str(intent))
    return _query_contract_packet(intent,arg,value,ready,state,topic,refs)

_cold_start_packet_p2_base=_v130_layer_cold_start_packet_01
def _v1403_previous_cold_start_packet(base:Path=ROOT)->dict:
    old=_cold_start_packet_p2_base(base)
    state=read_json(base/'state.json');manifest=read_json(base/'manifest.json')
    try:
        acct=get_by_path(state,CALDER_552_CANONICAL_PATH)
        industry={'asset_count':acct.get('asset_count'),'daily_net_income_gold':acct.get('daily_net_income_gold'),'daily_net_income_grey':acct.get('daily_net_income_grey'),'next_settlement_at':acct.get('next_settlement_at'),'authority_ref':'state:'+CALDER_552_CANONICAL_PATH}
    except Exception:
        industry=None
    components=manifest.get('components') or {}
    # Resume packet deliberately excludes full profiles, source receipts and large narratives.
    compact={'packet':COLD_START_PACKET_SCHEMA,'engine_version':ENGINE_VERSION,'save_set_id':old.get('save_set_id'),'game_time':old.get('game_time'),
      'authority_fingerprint':old.get('authority_fingerprint'),'player_location':(old.get('fleet_locations') or {}).get('voyager'),
      'fleet_core':old.get('fleet_core'),'industry_current':industry,'next_deterministic_event':old.get('next_deterministic_event'),'next_semantic_barrier':old.get('next_semantic_barrier'),
      'active_summary':{'task_counts':old.get('task_counts'),'ongoing_obligations':old.get('ongoing_obligations'),'maintenance_runtime':old.get('maintenance_runtime'),'pending_contact_count':old.get('pending_contact_count')},
      'pending_decisions':old.get('open_decision_gates'),'random_runtime':old.get('combat_runtime'),'pending_turn':old.get('pending_turn'),
      'source_layout':{'core_save_files':1+len(components),'manifest_files':1,'hash_checked_components':len(components),'authority_file_count_semantics':'components excluding manifest.json'},
      'query_contract':QUERY_CONTRACT_VERSION,'source_refs':['manifest:save_set_id','state:game_time','state:fleet_core','state:'+CALDER_552_CANONICAL_PATH,'tasks:self','events:next_deterministic']}
    raw=json.dumps(compact,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    compact['context_bytes']=len(raw);compact['context_budget_bytes']=3500
    if len(raw)>3500:
        compact['active_summary']['ongoing_obligations']=(compact['active_summary'].get('ongoing_obligations') or [])[:4]
        compact['pending_decisions']=(compact.get('pending_decisions') or [])[:4]
        compact['context_bytes']=len(json.dumps(compact,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
    return compact

def reference_integrity_packet(base:Path=ROOT)->dict:
    rules=read_json(base/'rules.json');catalog=read_json(base/'catalog.json');state=read_json(base/'state.json');tasks=read_json(base/'tasks.json')
    rr=((rules.get('rule_registry') or {}).get('rules') or {}); cr=((catalog.get('catalog_registry') or {}).get('entities') or {})
    rule_ids=set(rr); entity_ids=set(cr); state_entities=set((((state.get('entity_registry') or {}).get('entities')) or {}))
    errors=[];warnings=[];edges=[]
    try:resolve_rule_registry(base)
    except EngineError as ex:errors.append(str(ex))
    # duplicates are impossible in JSON objects but registry key/id mismatch is equivalent corruption.
    for k,v in rr.items():
        if not isinstance(v,dict) or v.get('rule_id')!=k: errors.append('RULE_ID_KEY_MISMATCH:'+str(k))
        for x in (v.get('supersedes') or []):
            edges.append(('rule',k,'supersedes',x))
            if x not in rule_ids: errors.append('DANGLING_SUPERSEDES:'+k+'->'+str(x))
        for x in (v.get('superseded_by') or []):
            if x not in rule_ids: errors.append('DANGLING_SUPERSEDED_BY:'+k+'->'+str(x))
    for k,v in cr.items():
        if not isinstance(v,dict) or v.get('entity_id')!=k: errors.append('ENTITY_ID_KEY_MISMATCH:'+str(k))
    # direct two-way supersedes cycle guard
    for a,v in rr.items():
        for b in (v.get('supersedes') or []):
            if b in rr and a in (rr[b].get('supersedes') or []):errors.append('CIRCULAR_SUPERSEDES:'+a+'<->'+b)
    all_entities=entity_ids|state_entities
    for bucket in ('active_tasks','queued_tasks'):
        for t in tasks.get(bucket) or []:
            if not isinstance(t,dict):continue
            tid=str(t.get('task_id') or '?')
            for oid in (t.get('owner_ids') or [])+(t.get('location_ids') or []):
                if isinstance(oid,str) and (oid.startswith(('PER-','ORG-','CLS-','LOC-','SHIP-','VES-','FAC-','EQ-'))) and oid not in all_entities:
                    msg='TASK_ENTITY_UNRESOLVED:'+tid+'->'+oid
                    # V12.49: executable references in active tasks are a save-hard gate.
                    # Queued drafts remain warnings until they become executable.
                    (errors if bucket=='active_tasks' else warnings).append(msg)
            rrte=t.get('retrieval_route') or {}
            for j,raw_path in enumerate(rrte.get('state_paths') or []):
                if not isinstance(raw_path,str):continue
                try:get_state_path(state,raw_path)
                except Exception:errors.append('TASK_STATE_PATH_UNRESOLVED:'+tid+'->retrieval_route.state_paths['+str(j)+']:'+raw_path)
            for field_path,raw_path in _task_machine_state_paths(t):
                try:get_state_path(state,raw_path)
                except Exception:errors.append('TASK_MACHINE_STATE_PATH_UNRESOLVED:'+tid+'->'+field_path+':'+raw_path)
            refs=[]
            for key in ('query_order','world_rules','history_tags'):
                refs += [x for x in (rrte.get(key) or []) if isinstance(x,str)]
            for x in refs:
                if x.startswith('rules:') and x[6:] not in rule_ids:errors.append('TASK_RULE_MISSING:'+tid+'->'+x)
                if x.startswith('catalog:') and x[8:] not in entity_ids:errors.append('TASK_CATALOG_MISSING:'+tid+'->'+x)
    # unresolved commitments must have a declared subject/org when those fields exist.
    items=((((state.get('engine_runtime') or {}).get('commitment_registry') or {}).get('items')) or {})
    for cid,rec in items.items():
        if isinstance(rec,dict) and rec.get('status') not in {'resolved','closed','cancelled'}:
            for k in ('character_id','organization_id','entity_id'):
                x=rec.get(k)
                if x and x not in all_entities:warnings.append('COMMITMENT_ENTITY_UNRESOLVED:'+str(cid)+'->'+str(x))
    return {'packet':'REFERENCE_INTEGRITY_V1','schema':REFERENCE_GRAPH_SCHEMA,'status':'FAIL' if errors else 'PASS','errors':sorted(set(errors)),'warnings':sorted(set(warnings)),'counts':{'rules':len(rule_ids),'catalog_entities':len(entity_ids),'state_entities':len(state_entities),'edges_checked':len(edges)}}

def legacy_migration_packet(input_dir:Path,output_dir:Path)->dict:
    inp=input_dir.resolve();out=output_dir.resolve()
    if inp==out or out in inp.parents:raise EngineError('LEGACY_MIGRATION_OUTPUT_MUST_BE_SEPARATE')
    if not inp.is_dir():raise EngineError('LEGACY_MIGRATION_INPUT_DIR_REQUIRED')
    if out.exists():raise EngineError('LEGACY_MIGRATION_OUTPUT_ALREADY_EXISTS')
    out.mkdir(parents=True);q=out/'legacy_input_snapshot';shutil.copytree(inp,q)
    # Migration logic is explicitly quarantined; normal boot/query/advance/commit never enters here.
    return {'packet':'LEGACY_MIGRATION_V1','status':'QUARANTINED_INPUT','input_snapshot':str(q),'output':str(out),'in_place_modified':False,'next_step':'run a version-specific migration adapter explicitly; no adapter is guessed from ambiguous legacy input'}

