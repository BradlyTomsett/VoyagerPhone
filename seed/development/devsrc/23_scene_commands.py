# === VOYAGER_DEV_MODULE: scene_commands ===
_domain_targets_v1408=_domain_command_targets_v1408
_apply_domain_v1408=_apply_domain_command_v1408
_domain_post_v1408=_phase2_domain_post_mutation_validate_v1408
_run_checks_v1408=run_checks_v1408
_catalog_v1408=domain_command_catalog_v1408

for _price_kind,_price_fields in {'settle_price':('settlement_id','quote','direction','account','source_event_id'),'price_evidence_register':('evidence_id','evidence','source_event_id'),'price_policy_update':('policy_ref','unit_price','source_event_id')}.items():
    DOMAIN_PUBLIC_KINDS.add(_price_kind);DOMAIN_COMMAND_KINDS.add(_price_kind);DOMAIN_REQUIRED_FIELDS[_price_kind]=_price_fields

def _domain_command_targets(payload:dict)->list:
    extra=_batch_b_command_targets(payload)
    if extra is not None:return extra
    if payload.get('kind')=='scene_record':
        sid=payload.get('scene_id')
        if not isinstance(sid,str) or not SCENE_ID_RE.fullmatch(sid):raise EngineError('SCENE_ID_INVALID')
        out=['state:engine_runtime.scene_registry_v1.records.'+sid]
        if payload.get('task_id')==_PATROL_TASK_ID:
            out+=['tasks:task:'+_PATROL_TASK_ID,'state:'+SCENE_PATROL_PATH+'.current_local_event']
        return out
    return _domain_targets_v1408(payload)

