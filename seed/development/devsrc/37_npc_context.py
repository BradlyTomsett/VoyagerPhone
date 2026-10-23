# === VOYAGER_DEV_MODULE: npc_context ===
STORY_TURN_SCHEMA='STORY_TURN_PROPOSAL_V1'
STORY_NPC_SCHEMA='NPC_STATE_V1'
_s3_previous_scene_integrity=_scene_integrity_report
_s3_previous_story_integrity=_story_integrity
_s3_previous_apply=_apply_domain_command
_s3_previous_targets=_domain_command_targets
_s3_previous_cost=_domain_authorization_cost
_s3_previous_authorization=_phase2_domain_authorization
_s3_previous_main=main
_s3_previous_context=narrative_context_packet
_s3_previous_source_report=_story_source_report


def _s3_runtime(state):
    value=state.get('engine_runtime',{}).get('story_turns_v1')
    if not isinstance(value,dict) or value.get('schema')!='STORY_TURNS_V1':raise EngineError('STORY_TURNS_EXPLICIT_MIGRATION_REQUIRED')
    return value


def _s3_entity(state,eid,person=False):
    row=state.get('entity_registry',{}).get('entities',{}).get(eid)
    if not isinstance(row,dict) or (person and row.get('entity_type')!='person'):raise EngineError('STORY_ENTITY_UNAVAILABLE')
    return row


def _s3_empty_npc(eid):
    return {'schema':STORY_NPC_SCHEMA,'entity_id':eid,'identity_ref':'state:entity_registry.entities.'+eid,'organization_ref':None,'location_ref':None,'traits':[],'goals':{},'relations':{},'memory_refs':[],'commitment_refs':[],'resource_refs':[],'revision':0,'last_event_id':None,'visibility':'self','initialization':'reference_only_unknown_fields_not_generated'}


def _s3_initial_state(state,rules):
    # No inferred personality, past event, location, relationship or knowledge.
    registry=state['entity_registry']['entities'];index={}
    mandatory={'RULE-DYNAMIC-STATE-PLACEMENT-01','RULE-RANDOM-DETERMINISM-01','RULE-INTEL-KNOWLEDGE-01','RULE-EVIDENCE-01'}
    tags={'RULE-NPC-NAMING-DIVERSITY-01':['new_person'],'RULE-NPC-NAME-DIVERSITY-01':['new_person'],'RULE-CONTACT-SENSOR-INITIATIVE-01':['contact','patrol'],'RULE-TRADE-DELIVERY-01':['trade'],'RULE-ECONOMY-01':['trade'],'RULE-FTL-01':['travel'],'RULE-SUPPLY-INVENTORY-01':['inventory'],'RULE-SHADOW-FLEET-OPS-01':['patrol']}
    for rid,row in rules['rule_registry']['rules'].items():
        if rid in mandatory or rid in tags:
            index[rid]={'tags':tags.get(rid,['always']),'subjects':['*'],'scene_types':['*'],'trigger':'always' if rid in mandatory else 'intent_tag','priority':100 if rid in mandatory else 50,'hard':rid in mandatory,'visibility':'player' if rid=='RULE-SHADOW-FLEET-OPS-01' else 'public_constraints','valid_from':None,'valid_until':None,'source_ref':row['source_ref'],'rule_version':row['version']}
    return {'schema':'STORY_TURNS_V1','schema_version':1,'npcs':{eid:_s3_empty_npc(eid) for eid,row in registry.items() if row['entity_type']=='person'},'turns':{},'rule_index':index,'policies':{'schema':'STORY_GAMEPLAY_POLICY_V1','patrol_one_open_scene':True,'preserve_hidden_standby':True,'automatic_scene_generation':False,'background_requires_verified_grant':True},'migration':{'reference_only':True,'no_new_people_or_learning':True}}


def _s3_identity(base):
    base=Path(base);manifest=read_json(base/'manifest.json')
    return {'save_set_id':manifest['save_set_id'],'manifest_sha256':_snapshot_sha_file(base/'manifest.json'),'engine_sha256':_snapshot_sha_file(base/'engine.py')}


