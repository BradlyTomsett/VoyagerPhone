# === VOYAGER_DEV_MODULE: scene_visibility ===
def _scene_registry(state:dict)->dict:
    reg=((state.get('engine_runtime') or {}).get('scene_registry_v1'))
    if not isinstance(reg,dict) or reg.get('schema')!=SCENE_REGISTRY_SCHEMA:
        raise EngineError('SCENE_REGISTRY_MISSING_OR_INVALID')
    return reg

def _scene_legacy_record(state:dict,ref:dict)->dict:
    path=ref.get('source_path')
    if not isinstance(path,str) or not path.startswith(SCENE_PATROL_PATH+'.recent_closed_events.'):
        raise EngineError('SCENE_LEGACY_REFERENCE_INVALID')
    try:rec=get_by_path(state,path)
    except KeyError as ex:raise EngineError('SCENE_LEGACY_REFERENCE_MISSING') from ex
    if not isinstance(rec,dict) or rec.get('event_id')!=ref.get('scene_id'):
        raise EngineError('SCENE_LEGACY_REFERENCE_MISMATCH')
    if not (str(rec.get('status') or '').startswith('closed') or rec.get('closed_at')):
        raise EngineError('SCENE_LEGACY_NOT_TERMINAL')
    return rec

def _scene_integrity_report(state:dict,tasks:dict)->dict:
    errors=[]
    try:reg=_scene_registry(state)
    except EngineError as ex:return {'status':'FAIL','errors':[str(ex)]}
    legacy=reg.get('legacy_closed') or {};records=reg.get('records') or {}
    if not isinstance(legacy,dict) or not isinstance(records,dict):return {'status':'FAIL','errors':['SCENE_INDEX_SHAPE_INVALID']}
    task_ids={t.get('task_id') for bucket in ('active_tasks','queued_tasks') for t in tasks.get(bucket,[]) if isinstance(t,dict)}
    terminal_ids=set(task_ids)
    for bucket in ('recent_completed_tasks','completed_tasks','cancelled_tasks'):
        values=tasks.get(bucket,[])
        values=values.values() if isinstance(values,dict) else values
        terminal_ids.update(t.get('task_id') for t in values if isinstance(t,dict))
    terminal_ids.update((state.get('engine_runtime',{}).get('task_registry_v1') or {}).keys())
    nonterminal={}
    for sid,ref in legacy.items():
        try:
            if not SCENE_ID_RE.fullmatch(sid) or ref.get('scene_id')!=sid:raise EngineError('SCENE_LEGACY_ID_INVALID')
            _scene_legacy_record(state,ref)
        except (EngineError,TypeError) as ex:errors.append(str(ex)+':'+str(sid))
    for sid,rec in records.items():
        if sid in legacy or not SCENE_ID_RE.fullmatch(str(sid)) or not isinstance(rec,dict) or rec.get('scene_id')!=sid:
            errors.append('SCENE_RECORD_ID_INVALID:'+str(sid));continue
        phase=rec.get('phase');status=rec.get('status');tid=rec.get('task_id')
        independent=tid is None and rec.get('story_schema')=='STORY_SCENE_V2' and rec.get('location_ref') in state.get('entity_registry',{}).get('entities',{})
        if phase not in SCENE_PHASES or status!=('closed' if phase=='closed' else 'active') or (not independent and tid not in (terminal_ids if phase=='closed' else task_ids)):errors.append('SCENE_RECORD_LIFECYCLE_INVALID:'+sid)
        if phase!='closed' and not independent:nonterminal.setdefault(tid,[]).append(sid)
        if phase=='closed' and not rec.get('closed_at'):errors.append('SCENE_CLOSED_AT_MISSING:'+sid)
        facts=rec.get('facts') or {};disclosures=rec.get('disclosures') or []
        if not isinstance(facts,dict) or not isinstance(disclosures,list):errors.append('SCENE_KNOWLEDGE_SHAPE_INVALID:'+sid);continue
        for fid,f in facts.items():
            if not isinstance(f,dict) or f.get('fact_id')!=fid or f.get('epistemic') not in {'confirmed','rumor','hypothesis'}:
                errors.append('SCENE_FACT_INVALID:'+sid+':'+str(fid))
        for d in disclosures:
            if not isinstance(d,dict) or d.get('fact_id') not in facts or (d.get('viewer')!='player' and not re.fullmatch(r'observer:[A-Za-z0-9_.:-]{1,100}',str(d.get('viewer') or ''))):errors.append('SCENE_DISCLOSURE_INVALID:'+sid)
    for tid,ids in nonterminal.items():
        if len(ids)>1:errors.append('SCENE_MULTIPLE_OPEN_FOR_TASK:'+str(tid))
    dossier=get_by_path(state,SCENE_PATROL_PATH);slot=dossier.get('current_local_event')
    if isinstance(slot,dict) and slot.get('event_id') in legacy:errors.append('SCENE_CLOSED_ID_REOPENED')
    patrol_native=[(sid,records[sid]) for sid in nonterminal.get(_PATROL_TASK_ID,[]) if records[sid].get('phase')!='proposed']
    if patrol_native:
        sid,rec=patrol_native[0]
        task=next((x for x in tasks.get('active_tasks',[]) if x.get('task_id')==_PATROL_TASK_ID),None)
        data=(task or {}).get('task_data') or {}
        if not isinstance(slot,dict) or slot.get('event_id')!=sid or authoritative_event_stage(slot)!=authoritative_event_stage(rec) or data.get('current_event_id')!=sid or data.get('current_event_stage')!=rec.get('phase'):
            errors.append('SCENE_PATROL_ADAPTER_OUT_OF_SYNC')
    elif isinstance(slot,dict) and slot.get('scene_registry_ref'):
        errors.append('SCENE_PATROL_ORPHANED_SLOT')
    return {'status':'FAIL' if errors else 'PASS','errors':errors,'legacy_closed_count':len(legacy),'native_count':len(records)}