def _scene_domain_record(state:dict,tasks:dict,payload:dict)->dict:
    sid=payload['scene_id'];action=payload['scene_action'];reg=_scene_registry(state);records=reg['records']
    if action not in {'create','advance','close','reveal'}:raise EngineError('SCENE_ACTION_INVALID')
    if sid in reg['legacy_closed']:raise EngineError('SCENE_TERMINAL_ID_REUSE_FORBIDDEN')
    now=state.get('game_time');changes=[]
    if action=='create':
        if sid in records:raise EngineError('SCENE_ALREADY_EXISTS')
        tid=payload.get('task_id');typ=payload.get('scene_type');title=payload.get('title');participants=payload.get('participants',[]);facts=payload.get('facts',[])
        if not isinstance(tid,str) or not tid or not any(x.get('task_id')==tid for bucket in ('active_tasks','queued_tasks') for x in tasks.get(bucket,[]) if isinstance(x,dict)):raise EngineError('SCENE_LINKED_TASK_REQUIRED')
        if tid==_PATROL_TASK_ID and get_by_path(state,SCENE_PATROL_PATH).get('current_local_event') is not None:raise EngineError('SCENE_PATROL_SLOT_OCCUPIED')
        if any(r.get('task_id')==tid and r.get('phase')!='closed' for r in records.values()):raise EngineError('SCENE_TASK_ALREADY_HAS_OPEN_SCENE')
        if not isinstance(typ,str) or not typ.strip() or len(typ)>80 or not isinstance(title,str) or not title.strip() or len(title)>200:raise EngineError('SCENE_DEFINITION_INVALID')
        if not isinstance(participants,list) or len(participants)>40 or any(not isinstance(x,str) or not x.strip() or len(x)>160 for x in participants):raise EngineError('SCENE_PARTICIPANTS_INVALID')
        if not isinstance(facts,list) or len(facts)>80:raise EngineError('SCENE_FACTS_INVALID')
        factmap={}
        for f in facts:
            if not isinstance(f,dict) or set(f)!={'fact_id','value','epistemic'} or not isinstance(f.get('fact_id'),str) or not SCENE_ID_RE.fullmatch(f['fact_id']) or not isinstance(f.get('value'),str) or not f['value'].strip() or len(f['value'])>2000 or f.get('epistemic') not in {'confirmed','rumor','hypothesis'} or f['fact_id'] in factmap:raise EngineError('SCENE_FACT_INVALID')
            factmap[f['fact_id']]=copy.deepcopy(f)
        records[sid]={'scene_id':sid,'type':typ,'title':title,'participants':participants,'task_id':tid,'phase':'proposed','status':'active','created_at':now,'facts':factmap,'disclosures':[],'pending_decisions':[]}
        if tid==_PATROL_TASK_ID:
            dossier=get_by_path(state,SCENE_PATROL_PATH);task=next(x for x in tasks['active_tasks'] if x.get('task_id')==tid)
            records[sid]['legacy_adapter_prior']={'task_phase':task.get('phase'),'task_field_status':(task.get('task_data') or {}).get('field_status'),'mission_status':dossier.get('mission_status'),'local_event_slot':dossier.get('local_event_slot'),'decision_gate':dossier.get('decision_gate'),'split_status':(dossier.get('current_split') or {}).get('status'),'split_open_local_event':(dossier.get('current_split') or {}).get('open_local_event')}
        changes.append({'target':'state:engine_runtime.scene_registry_v1.records.'+sid,'action':'create_proposed_scene'})
    else:
        rec=records.get(sid)
        if not isinstance(rec,dict):raise EngineError('SCENE_NOT_FOUND')
        patrol=rec.get('task_id')==_PATROL_TASK_ID
        if patrol and payload.get('task_id')!=_PATROL_TASK_ID:raise EngineError('SCENE_PATROL_TASK_TARGET_REQUIRED')
        phase=rec.get('phase')
        if phase=='closed':raise EngineError('SCENE_TERMINAL_CANNOT_REOPEN')
        if action=='advance':
            target=payload.get('phase')
            if target not in SCENE_TRANSITIONS.get(phase,set()) or target=='closed':raise EngineError('SCENE_STAGE_TRANSITION_INVALID')
            rec['phase']=target
            changes.append({'target':'state:engine_runtime.scene_registry_v1.records.'+sid+'.phase','action':'advance_scene'})
            if patrol:
                dossier=get_by_path(state,SCENE_PATROL_PATH);task=next(x for x in tasks['active_tasks'] if x.get('task_id')==_PATROL_TASK_ID)
                if phase=='proposed':
                    if dossier.get('current_local_event') is not None:raise EngineError('SCENE_PATROL_SLOT_OCCUPIED')
                    dossier['current_local_event']={'event_id':sid,'phase':target,'status':'open','scene_registry_ref':'state:engine_runtime.scene_registry_v1.records.'+sid}
                    dossier['local_event_slot']='occupied_scene_registry';dossier['mission_status']='patrol_active_local_scene';dossier['decision_gate']='当前场景按 scenequery 的玩家可见信息与指挥官授权处理。'
                    task['phase']='patrol_local_scene_active';task.setdefault('task_data',{})['field_status']='local_scene_active';task['task_data']['current_event_id']=sid;task['task_data']['current_event_state_path']=SCENE_PATROL_PATH+'.current_local_event'
                    dossier.setdefault('current_split',{})['status']='local_scene_active';dossier['current_split']['open_local_event']=True
                else:
                    slot=dossier.get('current_local_event')
                    if not isinstance(slot,dict) or slot.get('event_id')!=sid:raise EngineError('SCENE_PATROL_SLOT_OUT_OF_SYNC')
                    slot['phase']=target
                task['task_data']['current_event_stage']=target
                task['task_data'].update(slot_status='occupied',scene_id=sid)
                dossier.update(slot_status='occupied',scene_id=sid)
                changes.extend([{'target':'state:'+SCENE_PATROL_PATH+'.current_local_event','action':'sync_scene_phase'},{'target':'tasks:active_tasks.task:'+_PATROL_TASK_ID,'action':'sync_scene_phase'}])
        elif action=='close':
            if phase!='resolved':raise EngineError('SCENE_CLOSE_REQUIRES_RESOLVED')
            if rec.get('pending_decisions'):raise EngineError('SCENE_PENDING_DECISIONS')
            rec['phase']='closed';rec['status']='closed';rec['closed_at']=now
            changes.append({'target':'state:engine_runtime.scene_registry_v1.records.'+sid,'action':'close_scene'})
            if patrol:
                dossier=get_by_path(state,SCENE_PATROL_PATH);task=next(x for x in tasks['active_tasks'] if x.get('task_id')==_PATROL_TASK_ID)
                if not isinstance(dossier.get('current_local_event'),dict) or dossier['current_local_event'].get('event_id')!=sid:raise EngineError('SCENE_PATROL_SLOT_OUT_OF_SYNC')
                prior=rec['legacy_adapter_prior'];dossier['current_local_event']=None
                for key,source in (('mission_status','mission_status'),('local_event_slot','local_event_slot'),('decision_gate','decision_gate')):dossier[key]=prior[source]
                dossier['current_split']['status']=prior['split_status'];dossier['current_split']['open_local_event']=prior['split_open_local_event']
                task['phase']=prior['task_phase'];task['task_data']['field_status']=prior['task_field_status']
                for key in ('current_event_id','current_event_state_path','current_event_stage'):task['task_data'][key]=None
                task['task_data'].update(slot_status='empty',scene_id=None)
                dossier.update(slot_status='empty',scene_id=None)
                rec['close_receipt']={'command_id':payload['command_id'],'closed_at':now,'slot_released':True}
                changes.extend([{'target':'state:'+SCENE_PATROL_PATH+'.current_local_event','action':'release_scene_slot'},{'target':'tasks:active_tasks.task:'+_PATROL_TASK_ID,'action':'release_scene_slot'}])
        else:
            fid=payload.get('fact_id');viewer=payload.get('viewer')
            if fid not in rec.get('facts',{}):raise EngineError('SCENE_FACT_NOT_FOUND')
            if viewer!='player' and not (isinstance(viewer,str) and re.fullmatch(r'observer:[A-Za-z0-9_.:-]{1,100}',viewer)):raise EngineError('SCENE_VIEWER_INVALID')
            if any(d.get('fact_id')==fid and d.get('viewer')==viewer for d in rec['disclosures']):raise EngineError('SCENE_ALREADY_DISCLOSED')
            rec['disclosures'].append({'fact_id':fid,'viewer':viewer,'disclosed_at':now,'command_id':payload['command_id'],'basis':'verified_authorized_scene_disclosure'})
            changes.append({'target':'state:engine_runtime.scene_registry_v1.records.'+sid+'.disclosures','action':'record_verified_disclosure'})
    chk=_scene_integrity_report(state,tasks)
    if chk['status']!='PASS':raise EngineError('SCENE_POSTCHECK_FAILED:'+','.join(chk['errors'][:3]))
    return {'kind':'scene_record','scene_id':sid,'scene_action':action,'changes':changes}

