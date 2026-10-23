# === VOYAGER_DEV_MODULE: memory_experience ===
EXPERIENCE_V2_POLICY='bounded_observed_strategy_v1'
EXPERIENCE_V2_SCOPES={'retrieval','conversation','proposal'}


def _s4_memory_index(base,state,viewer):
    """Authenticated, disposable viewer-specific index, never a second truth store."""
    binding={'schema':'MEMORY_INDEX_V5','dependencies':_repair_digest({'scenes':_scene_registry(state),'facts':_story_runtime(state)['facts'],'learning':_story_runtime(state)['learning_events'],'aliases':_story_runtime(state).get('legacy_viewer_bindings',{}),'environment':_s4_xp_environment(base),'recall':state.get('engine_runtime',{}).get('living_world_v1',{}).get('profiles',{}).get(viewer[4:],{}).get('forgotten',{}) if viewer.startswith('npc:') else {}}),'viewer':viewer,'policy':'explicit_learning_only_v2'}
    name='memory_v2_'+sha256_bytes(viewer.encode())[:24]+'.json';cached=_derived_read(base,name,binding);hit=cached is not None
    if cached is None:
        rows=[]
        for sid,rec in _scene_registry(state)['records'].items():
            if not _story_scene_visible(state,rec,viewer):continue
            for fact in _knowledge_rows(state,sid,viewer):
                rows.append({'ref':'fact/'+sid+'/'+fact['fact_id'],'scene_id':sid,'entity_id':fact.get('subject_id'),'time':fact.get('valid_from'),'layer':'cold' if rec['phase']=='closed' else 'retrievable','value':fact.get('value'),'epistemic':fact['epistemic'],'sources':fact.get('source_event_ids',[]),'acquired_from':fact.get('acquired_from',[])})
        cached={'rows':rows,'source_interval':{'first':min((str(r['time']) for r in rows),default=None),'last':max((str(r['time']) for r in rows),default=None)},'method':'exact authorized fact projection; no generated omniscient summary'}
        cached['by_scene']={};cached['by_entity']={}
        for i,row in enumerate(rows):
            cached['by_scene'].setdefault(row['scene_id'],[]).append(i)
            if isinstance(row.get('entity_id'),str):cached['by_entity'].setdefault(row['entity_id'],[]).append(i)
        _derived_write(base,name,binding,cached)
    return copy.deepcopy(cached),hit


def _s4_memory_search(base,viewer,query='',entity_id=None,scene_id=None,layer='all',since=None,until=None,offset=0,limit=20):
    _s3_viewer(viewer)
    if layer not in ('all','retrievable','cold') or type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100 or not isinstance(query,str) or len(query)>400:raise EngineError('MEMORY_QUERY_BOUNDS')
    lo=parse_iso(since);hi=parse_iso(until)
    if since is not None and not lo or until is not None and not hi or lo and hi and lo>hi:raise EngineError('MEMORY_QUERY_TIME')
    state=read_json_view(Path(base)/'state.json');index,hit=_s4_memory_index(base,state,viewer);terms=[x.casefold() for x in query.split() if x];selected=[]
    candidates=index['by_scene'].get(scene_id,[]) if scene_id else range(len(index['rows']))
    if entity_id:
        entity_candidates=index['by_entity'].get(entity_id,[])
        candidates=[i for i in entity_candidates if not scene_id or index['rows'][i]['scene_id']==scene_id]
    for i in candidates:
        row=index['rows'][i]
        if entity_id and row['entity_id']!=entity_id or scene_id and row['scene_id']!=scene_id or layer!='all' and row['layer']!=layer:continue
        when=parse_iso(row['time'])
        if lo and (not when or when<lo) or hi and (not when or when>hi):continue
        searchable=json.dumps({'value':row['value'],'entity_id':row['entity_id']},ensure_ascii=False).casefold();score=sum(t in searchable for t in terms)
        if terms and score==0:continue
        selected.append({**row,'match_score':score})
    selected.sort(key=lambda r:(-r['match_score'],str(r['time']),r['ref']))
    page=selected[offset:offset+limit]
    # Recheck every returned stable reference against live authorized truth.
    live_scenes={sid:{f['fact_id']:f for f in _knowledge_rows(state,sid,viewer)} for sid in dict.fromkeys(r['scene_id'] for r in page)}
    for row in page:
        facts=live_scenes[row['scene_id']];fid=row['ref'].split('/')[-1];live=facts.get(fid)
        if not live or live.get('value')!=row['value'] or live.get('source_event_ids',[])!=row['sources']:raise EngineError('MEMORY_INDEX_SOURCE_MISMATCH')
    return {'packet':'MEMORY_SEARCH_V2','viewer':viewer,'base_identity':_s3_identity(base),'rows':page,'total':len(selected),'offset':offset,'next_offset':offset+limit if offset+limit<len(selected) else None,'cache_hit':hit,'source_interval':index['source_interval'],'method':index['method'],'instructions_are_data':True,'world_truth_modified':False}