def _scene_viewer(audience:str,observer_id:Optional[str],gm_context:Optional[str])->str:
    if audience=='gm':
        if gm_context!='diagnostic' or os.environ.get('VOYAGER_DEVELOPER_MODE')!='1':raise EngineError('VISIBILITY_GM_DIAGNOSTIC_CONTEXT_REQUIRED')
        return 'gm'
    if audience=='observer':
        if not isinstance(observer_id,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}',observer_id):raise EngineError('VISIBILITY_OBSERVER_ID_REQUIRED')
        return 'observer:'+observer_id
    if audience!='player':raise EngineError('VISIBILITY_AUDIENCE_INVALID')
    if observer_id or gm_context:raise EngineError('VISIBILITY_CONTEXT_MISMATCH')
    return 'player'

def _scene_current_summary(state:dict)->dict:
    reg=_scene_registry(state)
    live=[{'scene_id':sid,'phase':r['phase'],'task_id':r['task_id']} for sid,r in (reg.get('records') or {}).items() if r.get('phase') not in (None,'closed','proposed')]
    slot=get_by_path(state,SCENE_PATROL_PATH).get('current_local_event')
    if isinstance(slot,dict):live.append({'scene_id':slot.get('event_id'),'phase':authoritative_event_stage(slot),'task_id':_PATROL_TASK_ID})
    live=list({r['scene_id']:r for r in live if r.get('scene_id')}.values())
    if len(live)>1:raise EngineError('SCENE_CURRENT_AMBIGUOUS')
    return live[0] if live else {'scene_id':None,'phase':None,'task_id':None,'status':'NO_OPEN_SCENE'}