def _scene_price_apply_command(stage:Path,state:dict,tasks:dict,payload:dict)->dict:
    if payload.get('kind')=='settle_price':return _pricing_domain_settle(stage,state,payload)
    if payload.get('kind')=='price_policy_update':return _pricing_update_policy(stage,state,payload)
    if payload.get('kind')=='price_evidence_register':return _pricing_register_evidence(stage,state,payload)
    if payload.get('kind')=='adjust_funds' and any(_money_units_currency(payload.get(c+'_delta',0),c) for c in ('gold','grey')):
        p=_pricing_adjust_payload(payload);return _pricing_domain_settle(stage,state,p)
    if payload.get('kind')=='scene_record':
        if payload.get('scene_action')=='create':
            payload=copy.deepcopy(payload);refs=_pricing_scene_refs(stage,payload);effect=_scene_domain_record(state,tasks,payload);state['engine_runtime']['scene_registry_v1']['records'][payload['scene_id']]['economic_fact_refs']=refs;return effect
        return _scene_domain_record(state,tasks,payload)
    return _apply_domain_v1408(stage,state,tasks,payload)

def _phase2_domain_post_mutation_validate(state:dict,tasks:dict,before_time:str)->dict:
    result=_domain_post_v1408(state,tasks,before_time);scene=_scene_integrity_report(state,tasks)
    if scene['status']!='PASS':raise EngineError('SCENE_INTEGRITY:'+','.join(scene['errors'][:3]))
    result['checks'].append('scene_lifecycle_integrity')
    if state.get('engine_runtime',{}).get('pricing_runtime'):
        _pricing_research_catalog_check(state)
        errs=_pricing_scene_integrity(state)
        if errs:raise EngineError('PRICE_SCENE_INTEGRITY:'+str(errs))
        result['checks'].append('price_policy_and_scene_integrity')
    accounts=accounts_integrity_report(state)
    if accounts['status']=='FAIL':raise EngineError('ACCOUNT_POSTCHECK:'+str(accounts['errors']))
    result['checks'].append('integer_accounts_and_game_state')
    return result