def memory_search(base,viewer='player',query='',entity_id=None,scene_id=None,layer='all',since=None,until=None,offset=0,limit=20):
    with SnapshotContext(base):
        ensure_source_ready(base);return _s4_memory_search(base,viewer,query,entity_id,scene_id,layer,since,until,offset,limit)


def memory_layers(base,viewer='player'):
    _s3_viewer(viewer)
    with SnapshotContext(base):
        ensure_source_ready(base);state=read_json_view(Path(base)/'state.json');sid=_story_current_summary(state,viewer).get('scene_id');facts=_knowledge_rows(state,sid,viewer) if sid else [];hot={'game_time':state['game_time'],'scene_id':sid,'facts':facts[:20],'fact_total':len(facts),'more_facts':'memorysearch with same viewer/scene' if len(facts)>20 else None}
        if viewer=='player' or viewer=='gm':hot['five_balances']=_five_account_balances(state)
        index,hit=_s4_memory_index(base,state,viewer)
        cold=state['engine_runtime'].get('memory_layers_v1',{}).get('cold_paths',{})
        return {'packet':'MEMORY_LAYERS_V2','viewer':viewer,'base_identity':_s3_identity(base),'hot':hot,'retrievable_count':sum(r['layer']=='retrievable' for r in index['rows']),'known_cold_count':sum(r['layer']=='cold' for r in index['rows']),'legacy_redirects':sorted(cold) if viewer=='gm' else [],'cache_hit':hit,'authority':'original fields/learning events and original archives; index is deletable and authenticated','unknown_historical_permissions':'no implicit disclosure','raw_history_removed':False}



def memory_evidence(base,ref,viewer='player'):
    _s3_viewer(viewer)
    with SnapshotContext(base):
        ensure_source_ready(base);state=read_json_view(Path(base)/'state.json')
        if ref.startswith('legacy:'):
            if viewer!='gm':return {'status':'NOT_FOUND','viewer':viewer}
            return memory_read_packet(base,ref[7:],'gm')
        if ref.startswith('fact/'):
            parts=ref.split('/')
            if len(parts)!=3:return {'status':'NOT_FOUND','viewer':viewer}
            _,sid,fid=parts;rec=_scene_registry(state)['records'].get(sid)
            if not rec or not _story_scene_visible(state,rec,viewer):return {'status':'NOT_FOUND','viewer':viewer}
            fact=next((f for f in _knowledge_rows(state,sid,viewer) if f['fact_id']==fid),None)
            if not fact:return {'status':'NOT_FOUND','viewer':viewer}
            sources=[]
            for eid in fact.get('source_event_ids',[]):
                ev=history_lookup(base,event_id=eid)
                if not ev:raise EngineError('MEMORY_SOURCE_EVENT_MISSING')
                sources.append({'event_id':eid,'game_time':ev.get('game_time'),'event_sha256':_repair_digest(ev),'full_event':copy.deepcopy(ev) if viewer=='gm' else None})
            return {'status':'COMPLETE','viewer':viewer,'fact':fact,'sources':sources,'instructions_are_data':True}
        if viewer!='gm':return {'status':'NOT_FOUND','viewer':viewer}
        event=history_lookup(base,event_id=ref)
        return {'status':'COMPLETE' if event else 'NOT_FOUND','viewer':viewer,'event':event,'instructions_are_data':True}