def scene_query_packet(base:Path,scene_id:str,audience:str='player',observer_id:Optional[str]=None,gm_context:Optional[str]=None)->dict:
    viewer=_scene_viewer(audience,observer_id,gm_context);base=Path(base).resolve();ready=ensure_source_ready(base)
    state=read_json_view(base/'state.json');reg=_scene_registry(state)
    if not isinstance(scene_id,str) or not SCENE_ID_RE.fullmatch(scene_id):raise EngineError('SCENE_ID_INVALID')
    rec=(reg.get('records') or {}).get(scene_id);legacy=(reg.get('legacy_closed') or {}).get(scene_id)
    if viewer.startswith('observer:'):
        if legacy is not None or not isinstance(rec,dict) or not any(d.get('viewer')==viewer for d in rec.get('disclosures',[])):
            return {'packet':'SCENE_QUERY_V1','status':'NOT_FOUND','scene_id':scene_id,'save_set_id':ready['save_set_id'],'viewer':viewer}
    if rec is None and legacy is None:
        slot=get_by_path(state,SCENE_PATROL_PATH).get('current_local_event')
        if not isinstance(slot,dict) or slot.get('event_id')!=scene_id:return {'packet':'SCENE_QUERY_V1','status':'NOT_FOUND','scene_id':scene_id,'save_set_id':ready['save_set_id'],'viewer':viewer}
        rec={'scene_id':scene_id,'type':'legacy_local_event','phase':authoritative_event_stage(slot),'status':'active','task_id':_PATROL_TASK_ID,'facts':{},'disclosures':[]}
        legacy_slot=slot
    else:legacy_slot=None
    if legacy is not None:
        source=_scene_legacy_record(state,legacy)
        out={'scene_id':scene_id,'type':legacy.get('type') or 'legacy_closed_event','phase':'closed','status':'closed','task_id':legacy.get('task_id'),'closed_at':source.get('closed_at'),'confirmed_facts':[],'pending_decisions':[],'knowledge_evidence':'closed_at / terminal status only; narrative disclosure unverified','source_ref':'state:'+legacy['source_path']}
        if viewer=='gm':out['world_truth']=copy.deepcopy(source)
    else:
        out={'scene_id':scene_id,'type':rec.get('type'),'phase':rec.get('phase'),'status':rec.get('status'),'task_id':rec.get('task_id'),'title':rec.get('title') if viewer=='gm' or rec.get('phase')!='proposed' else None,'participants':rec.get('participants') if viewer=='gm' else [],'confirmed_facts':[],'pending_decisions':rec.get('pending_decisions',[]) if viewer=='gm' else []}
        visible={d['fact_id'] for d in rec.get('disclosures',[]) if d.get('viewer')==viewer}
        if viewer=='gm':out['world_truth']=copy.deepcopy(legacy_slot if legacy_slot is not None else rec)
        else:
            out['confirmed_facts']=[copy.deepcopy(f) for fid,f in (rec.get('facts') or {}).items() if fid in visible]
            out['economic_fact_refs']={fid:copy.deepcopy(ref) for fid,ref in rec.get('economic_fact_refs',{}).items() if fid in visible}
            out['knowledge_evidence']='explicit_disclosure_only'
    return {'packet':'SCENE_QUERY_V1','status':'COMPLETE','save_set_id':ready['save_set_id'],'game_time':state.get('game_time'),'viewer':viewer,'value':copy.deepcopy(out)}

def scene_index_packet(base:Path,offset:int=0,limit:int=20,audience:str='player',observer_id:Optional[str]=None,gm_context:Optional[str]=None)->dict:
    viewer=_scene_viewer(audience,observer_id,gm_context)
    if not isinstance(offset,int) or offset<0 or not isinstance(limit,int) or not 1<=limit<=100:raise EngineError('SCENE_INDEX_PAGE_INVALID')
    base=Path(base).resolve();ready=ensure_source_ready(base);state=read_json_view(base/'state.json');reg=_scene_registry(state)
    rows=[{'scene_id':sid,'phase':'closed','status':'closed','task_id':ref.get('task_id')} for sid,ref in sorted(reg['legacy_closed'].items())] if not viewer.startswith('observer:') else []
    rows += [{'scene_id':sid,'phase':r['phase'],'status':r['status'],'task_id':r['task_id']} for sid,r in sorted(reg['records'].items()) if viewer=='gm' or (r['phase']!='proposed' and (viewer=='player' or any(d.get('viewer')==viewer for d in r.get('disclosures',[])) ))]
    current=_scene_current_summary(state) if not viewer.startswith('observer:') else {'scene_id':None,'phase':None,'task_id':None,'status':'NOT_DISCLOSED'}
    return {'packet':'SCENE_INDEX_V1','status':'COMPLETE','save_set_id':ready['save_set_id'],'viewer':viewer,'current':current,'total':len(rows),'offset':offset,'rows':rows[offset:offset+limit],'next_offset':offset+limit if offset+limit<len(rows) else None,'authority':'state:engine_runtime.scene_registry_v1 (references to legacy current/closed records)'}

