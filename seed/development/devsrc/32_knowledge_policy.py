# === VOYAGER_DEV_MODULE: knowledge_policy ===
STORY_PREDICATES={'appearance','atmosphere','goal','social_reaction','statement','intent','route_hint'}


def _knowledge_key(sid,fid):return _story_id(sid)+'/'+_story_id(fid)


def _knowledge_index(state):
    owner=_stage2_cache_owner()
    if owner is None or not isinstance(state,_ReadOnlyDict):return None
    if not hasattr(owner,'proofs'):owner.proofs={}
    key=('knowledge_index_v3',id(state))
    if key in owner.proofs:return owner.proofs[key][1]
    facts={};learning={};known={};corrections={};subjects={};disclosures={};legacy_known={};aliases={};rt=_story_runtime(state)
    for old,row in rt.get('legacy_viewer_bindings',{}).items():
        aliases.setdefault(row['viewer_id'],set()).add(old);_stage2_count('knowledge_alias_bindings_indexed')
    for sid,rec in _scene_registry(state)['records'].items():
        facts[sid]={fid:{'fact_id':fid,'scene_id':sid,'value':row.get('value',row.get('text')),'epistemic':row['epistemic'],'valid_from':row.get('valid_from',row.get('as_of',rec.get('created_at'))),'source_event_ids':copy.deepcopy(row.get('source_event_ids',[])),'legacy_record':True,'source_ref':'state:engine_runtime.scene_registry_v1.records.'+sid+'.facts.'+fid} for fid,row in rec.get('facts',{}).items()}
        for position,row in enumerate(rec.get('disclosures',[])):
            viewer=row.get('viewer');fid=row['fact_id']
            disclosures.setdefault((sid,viewer),{}).setdefault(fid,[]).append((position,row))
            legacy_known.setdefault((sid,viewer),set()).add(fid);_stage2_count('knowledge_disclosures_indexed')
    for row in rt['facts'].values():facts.setdefault(row['scene_id'],{})[row['fact_id']]=row
    for row in rt['learning_events']:
        learning.setdefault((row['scene_id'],row['viewer_id'],row['fact_id']),[]).append(row);known.setdefault((row['scene_id'],row['viewer_id']),set()).add(row['fact_id']);_stage2_count('knowledge_learning_indexed')
    for sid,rows in facts.items():
        for row in rows.values():
            subjects.setdefault((sid,row.get('subject_id')),[]).append(row['fact_id'])
            if row.get('supersedes_fact_id'):corrections.setdefault((sid,row['supersedes_fact_id']),[]).append(row['fact_id'])
    value={'facts':facts,'learning':learning,'known':known,'corrections':corrections,'subjects':subjects,'disclosures':disclosures,'legacy_known':legacy_known,'aliases':aliases,'rows':{}}
    owner.proofs[key]=(state,value);_stage2_count('knowledge_index_builds');return value


def _knowledge_facts(state,sid):
    rec=_story_record(state,sid);index=_knowledge_index(state)
    if index is not None:return copy.deepcopy(index['facts'].get(sid,{}))
    facts={}
    for fid,row in rec.get('facts',{}).items():
        facts[fid]={'fact_id':fid,'scene_id':sid,'value':row.get('value',row.get('text')),'epistemic':row['epistemic'],'valid_from':row.get('valid_from',row.get('as_of',rec.get('created_at'))),'source_event_ids':copy.deepcopy(row.get('source_event_ids',[])),'legacy_record':True,'source_ref':'state:engine_runtime.scene_registry_v1.records.'+sid+'.facts.'+fid}
    for key,row in _story_runtime(state)['facts'].items():
        if row['scene_id']==sid:facts[row['fact_id']]=copy.deepcopy(row)
    return facts


