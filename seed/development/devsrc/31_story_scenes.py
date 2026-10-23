# === VOYAGER_DEV_MODULE: story_scenes ===
_story_scope=contextvars.ContextVar('voyager_story_scope',default=None)
STORY_ACTIONS={'entity_register','scene_create','scene_phase','scene_focus','fact_append','fact_correct','knowledge_disclose','decision_open','decision_resolve','evidence_link','narrative_commit','narrative_rewrite','consequence_resolve','experience_record','experience_revoke'}


def _story_id(value):
    if not isinstance(value,str) or not SCENE_ID_RE.fullmatch(value):raise EngineError('STORY_STABLE_ID_REQUIRED')
    return value


def _story_text(value,limit=2000):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:raise EngineError('STORY_TEXT_INVALID')
    return value


def _story_runtime(state):
    rt=state.get('engine_runtime',{}).get('story_runtime_v1')
    if not isinstance(rt,dict) or rt.get('schema')!='STORY_RUNTIME_V1':raise EngineError('STORY_EXPLICIT_MIGRATION_REQUIRED')
    return rt


def _story_record(state,sid,open_only=False):
    rec=_scene_registry(state)['records'].get(_story_id(sid))
    if not isinstance(rec,dict):raise EngineError('STORY_SCENE_NOT_FOUND')
    if open_only and rec['phase']=='closed':raise EngineError('STORY_SCENE_TERMINAL')
    return rec


def _story_event_context():
    ctx=_story_scope.get()
    if not ctx:raise EngineError('STORY_NATIVE_TRANSACTION_REQUIRED')
    return ctx


def _story_entity(state,eid,require_active=True):
    row=state.get('entity_registry',{}).get('entities',{}).get(eid)
    if not isinstance(row,dict) or require_active and row.get('status') not in ('active','alive',None):raise EngineError('STORY_ENTITY_NOT_REGISTERED:'+str(eid))
    return row


def _story_entity_expected(state):
    out=_batch_c_entity_expected(state)
    for eid,rec in state.get('engine_runtime',{}).get('story_runtime_v1',{}).get('entities',{}).items():
        path='engine_runtime.story_runtime_v1.entities.'+eid
        out[eid]={'entity_type':'person','canonical_name':rec['name'],'aliases':rec.get('aliases',[]),'status':'active','state_path':path,'source_ref':path,'managed_by':'story_runtime_v1'}
    return out


def _story_targets(payload):
    if payload.get('kind') not in ('story_action','story_transaction'):return _batch_c_targets(payload)
    actions=payload.get('actions') if payload['kind']=='story_transaction' else [payload.get('action')]
    if not isinstance(actions,list) or not 1<=len(actions)<=80:raise EngineError('STORY_ACTION_BATCH_INVALID')
    targets=[]
    for action in actions:
        if not isinstance(action,dict) or action.get('type') not in STORY_ACTIONS:raise EngineError('STORY_ACTION_UNKNOWN')
        typ=action['type'];sid=action.get('scene_id')
        if sid:targets.append('state:engine_runtime.scene_registry_v1.records.'+_story_id(sid))
        if typ=='entity_register':targets+=['state:entity_registry','state:engine_runtime.story_runtime_v1.entities.'+_story_id(action.get('entity_id')),'state:engine_runtime.story_turns_v1.npcs.'+_story_id(action.get('entity_id')),'state:engine_runtime.living_world_v1.profiles.'+_story_id(action.get('entity_id'))]
        elif typ.startswith('experience_'):targets.append('events:experience_v1')
        elif typ=='scene_focus':targets.append('state:engine_runtime.story_runtime_v1.focus_scene_id')
        else:targets.append('state:engine_runtime.story_runtime_v1')
        if action.get('task_id')==_PATROL_TASK_ID or (sid and typ=='scene_phase' and action.get('patrol_adapter') is True):targets+=['tasks:task:'+_PATROL_TASK_ID,'state:'+SCENE_PATROL_PATH+'.current_local_event']
    return sorted(set(targets))