# Public player-facing routes use an allowlist. The old broad search remains an
# explicit developer diagnostic, never a fallback after an unclassified topic.
def visible_query_packet(base:Path,topic:str,history_limit:int=5,detail:str='compact',audience:str='player',observer_id:Optional[str]=None,gm_context:Optional[str]=None)->dict:
    viewer=_scene_viewer(audience,observer_id,gm_context);base=Path(base).resolve()
    if viewer=='gm':return query_packet(base,topic,history_limit,detail=detail)
    if viewer!='player':return {'packet':'VISIBLE_QUERY_V1','status':'VISIBILITY_DENIED','topic':topic,'viewer':viewer}
    q=str(topic).strip();m=re.fullmatch(r'(?:scene|event):([A-Za-z0-9_.:-]+)',q,re.I)
    if m:return scene_query_packet(base,m.group(1))
    if _normalize_search_text(q) in ('当前场景','开放事件','当前开放事件'):
        state=read_json_view(base/'state.json');cur=_scene_current_summary(state)
        if cur['scene_id']:return scene_query_packet(base,cur['scene_id'])
        return {'packet':'SCENE_QUERY_V1','status':'NO_OPEN_SCENE','save_set_id':ensure_source_ready(base)['save_set_id'],'value':cur}
    m=re.fullmatch(r'task:([A-Za-z0-9_.:-]+)',q,re.I)
    if m:
        tid=m.group(1);tasks=read_json_view(base/'tasks.json');state=read_json_view(base/'state.json')
        row=next((t for bucket in ('active_tasks','queued_tasks') for t in tasks.get(bucket,[]) if t.get('task_id')==tid),None)
        if row is None:return {'packet':'VISIBLE_QUERY_V1','status':'NOT_FOUND','topic':topic}
        return {'packet':'VISIBLE_QUERY_V1','status':'COMPLETE','topic':topic,'save_set_id':ensure_source_ready(base)['save_set_id'],'value':{'task_id':tid,'title':row.get('title'),'status':row.get('status'),'phase':row.get('phase'),'decision_gate_open':_task_player_decision_gate_open(row),'as_of':state.get('game_time')}}
    intent,arg=_query_intent_key(q)
    allowed={'core','finance','active_tasks','queued_tasks','decision_gates','obligations','fleet_location','inventory','voyager_ship_combat'}
    if intent in allowed:
        pkt=query_intent_packet(base,q)
        if pkt and intent=='active_tasks':
            for item in pkt.get('value') or []:item.pop('resolver',None)
        return pkt
    key=_exact_alias_key(q)
    if key in {'gold','grey','game_time','voyager_ships','jinchuan_ships','shadow_ships'}:return query_packet(base,q,0,detail='exact')
    return {'packet':'VISIBLE_QUERY_V1','status':'VISIBILITY_UNCLASSIFIED_QUERY','topic':topic,'viewer':viewer,'next_queries':['startup --layer navigation','sceneindex','scenequery --id <scene_id>','assetquery --id <asset_id>','rulesaudit --rule-id <rule_id>']}

def visible_query_batch_packet(base:Path,topics:list,detail:str='compact',audience:str='player',observer_id:Optional[str]=None,gm_context:Optional[str]=None)->dict:
    if not isinstance(topics,list) or not 1<=len(topics)<=8 or any(not isinstance(x,str) or not x.strip() for x in topics):raise EngineError('QUERY_BATCH_REQUIRES_1_TO_8_TOPICS')
    base=Path(base).resolve();viewer=_scene_viewer(audience,observer_id,gm_context)
    with engine_lock(base,exclusive=True):
        before=_cached_mobile_validate_authority(base)
        if not before:raise EngineError('COMPONENT_AUTHORITY_INVALID')
        scope=_mobile_scope_from_authority(base,before);token=_mobile_read_scope.set(scope)
        try:results=[visible_query_packet(base,t,detail=detail,audience=audience,observer_id=observer_id,gm_context=gm_context) for t in topics];_mobile_read_guard(scope)
        finally:_mobile_read_scope.reset(token)
        _assert_authority_bytes_unchanged(base,before,scope)
        return {'packet':'VISIBLE_QUERY_BATCH_V1','save_set_id':before['save_set_id'],'viewer':viewer,'results':results}

def visible_evidence_packet(base:Path,source:str,path:str,offset:int=0,limit:int=4000,audience:str='player',observer_id:Optional[str]=None,gm_context:Optional[str]=None)->dict:
    viewer=_scene_viewer(audience,observer_id,gm_context)
    if viewer=='gm':return evidence_packet(base,source,path,offset,limit)
    if viewer=='player' and source=='rules':return evidence_packet(base,source,path,offset,limit)
    if viewer=='player' and source=='state' and path in {'game_time','state:game_time','summary.funds','state:summary.funds'}:return evidence_packet(base,source,path,offset,limit)
    return {'packet':'VISIBLE_EVIDENCE_V1','status':'VISIBILITY_DENIED','viewer':viewer,'source':source,'next_query':'scenequery --id <scene_id> (revealed facts only)'}