def _knowledge_known(state,sid,viewer):
    rec=_story_record(state,sid);index=_knowledge_index(state)
    if index is not None:
        viewers={viewer}
        if viewer.startswith('npc:'):viewers|={'observer:'+viewer[4:]}|index['aliases'].get(viewer,set())
        known=set(index['known'].get((sid,viewer),set()))
        for original in viewers:known.update(index['legacy_known'].get((sid,original),set()))
        return known
    known={d['fact_id'] for d in rec.get('disclosures',[]) if d.get('viewer')==viewer}
    if viewer.startswith('npc:'):
        aliases={'observer:'+viewer[4:]}
        aliases|={old for old,row in _story_runtime(state).get('legacy_viewer_bindings',{}).items() if row['viewer_id']==viewer}
        known|={d['fact_id'] for d in rec.get('disclosures',[]) if d.get('viewer') in aliases}
    known|={r['fact_id'] for r in _story_runtime(state)['learning_events'] if r['scene_id']==sid and r['viewer_id']==viewer}
    return known


def _knowledge_viewer(viewer,diagnostic=False):
    if viewer in ('player','gm'):
        if viewer=='gm' and not diagnostic:raise EngineError('GM_DIAGNOSTIC_CONTEXT_REQUIRED')
        return viewer
    if not isinstance(viewer,str) or not re.fullmatch(r'(observer|npc):[A-Za-z0-9_.:-]{1,100}',viewer):raise EngineError('KNOWLEDGE_VIEWER_INVALID')
    if viewer.startswith('npc:') and not diagnostic:raise EngineError('NPC_PRIVATE_CONTEXT_REQUIRES_GM')
    return viewer


def _knowledge_action(stage,state,tasks,action):
    rt=_story_runtime(state);sid=_story_id(action['scene_id']);rec=_story_record(state,sid);ctx=_story_event_context();typ=action['type'];now=state['game_time'];fid=_story_id(action['fact_id']);key=_knowledge_key(sid,fid);facts=_knowledge_facts(state,sid)
    if typ in ('fact_append','fact_correct'):
        _story_record(state,sid,True)
        if fid in facts:raise EngineError('KNOWLEDGE_FACT_ID_EXISTS')
        subject=action['subject_id'];_story_entity(state,subject,False);predicate=action['predicate']
        if predicate not in STORY_PREDICATES:raise EngineError('KNOWLEDGE_MECHANICAL_FACT_REQUIRES_DOMAIN_COMMAND')
        value=_story_text(action['value']);epistemic=action['epistemic'];source=action.get('source_category')
        if epistemic=='confirmed':_narrative_soft_text(value)
        if epistemic not in ('confirmed','rumor','hypothesis') or source not in ('direct_observation','npc_statement','creative_setting'):raise EngineError('KNOWLEDGE_SOURCE_OR_EPISTEMIC')
        supersedes=action.get('supersedes_fact_id')
        if typ=='fact_correct':
            if supersedes not in facts or facts[supersedes]['epistemic'] not in ('rumor','hypothesis'):raise EngineError('KNOWLEDGE_CORRECTION_REQUIRES_UNCERTAIN_ORIGINAL')
        elif supersedes:raise EngineError('KNOWLEDGE_USE_CORRECTION_ACTION')
        rt['facts'][key]={'fact_id':fid,'scene_id':sid,'subject_id':subject,'predicate':predicate,'value':value,'epistemic':epistemic,'valid_from':now,'valid_to':None,'source_category':source,'confidence_basis':_story_text(action.get('confidence_basis','explicit authorized story commitment'),500),'source_event_ids':[ctx['event_id']],'supersedes_fact_id':supersedes}
        # Facts are private until an explicit, source-backed acquisition action.
        return {'action':typ,'fact_id':fid,'changes':[{'target':'state:engine_runtime.story_runtime_v1.facts.'+key,'action':'append_fact_without_implicit_disclosure'}]}
    if fid not in facts:raise EngineError('KNOWLEDGE_FACT_NOT_FOUND')
    basis=action['basis_event_id'];basis=ctx['event_id'] if basis=='$current_transaction' else basis;event=None
    if basis!=ctx['event_id']:event=history_lookup(stage,event_id=basis)
    if basis!=ctx['event_id'] and not event:raise EngineError('KNOWLEDGE_BASIS_EVENT_MISSING')
    if typ=='evidence_link':
        if rec['phase']=='closed':raise EngineError('KNOWLEDGE_CLOSED_EVIDENCE_IMMUTABLE')
        link={'scene_id':sid,'fact_id':fid,'evidence_event_id':basis,'linked_at':now,'record_event_id':ctx['event_id']}
        if link in rt['evidence_links']:raise EngineError('KNOWLEDGE_EVIDENCE_ALREADY_LINKED')
        rt['evidence_links'].append(link);return {'action':typ,'changes':[{'target':'state:engine_runtime.story_runtime_v1.evidence_links','action':'link_original_event'}]}
    viewer=action['viewer_id'];_knowledge_viewer(viewer,True)
    if viewer=='gm':raise EngineError('KNOWLEDGE_GM_NEEDS_NO_DISCLOSURE')
    if viewer.startswith('npc:'):_story_entity(state,viewer[4:])
    if fid in _knowledge_known(state,sid,viewer):raise EngineError('KNOWLEDGE_ALREADY_KNOWN')
    if rec['phase']=='closed':
        receipts=(event or {}).get('knowledge_disclosures',[])
        if not any(x.get('scene_id')==sid and x.get('fact_id')==fid and x.get('viewer_id')==viewer for x in receipts):raise EngineError('HISTORICAL_DISCLOSURE_EVIDENCE_INSUFFICIENT')
    channel=action.get('channel')
    if channel not in ('observed','heard','reported','document'):raise EngineError('KNOWLEDGE_ACQUISITION_CHANNEL_REQUIRED')
    rt['learning_events'].append({'scene_id':sid,'fact_id':fid,'viewer_id':viewer,'learned_at':now,'channel':channel,'basis_event_id':basis,'record_event_id':ctx['event_id']})
    return {'action':typ,'viewer_id':viewer,'fact_id':fid,'changes':[{'target':'state:engine_runtime.story_runtime_v1.learning_events','action':'record_explicit_knowledge_acquisition'}]}