def _story_cost(payload):
    if payload.get('kind') in ('story_action','story_transaction'):
        actions=payload.get('actions') if payload['kind']=='story_transaction' else [payload.get('action')]
        return {'uses':1,'gold_units':0,'grey_units':0,'quantity':len(actions) if isinstance(actions,list) else 0}
    return _batch_c_cost(payload)


def _story_actions_apply(stage,state,tasks,payload):
    if payload.get('kind') not in ('story_action','story_transaction'):
        if payload.get('kind')=='scene_record' and payload.get('scene_action')=='create':
            for eid in payload.get('participants',[]):_story_entity(state,eid)
        result=_batch_c_apply(stage,state,tasks,payload)
        if payload.get('kind')=='scene_record' and payload.get('scene_action')=='create':
            rt=_story_runtime(state);tid=payload['task_id'];binding=rt['task_scene_bindings'].setdefault(tid,{'task_id':tid,'one_open_scene':True,'adapter':'patrol_v1' if tid==_PATROL_TASK_ID else 'generic','scene_ids':[]});binding['scene_ids'].append(payload['scene_id'])
        return result
    digest=_domain_payload_digest(payload);ctx={'event_id':'DOMAIN-'+payload['command_id']+'-'+sha256_bytes(str(digest).encode())[:8],'command_id':payload['command_id'],'authorization_ref':payload['authorization_ref'],'outer':payload,'stage':Path(stage)};token=_story_scope.set(ctx)
    try:
        actions=payload['actions'] if payload['kind']=='story_transaction' else [payload['action']];results=[];changes=[]
        for action in actions:
            if action.get('type')=='scene_create':raise EngineError('STORY_LEGACY_SCENE_USE_TYPED_SCENE_OPEN')
            result=_s3_apply_update(stage,state,tasks,copy.deepcopy(action)) if action.get('type')=='entity_register' else _story_action_apply(stage,state,tasks,copy.deepcopy(action));results.append(result);changes+=result.get('changes',[])
        report=_story_integrity(state,tasks)
        if report['status']!='PASS':raise EngineError('STORY_POSTCHECK:'+str(report['errors']))
        return {'kind':payload['kind'],'results':results,'changes':changes}
    finally:_story_scope.reset(token)