def _s4_xp_environment(base):
    base=Path(base).resolve();catalog=read_json_view(base/'catalog.json');ctx=_snapshot_scope.get()
    def bound(name):
        # Anchor producer implementation/rules to the exact validated snapshot,
        # not to a later file replacement observed while signing a cache entry.
        return ctx.fingerprint[name] if ctx and ctx.base==base and name in ctx.fingerprint else _snapshot_sha_file(base/name)
    return {'engine_sha256':bound('engine.py'),'rules_sha256':bound('rules.json'),'active_content_sha256':_repair_digest(catalog.get('content_packages_v1',{}))}


def _s4_xp_view(base,viewer='player'):
    _s3_viewer(viewer);base=Path(base).resolve();path=base/'events.jsonl';data=path.read_bytes();head,sep,body=data.partition(b'\n');meta=strict_json_loads(head.decode('utf-8'))
    ctx=_snapshot_scope.get();proof=ctx is not None and ctx.base==base and ctx.authority is not None and ctx.fingerprint.get('events.jsonl')==sha256_bytes(data)
    manifest=ctx.manifest if ctx and ctx.base==base else _component_manifest_read(base);binding={'schema':'XP_PHYSICAL_CURSOR_V1','viewer':viewer,'engine':ctx.fingerprint['engine.py'] if ctx and ctx.base==base else _snapshot_sha_file(base/'engine.py'),'archives':_component_cold_archives(manifest),'policy':EXPERIENCE_V2_POLICY}
    name='experience_raw_v3_'+sha256_bytes(viewer.encode())[:24]+'.json';cached=_derived_read(base,name,binding);objects=[];events=None;size=len(body)
    if proof and cached is not None and type(cached.get('bytes')) is int and 0<=cached['bytes']<=size and sha256_bytes(body[:cached['bytes']])==cached.get('prefix_sha256'):
        objects=copy.deepcopy(cached['objects']);tail=body[cached['bytes']:];events=[strict_json_loads(line.decode('utf-8')) for line in tail.splitlines() if line.strip()];last=cached['last_seq']
        for event in events:
            if event.get('seq')!=last+1:events=None;break
            last=event['seq']
        if events is not None and last+1!=meta.get('next_seq'):events=None
        if events is not None:_stage2_count('experience_prefix_hits');_stage2_count('experience_tail_events')
    if events is None:
        _,events,_=read_history_view(path,_raw_bytes=data);objects=[];_stage2_count('experience_full_rebuilds')
    for event in events:
        _stage2_count('experience_events_examined');obj=(event.get('domain_effect') or {}).get('experience_v2_object')
        if not obj:continue
        command=event['domain_effect'].get('command_payload') or {}
        if event.get('authorization',{}).get('status')!='verified' or command.get('kind') not in ('experience_probe','experience_control') or _domain_payload_digest(command)!=event.get('payload_sha256'):raise EngineError('EXPERIENCE_EVIDENCE_BINDING')
        if viewer=='gm' or obj['viewer']==viewer:objects.append({'object':copy.deepcopy(obj),'event_id':event['event_id'],'time':event['game_time']})
    raw={'bytes':size,'prefix_sha256':sha256_bytes(body),'last_seq':meta['next_seq']-1,'objects':objects}
    if raw!=cached:_derived_write(base,name,binding,raw)
    records=[];revoked=set();enabled={s:True for s in EXPERIENCE_V2_SCOPES};now=parse_iso(read_json_view(base/'state.json')['game_time'])
    for row in objects:
        obj=row['object']
        if obj['op']=='revoke':revoked.add(obj['entry_id'])
        elif obj['op'] in ('enable','disable'):
            if now<=parse_iso(obj['valid_until']):enabled[obj['scope']]=obj['op']=='enable'
        else:records.append({**copy.deepcopy(obj),'source_event_id':row['event_id'],'recorded_at':row['time']})
    return {'records':records,'revoked':sorted(revoked),'enabled':enabled}