def _knowledge_rows(state,sid,viewer):
    index=_knowledge_index(state);rec=_story_record(state,sid)
    if index is not None and (sid,viewer) in index['rows']:
        _stage2_count('knowledge_rows_cache_hits');return copy.deepcopy(index['rows'][(sid,viewer)])
    facts=index['facts'].get(sid,{}) if index is not None else _knowledge_facts(state,sid);known=set(facts) if viewer=='gm' else _knowledge_known(state,sid,viewer);rows=[]
    aliases={viewer}
    if viewer.startswith('npc:'):
        aliases|=index['aliases'].get(viewer,set()) if index is not None else {old for old,binding in _story_runtime(state).get('legacy_viewer_bindings',{}).items() if binding['viewer_id']==viewer}
    for fid,row in facts.items():
        if fid not in known:continue
        item=copy.deepcopy(row)
        if index is not None:
            # Preserve physical disclosure order across aliases, including the old
            # distinction between implicit observer knowledge and sourced aliases.
            legacy=sorted((entry for alias in aliases for entry in index['disclosures'].get((sid,alias),{}).get(fid,[])),key=lambda entry:entry[0])
            acquired=[entry[1] for entry in legacy]
        else:acquired=[d for d in rec.get('disclosures',[]) if d.get('viewer') in aliases and d['fact_id']==fid]
        item['acquired_from']=[{'learned_at':d.get('disclosed_at'),'basis':d.get('basis'),'source_ref':'state:engine_runtime.scene_registry_v1.records.'+sid+'.disclosures','original_viewer_id':d['viewer']} for d in acquired]
        item['acquired_from'] += [copy.deepcopy(d) for d in (index['learning'].get((sid,viewer,fid),[]) if index is not None else _story_runtime(state)['learning_events']) if d['scene_id']==sid and d['fact_id']==fid and d['viewer_id']==viewer]
        corrections=[cid for cid in index['corrections'].get((sid,fid),[]) if cid in known] if index is not None else [f['fact_id'] for f in facts.values() if f.get('supersedes_fact_id')==fid and f['fact_id'] in known]
        if corrections:item['superseded_by']=corrections
        if viewer!='gm':item.pop('confidence_basis',None);item.pop('source_category',None)
        rows.append(item)
    if index is not None:index['rows'][(sid,viewer)]=_stage2_freeze(rows);_stage2_count('knowledge_rows_builds')
    return rows