_s3_view_scope=contextvars.ContextVar('voyager_trusted_session_viewer',default=None)


def _s3_viewer(viewer):
    return _knowledge_viewer(viewer,_s3_view_scope.get()==viewer or os.environ.get('VOYAGER_DEVELOPER_MODE')=='1' and os.environ.get('VOYAGER_DIAGNOSTIC_CONTEXT')=='gm')


def _s3_scene_access(state,sid,viewer,actor=None):
    _s3_viewer(viewer);rec=_story_record(state,sid,True)
    if not _story_scene_visible(state,rec,viewer):raise EngineError('STORY_CONTEXT_UNAVAILABLE')
    if actor:
        if rec['phase']=='proposed':raise EngineError('STORY_SCENE_ACTIVATION_REQUIRED')
        _s3_entity(state,actor,True)
        if actor not in rec.get('participants',[]):raise EngineError('STORY_ACTOR_NOT_PRESENT')
        _s3_presence(state,rec,actor,rec.get('presence_mode','present'))
        if viewer not in ('player','gm','npc:'+actor):raise EngineError('STORY_ACTOR_VIEWER_MISMATCH')
    return rec


def _s3_rule_content(rules,ref):
    match=re.fullmatch(r'document_segments.order=(\d+).markdown',str(ref))
    if match:
        return next((row['markdown'] for row in rules.get('document_segments',[]) if row.get('order')==int(match.group(1))),None)
    return None


def _s3_rules(state,rules,intent_tags,scene_type,actor,now,viewer='player'):
    selected=[];runtime=_s3_runtime(state)
    for rid,index in runtime['rule_index'].items():
        if index.get('visibility')=='player' and viewer not in ('player','gm'):continue
        lo=parse_iso(index.get('valid_from'));hi=parse_iso(index.get('valid_until'))
        if (lo and now<lo) or (hi and now>hi):continue
        if '*' not in index['subjects'] and actor not in index['subjects']:continue
        if '*' not in index['scene_types'] and scene_type not in index['scene_types']:continue
        if not index['hard'] and not set(index['tags'])&set(intent_tags):continue
        rule=rules['rule_registry']['rules'][rid]
        if rule['version']!=index['rule_version'] or rule['source_ref']!=index['source_ref']:raise EngineError('STORY_RULE_INDEX_NEEDS_MIGRATION')
        if rule.get('lifecycle_status') not in ('active',None):continue
        content=_s3_rule_content(rules,rule['source_ref'])
        if content is None:raise EngineError('STORY_APPLICABLE_RULE_CONTENT_UNAVAILABLE')
        selected.append({'rule_id':rid,'version':rule['version'],'hard':index['hard'],'priority':index['priority'],'source_ref':'rules:'+rule['source_ref'],'content':content,'constraints':copy.deepcopy(rule.get('constraints',[])),'authorization_requirement':rule.get('authorization_requirement')})
    return sorted(selected,key=lambda r:(not r['hard'],-r['priority'],r['rule_id']))


def _s3_public_npc(state,eid,sid,viewer):
    npc=_s3_runtime(state)['npcs'].get(eid)
    if npc is None:raise EngineError('NPC_STATE_NOT_INITIALIZED')
    visible=lambda row:viewer=='gm' or viewer in row.get('visible_to',[]) or viewer=='npc:'+eid
    # Canonical identity only for already visible participants; private biography
    # and the free-form legacy state_path are never copied into context.
    result={'entity_id':eid,'name':_s3_entity(state,eid)['canonical_name'],'revision':npc['revision'],'traits':[copy.deepcopy(r) for r in npc['traits'] if visible(r)],'goals':[copy.deepcopy(r) for r in npc['goals'].values() if visible(r)],'relations':[copy.deepcopy(r) for r in npc['relations'].values() if visible(r)]}
    if viewer in ('gm','npc:'+eid):
        result['resource_refs']=copy.deepcopy(npc['resource_refs']);result['commitment_refs']=copy.deepcopy(npc['commitment_refs'])
    return result