def experience_v2(base,viewer='player'):
    with SnapshotContext(base):
        ensure_source_ready(base);view=_s4_xp_view(base,viewer);environment=_s4_xp_environment(base);now=parse_iso(read_json_view(Path(base)/'state.json')['game_time']);rows=[]
        for row in view['records']:
            expiry=parse_iso(row['valid_until']);row['active']=row['entry_id'] not in view['revoked'] and expiry is not None and now<=expiry and (row['op']=='preference' or row['environment']==environment);rows.append(row)
        return {'packet':'EXPERIENCE_V2','viewer':viewer,'machine_enabled':os.environ.get('VOYAGER_EXPERIENCE','1')!='0','scope_enabled':view['enabled'],'policy_version':EXPERIENCE_V2_POLICY,'records':rows,'revoked':view['revoked'],'scope_limit':'retrieval/order/interaction hints only; no code, world, authorization, currency, RNG or content mutation','inferred_preferences':'unsupported; never inferred from NPC/game text'}



def _s4_strategy(base,viewer,scope):
    if scope not in EXPERIENCE_V2_SCOPES:raise EngineError('EXPERIENCE_SCOPE')
    view=experience_v2(base,viewer);rows=[r for r in view['records'] if r['active'] and r['scope']==scope];preferences=[r for r in rows if r['op']=='preference'];observed=[r for r in rows if r['op']=='observation'][-64:];hints=[];sources=[];failure_runs={};seen=set()
    enabled=view['machine_enabled'] and view['scope_enabled'][scope]
    if enabled:
        for row in observed:
            fp=row['observation']['input_sha256']
            if fp in seen:continue
            seen.add(fp);code=row['observation']['result_code']
            if code=='NEEDS_AUTHORIZATION':failure_runs.clear()
            elif code in ('NEEDS_INFORMATION','STALE','INVALID','UNSUPPORTED'):failure_runs.setdefault(code,[]).append(row['source_event_id'])
        choices={'NEEDS_INFORMATION':'known_basis_first','STALE':'prepare_again_before_authorization','INVALID':'validate_typed_schema_before_request','UNSUPPORTED':'ask_for_supported_mechanic'}
        for code,ids in sorted(failure_runs.items()):
            if len(ids)>=2:hints.append(choices[code]);sources+=ids[-2:]
    # Exact user feedback has priority; machine evidence can never negate it.
    preferred=preferences[-1]['preference'] if preferences else None
    return {'policy_version':EXPERIENCE_V2_POLICY,'scope':scope,'machine_enabled':enabled,'hints':hints[:3],'preferred_topic':preferred['topic'] if preferred else None,'preferred_pace':preferred['pace'] if preferences else None,'user_evidence_event':preferences[-1]['source_event_id'] if preferences else None,'machine_evidence_events':sources[:6],'input_experience_sha256':_repair_digest(rows),'max_ranking_displacement':2,'mechanical_effects':False,'counterexample':'accepted validation resets current failure run','expiry':'observations <=7 game days; user preference <=30 game days; environment change invalidates machine evidence'}