def visible_reportframe_packet(base:Path,since:Optional[str]=None,since_seq:Optional[int]=None,audience:str='player',observer_id:Optional[str]=None,gm_context:Optional[str]=None)->dict:
    viewer=_scene_viewer(audience,observer_id,gm_context)
    if viewer=='gm':return reportframe_packet(base,since,since_seq)
    if viewer!='player':return {'packet':'VISIBLE_REPORT_FRAME_V1','status':'VISIBILITY_DENIED','viewer':viewer}
    p=reportframe_packet(base,since,since_seq);f=p.get('finance') or {}
    return {'packet':'VISIBLE_REPORT_FRAME_V1','status':p['status'],'header':p['header'],'fleet_core':p['fleet_core'],'active_task_count':p['active_task_count'],'queued_task_count':p['queued_task_count'],'finance':{k:f.get(k) for k in ('coverage_status','gold_delta','grey_delta','structured_gold_subtotal','structured_grey_subtotal')},'history_query':'sceneindex / scenequery (disclosed facts only)'}

def startup_layer_packet(base:Path,layer:str='essential',offset:int=0,limit:int=20,budget_bytes:int=4096)->dict:
    if not isinstance(budget_bytes,int) or budget_bytes<512 or budget_bytes>1048576:raise EngineError('STARTUP_BUDGET_INVALID')
    base=Path(base).resolve()
    if layer=='essential':
        packet=cold_start_packet(base);packet['requested_budget_bytes']=budget_bytes
        packet['context_bytes']=len(json.dumps(packet,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
        packet['budget_exceeded']=packet['context_bytes']>budget_bytes
        return packet
    if layer=='navigation':
        rows=[{'topic':'sceneindex','source':'state:engine_runtime.scene_registry_v1'},
              {'topic':'scenequery --id <ID>','source':'state:engine_runtime.scene_registry_v1'},
              {'topic':'query task:<ID>','source':'tasks:active_tasks / queued_tasks'},
              {'topic':'query 当前金币余额','source':'state:summary.funds'},
              {'topic':'assetquery --id <ID>','source':'state:asset_ledger_v1.assets'},
              {'topic':'rulesaudit --rule-id <ID>','source':'rules:rule_registry'},
              {'topic':'commandcatalog','source':'engine:domain_command_catalog'},
              {'topic':'invoke --input <JSON>','source':'engine:verified transactional command'}]
        if offset<0 or not 1<=limit<=100:raise EngineError('STARTUP_PAGE_INVALID')
        ready=ensure_source_ready(base)
        count=min(limit,max(0,len(rows)-offset))
        while count>1:
            probe={'packet':'STARTUP_NAVIGATION_V1','save_set_id':ready['save_set_id'],'offset':offset,'rows':rows[offset:offset+count]}
            if len(json.dumps(probe,ensure_ascii=False,separators=(',',':')).encode('utf-8'))<=budget_bytes:break
            count-=1
        result={'packet':'STARTUP_NAVIGATION_V1','status':'COMPLETE','save_set_id':ready['save_set_id'],'offset':offset,'rows':rows[offset:offset+count],'next_offset':offset+count if offset+count<len(rows) else None,'budget_bytes':budget_bytes,'paging':'Required rows are paged; no silent truncation.'}
        result['budget_exceeded']=len(json.dumps(result,ensure_ascii=False,separators=(',',':')).encode('utf-8'))>budget_bytes
        return result
    if layer=='focus':
        cur=scene_index_packet(base,offset,limit);state=read_json(base/'state.json');tasks=read_json(base/'tasks.json')
        focus=cur['current'];tid=focus.get('task_id')
        if not tid:
            pending=[t for t in tasks.get('active_tasks',[]) if _task_player_decision_gate_open(t)]
            if len(pending)==1:tid=pending[0].get('task_id')
        result={'packet':'STARTUP_FOCUS_V1','status':'COMPLETE','save_set_id':cur['save_set_id'],'game_time':state.get('game_time'),'current_scene':focus,'focus_task_id':tid,'scene_index':cur,'next_queries':['scenequery --id <scene_id>' if focus.get('scene_id') else 'sceneindex','query task:<task_id>' if tid else 'query 当前任务'],'offset':offset,'budget_bytes':budget_bytes}
        while len(cur['rows'])>1 and len(json.dumps(result,ensure_ascii=False,separators=(',',':')).encode('utf-8'))>budget_bytes:
            cur['rows'].pop();cur['next_offset']=offset+len(cur['rows'])
        result['budget_exceeded']=len(json.dumps(result,ensure_ascii=False,separators=(',',':')).encode('utf-8'))>budget_bytes
        return result
    raise EngineError('STARTUP_LAYER_INVALID')

DOMAIN_PUBLIC_KINDS.add('scene_record')
DOMAIN_COMMAND_KINDS.add('scene_record')
DOMAIN_KIND_ALIASES['记录场景']='scene_record'
DOMAIN_REQUIRED_FIELDS['scene_record']=('scene_id','scene_action')