def _story_scene_visible(state,rec,viewer):
    if viewer=='gm':return True
    if rec.get('source_event_id') and viewer in rec.get('visible_to',[]):return True
    if rec.get('knowledge_scope')=='explicit':return bool(_knowledge_known(state,rec['scene_id'],viewer))
    if viewer=='player':return rec['phase']!='proposed'
    return bool(_knowledge_known(state,rec['scene_id'],viewer))


def _story_current_summary(state,viewer='player'):
    rt=_story_runtime(state);records=_scene_registry(state)['records'];live=[r for r in records.values() if r['phase'] not in ('closed','proposed') and _story_scene_visible(state,r,viewer)];focus=rt['focus_scene_id']
    if focus and any(r['scene_id']==focus for r in live):
        r=records[focus];return {'scene_id':focus,'task_id':r['task_id'],'phase':r['phase'],'status':'FOCUSED'}
    return {'scene_id':None,'task_id':None,'phase':None,'status':'FOCUS_REQUIRED' if live else 'NO_OPEN_SCENE','candidates':[{'scene_id':r['scene_id'],'task_id':r['task_id'],'phase':r['phase']} for r in live]}


def _story_scene_query(base,scene_id,audience='player',observer_id=None,gm_context=None):
    viewer=_scene_viewer(audience,observer_id,gm_context)
    with SnapshotContext(base):
        ready=ensure_source_ready(base);state=read_json_view(Path(base)/'state.json');reg=_scene_registry(state);rec=reg['records'].get(scene_id)
        if rec is None:return _batch_c_scene_query(base,scene_id,audience,observer_id,gm_context)
        if not _story_scene_visible(state,rec,viewer):return {'packet':'SCENE_QUERY_V2','status':'NOT_FOUND','viewer':viewer,'save_set_id':ready['save_set_id']}
        facts=_knowledge_rows(state,scene_id,viewer);rt=_story_runtime(state)
        value={'scene_id':scene_id,'type':rec['type'],'phase':rec['phase'],'status':rec['status'],'task_id':rec['task_id'],'title':rec.get('title'),'facts':facts,'confirmed_facts':[r for r in facts if r['epistemic']=='confirmed'],'uncertain_facts':[r for r in facts if r['epistemic']!='confirmed'],'knowledge_evidence':'source-backed explicit disclosures; absent historical proof stays unknown','pending_decisions':[{'decision_id':did,'prompt':rt['decisions'][did]['prompt']} for did in rec.get('pending_decisions',[]) if did in rt['decisions'] and viewer=='player']}
        if viewer=='gm':value['world_truth']=copy.deepcopy(rec)
        return {'packet':'SCENE_QUERY_V2','status':'COMPLETE','save_set_id':ready['save_set_id'],'game_time':state['game_time'],'viewer':viewer,'value':value}


def _story_scene_index(base,offset=0,limit=20,audience='player',observer_id=None,gm_context=None):
    viewer=_scene_viewer(audience,observer_id,gm_context)
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:raise EngineError('SCENE_INDEX_PAGE_INVALID')
    with SnapshotContext(base):
        ready=ensure_source_ready(base);state=read_json_view(Path(base)/'state.json');reg=_scene_registry(state);rows=[{'scene_id':sid,'phase':r['phase'],'task_id':r['task_id']} for sid,r in sorted(reg['records'].items()) if _story_scene_visible(state,r,viewer)]
        if viewer in ('player','gm'):rows+=[{'scene_id':sid,'phase':'closed','task_id':r['task_id'],'knowledge_evidence':'historical_disclosure_unverified'} for sid,r in sorted(reg['legacy_closed'].items())]
        return {'packet':'SCENE_INDEX_V2','status':'COMPLETE','save_set_id':ready['save_set_id'],'viewer':viewer,'current':_story_current_summary(state,viewer),'total':len(rows),'offset':offset,'rows':rows[offset:offset+limit],'next_offset':offset+limit if offset+limit<len(rows) else None}