def _s4_xp_apply(stage,state,tasks,payload):
    host=_s4_host_required(payload);viewer=payload['viewer'];_s3_viewer(viewer);scope=payload['scope']
    if scope not in EXPERIENCE_V2_SCOPES:raise EngineError('EXPERIENCE_SCOPE')
    entry_id=_story_id(payload['command_id']);now=parse_iso(state['game_time']);until=parse_iso(payload['valid_until'])
    if not until or until<now:raise EngineError('EXPERIENCE_EXPIRY')
    if payload['kind']=='experience_probe':
        if until>now+dt.timedelta(days=7):raise EngineError('EXPERIENCE_OBSERVATION_WINDOW')
        probe=payload['probe'];_s3_fields(probe,{'kind','input'})
        import time
        started=time.perf_counter()
        if probe['kind']=='proposal_validation':
            if probe['input'].get('viewer')!=viewer:raise EngineError('EXPERIENCE_PROBE_VIEWER')
            result=validate_proposal(stage,probe['input']);code=result['status'];count=None
        elif probe['kind']=='memory_retrieval':
            _s3_fields(probe['input'],{'query','scene_id'});result=_s4_memory_search(stage,viewer,probe['input']['query'],scene_id=probe['input']['scene_id'],limit=10);code='RETRIEVAL_NONEMPTY' if result['rows'] else 'RETRIEVAL_EMPTY';count=len(result['rows'])
        else:raise EngineError('EXPERIENCE_PROBE_UNSUPPORTED')
        observation={'type':probe['kind'],'result_code':code,'input_sha256':_repair_digest(probe['input']),'result_sha256':_repair_digest(result),'result_count':count,'seconds':time.perf_counter()-started,'body_bytes':len(json.dumps(result,ensure_ascii=False,separators=(',',':')).encode())}
        obj={'op':'observation','entry_id':entry_id,'viewer':viewer,'scope':scope,'valid_until':until.isoformat(),'environment':_s4_xp_environment(stage),'observation':observation,'origin':'actual engine result, never model self-assessment'}
    else:
        if host.get('evidence_ref')!=payload['instruction_ref']:raise EngineError('EXPERIENCE_USER_EVIDENCE_REQUIRED')
        action=payload['control'];_s3_fields(action,{'op'}, {'entry_id','reason','feedback','preference'})
        if action['op'] not in ('preference','revoke','enable','disable'):raise EngineError('EXPERIENCE_CONTROL_UNSUPPORTED')
        if until>now+dt.timedelta(days=30):raise EngineError('EXPERIENCE_PREFERENCE_WINDOW')
        obj={'op':action['op'],'entry_id':entry_id,'viewer':viewer,'scope':scope,'valid_until':until.isoformat(),'instruction_ref':payload['instruction_ref'],'origin':'explicit authenticated user instruction'}
        if action['op']=='preference':
            _s3_fields(action['preference'],{'topic','pace'});_story_text(action['feedback'],1000);_story_text(action['preference']['topic'],80)
            if action['preference']['pace'] not in ('slow','balanced','fast'):raise EngineError('EXPERIENCE_PACE')
            obj.update(feedback=action['feedback'],preference=copy.deepcopy(action['preference']))
        elif action['op']=='revoke':
            records=_s4_xp_view(stage,viewer)
            if action['entry_id'] not in {r['entry_id'] for r in records['records'] if r['scope']==scope} or action['entry_id'] in records['revoked']:raise EngineError('EXPERIENCE_ENTRY_UNAVAILABLE')
            obj.update(entry_id=action['entry_id'],reason=_story_text(action['reason'],300))
    return {'kind':payload['kind'],'experience_v2_object':obj,'command_payload':copy.deepcopy(payload),'changes':[{'target':'events:experience_v2:'+viewer,'action':'append_evidence_or_reversible_strategy_control'}],'world_effects':False}


def _s4_xp_targets(payload):
    viewer=payload['viewer'];_s3_viewer(viewer)
    return ['events:experience_v2:'+viewer]


def _s4_context_policy(base,state,sid,viewer,intent,facts):
    strategy=_s4_strategy(base,viewer,'conversation');ordered=copy.deepcopy(facts)
    topic=strategy['preferred_topic'] or (intent if 'known_basis_first' in strategy['hints'] else None)
    if topic:
        # Stable, limited promotion of visible facts; hard rules/budget never altered.
        for i in range(len(ordered)):
            if topic.casefold() in str(ordered[i].get('value','')).casefold():
                target=max(0,i-2);ordered.insert(target,ordered.pop(i))
    return ordered,strategy


ExtensionServices.register('experience_probe',('viewer','scope','probe','valid_until'),_s4_xp_apply,_s4_xp_targets,_s4_zero_cost)
ExtensionServices.register('experience_control',('viewer','scope','control','instruction_ref','valid_until'),_s4_xp_apply,_s4_xp_targets,_s4_zero_cost)


class MemoryLayerService:
    layers=staticmethod(memory_layers)
    search=staticmethod(memory_search)
    evidence=staticmethod(memory_evidence)


class ObservedExperienceService:
    inspect=staticmethod(experience_v2)
    strategy=staticmethod(_s4_strategy)

ExperienceService.inspect_v2=staticmethod(experience_v2)
ExperienceService.strategy_v2=staticmethod(_s4_strategy)