def _story_action_apply(stage,state,tasks,action):
    _story_action_schema(action)
    typ=action['type'];rt=_story_runtime(state);ctx=_story_event_context();now=state['game_time'];sid=action.get('scene_id');changes=[];out={'action':typ}
    if typ=='entity_register':
        eid=_story_id(action['entity_id']);name=_story_text(action['name'],100);aliases=action.get('aliases',[])
        if not isinstance(aliases,list) or any(not isinstance(a,str) or not a.strip() for a in aliases):raise EngineError('STORY_ENTITY_ALIASES')
        if eid in state['entity_registry']['entities']:raise EngineError('STORY_ENTITY_ID_EXISTS_USE_REFERENCE')
        names={_normalize_search_text(n) for rec in state['entity_registry']['entities'].values() for n in [rec['canonical_name'],*rec.get('aliases',[])]}
        if any(_normalize_search_text(n) in names for n in [name,*aliases]):raise EngineError('STORY_ENTITY_NAME_EXISTS_USE_REFERENCE')
        rt['entities'][eid]={'entity_id':eid,'name':name,'aliases':aliases,'role':_story_text(action.get('role','independent civilian'),300),'registered_at':now,'source_event_id':ctx['event_id'],'crew_or_asset_created':False};_sync_entity_registry(state);changes=[{'target':'state:engine_runtime.story_runtime_v1.entities.'+eid,'action':'register_stable_person_identity'},{'target':'state:entity_registry','action':'derive_identity_route'}];out['entity_id']=eid
    elif typ=='scene_create':
        tid=action['task_id'];participants=action.get('participants',[])
        for eid in participants:_story_entity(state,eid)
        binding=rt['task_scene_bindings'].setdefault(tid,{'task_id':tid,'one_open_scene':True,'adapter':'patrol_v1' if tid==_PATROL_TASK_ID else 'generic','scene_ids':[]})
        p={'kind':'scene_record','scene_action':'create','scene_id':sid,'task_id':tid,'scene_type':_story_text(action['family'],80),'title':_story_text(action['title'],200),'participants':participants,'facts':[],'command_id':ctx['command_id']}
        effect=_scene_domain_record(state,tasks,p);rec=_story_record(state,sid);rec['knowledge_scope']='explicit';rec['location_label']=_story_text(action.get('location_label','未确认位置'),200);rec['story_schema']='STORY_SCENE_V1';binding['scene_ids'].append(sid);changes=effect['changes']+[{'target':'state:engine_runtime.story_runtime_v1.task_scene_bindings.'+tid,'action':'bind_scene'}];out['scene_id']=sid
    elif typ=='scene_focus':
        if sid is not None:_story_record(state,sid,True)
        rt['focus_scene_id']=sid;changes=[{'target':'state:engine_runtime.story_runtime_v1.focus_scene_id','action':'explicit_focus'}]
    elif typ=='scene_phase':
        rec=_story_record(state,sid,True);p={'scene_id':sid,'scene_action':'close' if action['phase']=='closed' else 'advance','phase':action['phase'],'command_id':ctx['command_id'],'task_id':rec['task_id']}
        if rec['task_id']==_PATROL_TASK_ID and action.get('patrol_adapter') is not True:raise EngineError('STORY_PATROL_TARGET_EXPLICIT_REQUIRED')
        effect=_scene_domain_record(state,tasks,p);changes=effect['changes']
        if action['phase']=='closed' and rt['focus_scene_id']==sid:rt['focus_scene_id']=None;changes.append({'target':'state:engine_runtime.story_runtime_v1.focus_scene_id','action':'release_closed_focus'})
    elif typ in ('fact_append','fact_correct','knowledge_disclose','evidence_link'):
        return _knowledge_action(stage,state,tasks,action)
    elif typ=='decision_open':
        rec=_story_record(state,sid,True);did=_story_id(action['decision_id'])
        if did in rt['decisions']:raise EngineError('STORY_DECISION_EXISTS')
        rt['decisions'][did]={'decision_id':did,'scene_id':sid,'prompt':_story_text(action['prompt']),'status':'pending','source_event_id':ctx['event_id']};rec.setdefault('pending_decisions',[]).append(did);changes=[{'target':'state:engine_runtime.story_runtime_v1.decisions.'+did,'action':'open_decision'},{'target':'state:engine_runtime.scene_registry_v1.records.'+sid+'.pending_decisions','action':'link_decision'}]
    elif typ=='decision_resolve':
        rec=_story_record(state,sid,True);decision=rt['decisions'].get(action['decision_id'])
        if not decision or decision['scene_id']!=sid or decision['status']!='pending':raise EngineError('STORY_DECISION_NOT_PENDING')
        decision.update(status='resolved',player_action=_story_text(action['player_action']),resolved_at=now,cause_event_id=ctx['event_id']);rec['pending_decisions'].remove(action['decision_id']);changes=[{'target':'state:engine_runtime.story_runtime_v1.decisions.'+action['decision_id'],'action':'resolve_freeform_choice'},{'target':'state:engine_runtime.scene_registry_v1.records.'+sid+'.pending_decisions','action':'resolve_decision'}]
    elif typ in ('narrative_commit','narrative_rewrite','consequence_resolve'):return _narrative_action(stage,state,tasks,action)
    elif typ in ('experience_record','experience_revoke'):return _experience_action(stage,state,action)
    else:raise EngineError('STORY_ACTION_UNKNOWN')
    return {**out,'changes':changes}