def knowledge_packet(base,sid,viewer='player'):
    diagnostic=os.environ.get('VOYAGER_DEVELOPER_MODE')=='1' and os.environ.get('VOYAGER_DIAGNOSTIC_CONTEXT')=='gm';viewer=_knowledge_viewer(viewer,diagnostic)
    with SnapshotContext(base):
        ready=ensure_source_ready(base);state=read_json_view(Path(base)/'state.json');_story_record(state,sid)
        if viewer.startswith('npc:'):_story_entity(state,viewer[4:])
        rows=_knowledge_rows(state,sid,viewer)
        return {'packet':'KNOWLEDGE_VIEW_V1','save_set_id':ready['save_set_id'],'game_time':state['game_time'],'viewer':viewer,'scene_id':sid,'facts':rows,'beliefs':[r for r in rows if r['epistemic']!='confirmed']+_knowledge_claims(state,sid,viewer),'world_truth_shared':viewer=='gm'}


def _knowledge_integrity(state):
    errors=[];rt=_story_runtime(state)
    for key,f in rt['facts'].items():
        try:
            if key!=_knowledge_key(f['scene_id'],f['fact_id']) or f['predicate'] not in STORY_PREDICATES or f['epistemic'] not in ('confirmed','rumor','hypothesis') or not f['source_event_ids']:errors.append('FACT_CONTRACT')
            _story_entity(state,f['subject_id'],False);_story_record(state,f['scene_id'])
        except Exception as ex:errors.append('FACT:'+str(ex))
    seen=set()
    for row in rt['learning_events']:
        key=(row['scene_id'],row['fact_id'],row['viewer_id'])
        if key in seen or row['fact_id'] not in _knowledge_facts(state,row['scene_id']) or not row.get('basis_event_id') or parse_iso(row['learned_at'])>parse_iso(state['game_time']):errors.append('KNOWLEDGE_ACQUISITION')
        seen.add(key)
    return errors


def player_output_policy(packet):
    # Single recursive final boundary, also used by the generated context/API routes.
    denied={'world_truth','gm_private_initial_conditions','gm_private','seed_anchor','machine_grant','standing_authorizations','hidden_truth','secret','raw_evidence','resolver','legacy_adapter_prior'}
    excluded=object()
    def walk(x):
        if isinstance(x,dict):
            if x.get('visibility')=='gm' or x.get('knowledge_scope')=='gm':return excluded
            return {k:v for k,value in x.items() if k not in denied and not k.startswith('gm_') and (v:=walk(value)) is not excluded}
        if isinstance(x,list):return [v for item in x if (v:=walk(item)) is not excluded]
        return copy.deepcopy(x)
    return walk(packet)


def _story_asset_query(base=ROOT,asset_id=None,legacy_path=None):
    with SnapshotContext(base):
        result=_batch_c_asset_query(base,asset_id,legacy_path);fields={'asset_id','asset_type_id','unit','unit_status','owner_ref','location_ref','fields','condition'};result['assets']=[{k:v for k,v in row.items() if k in fields} for row in result['assets'] if row.get('visibility')!='gm'];return player_output_policy(result)


def _story_price_query(base,request):
    request=copy.deepcopy(request)
    if request.get('audience') not in (None,'player'):raise EngineError('PUBLIC_PRICE_QUERY_AUDIENCE_REQUIRED')
    ref=str(request.get('source_ref',''))
    if any(x in ref for x in ('gm_private','story_runtime_v1.facts','seed_anchor')):raise EngineError('PRICE_PRIVATE_REFERENCE_DENIED')
    with SnapshotContext(base):return player_output_policy(_batch_c_price_query(base,request))


def _story_catalog(base=ROOT):
    out=_batch_c_command_catalog(base);out['queries']+=['knowledgequery','narrativecontext','narrativevalidate','narrativereport','experience'];return player_output_policy(out)


def _knowledge_claims(state,sid,viewer):
    rows=[]
    for pid,row in _story_runtime(state)['proposals'].items():
        if row['scene_id']!=sid:continue
        for i,claim in enumerate(row['proposal']['claims']):
            if viewer not in ('player','gm') and viewer!='npc:'+claim['speaker_id']:continue
            rows.append({'claim_ref':'claim/'+pid+'/'+str(i),'speaker_id':claim['speaker_id'],'text':claim['text'],'epistemic':claim['epistemic'],'source_event_id':row['source_event_id'],'world_truth':False})
    return rows