def run_checks(base:Path,full:bool=False,expected_version:Optional[str]=None,require_manifest:bool=True,parent_snapshot:Optional[dict]=None,validation_cache:Optional[dict]=None)->dict:
    out=_run_checks_v1408(base,full,expected_version,require_manifest,parent_snapshot,validation_cache)
    try:
        state=read_json(Path(base)/'state.json');tasks=read_json(Path(base)/'tasks.json')
        if parse_version(str(read_json(Path(base)/'manifest.json').get('save_version','V0.0')))>=(14,9):
            scene=_scene_integrity_report(state,tasks);out['scene_integrity']=scene
            out['errors'].extend('SCENE:'+e for e in scene['errors'])
            if parent_snapshot and parent_snapshot.get('dir'):
                parent=Path(parent_snapshot['dir']);previous=read_json(parent/'state.json')
                oldreg=((previous.get('engine_runtime') or {}).get('scene_registry_v1') or {})
                if oldreg.get('schema')==SCENE_REGISTRY_SCHEMA:
                    newreg=_scene_registry(state)
                    if oldreg.get('legacy_closed')!=newreg.get('legacy_closed'):out['errors'].append('SCENE_LEGACY_INDEX_IMMUTABLE')
                    for sid,rec in (oldreg.get('records') or {}).items():
                        if rec.get('phase')=='closed' and (newreg.get('records') or {}).get(sid)!=rec:out['errors'].append('SCENE_TERMINAL_RECORD_CHANGED:'+sid)
                    for sid,ref in (oldreg.get('legacy_closed') or {}).items():
                        if _scene_legacy_record(previous,ref)!=_scene_legacy_record(state,ref):out['errors'].append('SCENE_SEALED_LEGACY_FACT_CHANGED:'+sid)
    except Exception as ex:out['errors'].append('SCENE_INTEGRITY_EXCEPTION:'+type(ex).__name__+':'+str(ex))
    _pricing_finish_checks(base,out,parent_snapshot)
    out['errors']=sorted(set(out['errors']));out['error_count']=len(out['errors']);out['status']='FAIL' if out['errors'] else 'PASS'
    return out

def domain_command_catalog(base:Path=ROOT)->dict:
    p=_catalog_v1408(base)
    p['queries']+=['sceneindex','scenequery','startup','pricequery','pricequote']
    for key in ('settle_price','price_evidence_register','price_policy_update'):
        p['kinds'][key]['authorization']='existing verified machine_grant for exact targets, plus typed confirmed event; quote_id is not authorization'
    p['price_contract']={'readonly':['pricequery','pricequote'],'settlement':'invoke kind=settle_price; completed transaction cash leg only, existing asset/disposal rules still required','estimates':'never cash','policy_update':'typed confirmed policy event + scoped grant; current research only'}
    p['kinds']['scene_record']={'required_fields':{'scene_id':'stable scene ID','scene_action':'create | advance | close | reveal'},'optional_fields':{'create':'task_id, scene_type, title, participants, facts (private until explicit disclosure)','advance':'phase','reveal':'fact_id, viewer (player | observer:<id>)'},'authorization':'standing_authorization with verified machine_grant for exact scene record target','result':'DOMAIN_COMMAND_RESULT_V2'}
    p['aliases']['记录场景']='scene_record'
    p['visibility']={'default':'player','gm':'--audience gm --gm-context diagnostic with VOYAGER_DEVELOPER_MODE=1','unclassified_query':'VISIBILITY_UNCLASSIFIED_QUERY; no broad fallback'}
    return p



def _apply_domain_command(stage:Path,state:dict,tasks:dict,payload:dict)->dict:
    return _batch_b_apply_command(stage,state,tasks,payload,_scene_price_apply_command)