def prepare_turn(base=ROOT,scene_id=None,actor_id=None,viewer='player',player_intent='',intent_tags=None,budget_bytes=16384):
    if type(budget_bytes) is not int or not 1024<=budget_bytes<=131072:raise EngineError('STORY_CONTEXT_BUDGET_INVALID')
    _s3_viewer(viewer);tags=intent_tags or ['conversation']
    if not isinstance(tags,list) or len(tags)>12 or any(not isinstance(t,str) or len(t)>40 for t in tags):raise EngineError('STORY_INTENT_TAGS_INVALID')
    if not isinstance(player_intent,str) or len(player_intent)>2000:raise EngineError('STORY_PLAYER_INTENT_INVALID')
    with SnapshotContext(base):
        ensure_source_ready(base);state=read_json_view(Path(base)/'state.json');rt=_s3_runtime(state);sid=scene_id or _story_current_summary(state,viewer).get('scene_id');identity=_s3_identity(base)
        if sid is None:return {'packet':'STORY_PREPARE_V1','status':'NO_OPEN_SCENE','base_identity':identity,'viewer':viewer,'game_time':state['game_time'],'model_status':'NEEDS_AI','automatic_scene_generation':False}
        rec=_s3_scene_access(state,sid,viewer,actor_id);rules=read_json_view(Path(base)/'rules.json');facts=_knowledge_rows(state,sid,viewer)
        facts,strategy=ExtensionServices.context(base,state,sid,viewer,player_intent,facts)
        known_subjects={r.get('subject_id') for r in facts};people=[]
        # Membership is visible in a scene whose presence was explicitly disclosed.
        for eid in rec.get('participants',[]):
            if viewer=='gm' or eid==actor_id or eid in known_subjects or viewer in rec.get('participant_visibility',[]):people.append(_s3_public_npc(state,eid,sid,viewer))
        applied=_s3_rules(state,rules,tags,rec['type'],actor_id,parse_iso(state['game_time']),viewer,base=base,scene_id=sid)
        pending=[{'consequence_id':cid,'status':_s3_consequence_status(state,c),'not_before':c['not_before'],'not_after':c['not_after'],'effect_type':c['effect_type']} for cid,c in _story_runtime(state)['consequences'].items() if c['scene_id']==sid and (viewer=='gm' or viewer in c['visible_to']) and c['status'] in ('pending','waiting_ai','waiting_condition')]
        packet={'packet':'STORY_PREPARE_V1','status':'NEEDS_AI','model_status':'NEEDS_AI','base_identity':identity,'game_time':state['game_time'],'scene_id':sid,'actor_id':actor_id,'viewer':viewer,'player_intent':player_intent,'intent_tags':tags,'scene':{'type':rec['type'],'phase':rec['phase'],'title':rec.get('title'),'location_ref':rec.get('location_ref'),'task_id':rec.get('task_id')},'hard_constraints':['草稿、对白、传闻不改变世界；正式硬结果只来自已提交回执。','NPC只使用此角色已知事实；未知不是不存在。','所有机械效果须类型化、真实授权、预算和单一原子提交；重试不得重复效果或随机。','不得擅自移动、公开身份、联络第三方或触发新事件；行动须由玩法策略和真实授权核验。'],'rules':applied,'people':people,'facts':facts,'beliefs':_knowledge_claims(state,sid,viewer),'pending_consequences':pending,'basis_refs':['fact/'+sid+'/'+r['fact_id'] for r in facts],'proposal_schema':STORY_TURN_SCHEMA,'schema_query':'storyschema','budget_bytes':budget_bytes,'omitted':{}}
        packet['interaction_strategy']=strategy
        packet['content_definitions']=ExtensionServices.scene_definition(base,state,sid,viewer)
        packet['context_ref']={'schema':'STORY_CONTEXT_REF_V1',**identity,'scene_id':sid,'actor_id':actor_id,'viewer':viewer,'knowledge_revision':_repair_digest({'facts':facts,'npcs':[p['revision'] for p in people]})}
        return _s3_fit_context(packet,budget_bytes)