def _story_integrity(state,tasks):
    errors=[];rt=state.get('engine_runtime',{}).get('story_runtime_v1')
    if not rt:return {'status':'LEGACY','errors':[]}
    try:
        if rt['schema']!='STORY_RUNTIME_V1':errors.append('SCHEMA')
        records=_scene_registry(state)['records'];taskids={r['task_id'] for bucket in ('active_tasks','queued_tasks') for r in tasks.get(bucket,[])}
        focus=rt.get('focus_scene_id')
        if focus is not None and (focus not in records or records[focus]['phase']=='closed'):errors.append('FOCUS')
        for old,binding in rt.get('legacy_viewer_bindings',{}).items():
            if not old.startswith('observer:') or not binding['viewer_id'].startswith('npc:') or not binding.get('source_ref'):errors.append('LEGACY_KNOWLEDGE_IDENTITY_ROUTE')
            _story_entity(state,binding['viewer_id'][4:],False)
        for tid,b in rt['task_scene_bindings'].items():
            if len(set(b['scene_ids']))!=len(b['scene_ids']):errors.append('BINDING_DUPLICATE:'+tid)
            live=[sid for sid in b['scene_ids'] if records[sid]['phase']!='closed']
            if live and tid not in taskids:errors.append('TASK_NOT_LIVE:'+tid)
            if len(live)>1 or any(records[sid]['task_id']!=tid for sid in b['scene_ids']):errors.append('BINDING_CONFLICT:'+tid)
        for rec in records.values():
            if rec.get('story_schema')=='STORY_SCENE_V1':
                for eid in rec.get('participants',[]):_story_entity(state,eid,False)
                if rec['scene_id'] not in rt['task_scene_bindings'][rec['task_id']]['scene_ids']:errors.append('UNBOUND_SCENE')
        for did,d in rt['decisions'].items():
            if d['status']=='pending' and did not in records[d['scene_id']]['pending_decisions']:errors.append('DECISION_LINK')
        errors+=_knowledge_integrity(state);errors+=_narrative_integrity(state)
    except Exception as ex:errors.append(str(ex))
    return {'status':'FAIL' if errors else 'PASS','errors':errors,'bound_tasks':len(rt.get('task_scene_bindings',{})),'registered_people':len(rt.get('entities',{}))}


def _story_action_schema(action):
    keys={
      'entity_register':({'entity_id','name'},{'aliases','role'}),
      'scene_create':({'scene_id','task_id','family','title'},{'participants','location_label'}),
      'scene_phase':({'scene_id','phase'},{'patrol_adapter','task_id'}),
      'scene_focus':({'scene_id'},set()),
      'fact_append':({'scene_id','fact_id','subject_id','predicate','value','epistemic','source_category'},{'confidence_basis'}),
      'fact_correct':({'scene_id','fact_id','subject_id','predicate','value','epistemic','source_category','supersedes_fact_id'},{'confidence_basis'}),
      'knowledge_disclose':({'scene_id','fact_id','viewer_id','channel','basis_event_id'},set()),
      'evidence_link':({'scene_id','fact_id','basis_event_id'},set()),
      'decision_open':({'scene_id','decision_id','prompt'},set()),
      'decision_resolve':({'scene_id','decision_id','player_action'},set()),
      'narrative_commit':({'scene_id','proposal_id','proposal'},set()),
      'narrative_rewrite':({'scene_id','proposal_id','draft_text'},set()),
      'consequence_resolve':({'scene_id','consequence_id','status'},{'reason'}),
      'experience_record':({'entry'},set()),
      'experience_revoke':({'entry_id','reason'},set())}
    if not isinstance(action,dict) or action.get('type') not in keys:raise EngineError('STORY_ACTION_UNKNOWN')
    required,optional=keys[action['type']];fields=set(action)-{'type'}
    if not required<=fields or fields-(required|optional):raise EngineError('STORY_ACTION_SCHEMA:'+action['type'])