def _s3_scene_integrity(state,tasks):
    return _s3_previous_scene_integrity(state,tasks)


def _s3_integrity(state,tasks):
    out=_s3_previous_story_integrity(state,tasks);rt=state.get('engine_runtime',{}).get('story_turns_v1')
    if rt is None:return out
    try:
        if rt['schema']!='STORY_TURNS_V1':raise EngineError('STORY_TURNS_SCHEMA')
        for eid,npc in rt['npcs'].items():
            _s3_entity(state,eid,True)
            if npc['entity_id']!=eid or npc['schema']!=STORY_NPC_SCHEMA or type(npc['revision']) is not int or npc['revision']<0:raise EngineError('NPC_IDENTITY_OR_REVISION')
            if npc['identity_ref']!='state:entity_registry.entities.'+eid:raise EngineError('NPC_IDENTITY_REFERENCE')
            for rel in npc['relations'].values():
                _s3_entity(state,rel['target_id'])
                if rel['value'] is not None and (type(rel['value']) is not int or not -100<=rel['value']<=100):raise EngineError('NPC_RELATION_BOUNDS')
        for tid,row in rt['turns'].items():
            if row['turn_id']!=tid or row['proposal_sha256']!=_repair_digest(row['proposal']):raise EngineError('STORY_TURN_PAYLOAD_BINDING')
            if row['status']!='committed' or not row.get('source_event_id'):raise EngineError('STORY_TURN_RECEIPT_REQUIRED')
        for rid,index in rt['rule_index'].items():
            if not isinstance(index.get('tags'),list) or not index.get('source_ref'):raise EngineError('STORY_RULE_INDEX')
    except Exception as ex:out['errors'].append(str(ex))
    out['status']='FAIL' if out['errors'] else 'PASS';return out


_scene_integrity_report=_s3_scene_integrity
_story_integrity=_s3_integrity



def _s3_fit_context(packet,budget):
    def measured():
        packet['basis_refs']=['fact/'+packet['scene_id']+'/'+r['fact_id'] for r in packet['facts']]
        return _stage2_finalize_size(packet,budget)
    result=measured()
    for key in ('content_definitions','beliefs','people','facts','optional_rules'):
        if result['context_bytes']<=budget:return result
        original=[r for r in packet['rules'] if not r['hard']] if key=='optional_rules' else packet[key][:]
        if not original:continue
        # Precomputed UTF8 contributions give an initial cutoff. Exact final JSON
        # checks then find the longest fitting prefix, including omitted/ref size.
        contributions=[len(json.dumps(r,ensure_ascii=False,separators=(',',':'),default=str).encode())+1 for r in original]
        removed=0;guess=len(original)
        while guess and removed<result['context_bytes']-budget:guess-=1;removed+=contributions[guess]
        all_rules=packet['rules'][:] if key=='optional_rules' else None
        def select(n):
            if key=='optional_rules':
                keep={id(r) for r in original[:n]};packet['rules']=[r for r in all_rules if r['hard'] or id(r) in keep]
                if n<len(original):packet['omitted'][key]=[r['rule_id'] for r in reversed(original[n:])]
                else:packet['omitted'].pop(key,None)
            else:
                packet[key]=original[:n]
                if n<len(original):packet['omitted'][key]={'total':len(original),'included':n,'next_action':'increase budget or use knowledgequery with same viewer'}
                else:packet['omitted'].pop(key,None)
            return measured()
        result=select(guess);lo=guess if result['context_bytes']<=budget else 0;hi=len(original) if result['context_bytes']<=budget else guess
        best=lo
        while lo<=hi:
            mid=(lo+hi)//2;candidate=select(mid)
            if candidate['context_bytes']<=budget:best=mid;lo=mid+1
            else:hi=mid-1
        result=select(best)
    return result
