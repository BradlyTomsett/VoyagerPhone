# === VOYAGER_DEV_MODULE: narrative_director ===
NARRATIVE_POLICY_VERSION='bounded_director_v1'


def _narrative_soft_text(text):
    text=_story_text(text,12000)
    # Hard outcomes belong in verified engine result fields, never free prose.
    if re.search(r'(?:已(?:经)?(?:支付|收款|到账|扣款|到达|击毁|击杀|获得|转移|兑换)|\d+(?:\.\d+)?\s*(?:金币|灰币|铜币|gold|grey|战力|艘|支枪|枚手雷))',text,re.I):raise EngineError('NARRATIVE_HARD_OUTCOME_REQUIRES_VERIFIED_EFFECT')
    return text


def narrative_context_packet(base=ROOT,scene_id=None,viewer='player',budget_bytes=12000):
    if type(budget_bytes) is not int or not 1024<=budget_bytes<=65536:raise EngineError('NARRATIVE_CONTEXT_BUDGET')
    _knowledge_viewer(viewer,os.environ.get('VOYAGER_DEVELOPER_MODE')=='1' and os.environ.get('VOYAGER_DIAGNOSTIC_CONTEXT')=='gm')
    with SnapshotContext(base):
        ready=ensure_source_ready(base);state=read_json(Path(base)/'state.json');current=_story_current_summary(state,viewer)
        sid=scene_id or current.get('scene_id')
        if not sid:return {'packet':'NARRATIVE_CONTEXT_V1','status':current['status'],'focus':current,'save_set_id':ready['save_set_id']}
        if viewer!='player':_knowledge_viewer(viewer,os.environ.get('VOYAGER_DEVELOPER_MODE')=='1' and os.environ.get('VOYAGER_DIAGNOSTIC_CONTEXT')=='gm')
        rec=_story_record(state,sid)
        if not _story_scene_visible(state,rec,viewer):raise EngineError('NARRATIVE_SCENE_NOT_DISCLOSED')
        rt=_story_runtime(state);facts=_knowledge_rows(state,sid,viewer);rules=read_json(Path(base)/'rules.json')['rule_registry']['rules'];semantic=[]
        for rid,row in rules.items():
            if row.get('implementation_status')=='semantic_only' and any(token in (row.get('title','')+row.get('semantic_notes','')) for token in ('NPC','场景','叙事','命名')):semantic.append({'rule_id':rid,'version':row['version'],'title':row.get('title'),'source_ref':row['source_ref']})
        known_subjects={r.get('subject_id') for r in facts};people=[{'entity_id':eid,'name':_story_entity(state,eid)['canonical_name']} for eid in rec.get('participants',[]) if viewer=='gm' or eid in known_subjects]
        consequences=[{'consequence_id':cid,'effect_type':r['effect_type'],'status':r['status'],'cause_event_id':r['cause_event_id']} for cid,r in rt['consequences'].items() if r['scene_id']==sid and (viewer=='gm' or viewer in r['visible_to'])]
        experience=experience_packet(base);recent=[{'proposal_id':pid,'tags':p['narrative_tags']} for pid,p in list(rt['proposals'].items())[-8:]]
        known_refs=['fact/'+sid+'/'+r['fact_id'] for r in facts];packet={'packet':'NARRATIVE_CONTEXT_V1','status':'COMPLETE','base_save_set_id':ready['save_set_id'],'game_time':state['game_time'],'scene_id':sid,'viewer':viewer,'scene':{'family':rec['type'],'title':rec.get('title'),'phase':rec['phase'],'location_label':rec.get('location_label','未知')},'people':people,'facts':facts,'basis_refs':known_refs,'semantic_rules':semantic[:8],'pending_consequences':consequences,'recent_claims':_knowledge_claims(state,sid,viewer),'recent_patterns':recent,'strategy':_experience_strategy(experience,rec['type'],[tag for row in recent for tag in row['tags']]),'required_unknowns':['未披露事实不提供；新事实需授权提交；数值结果交给引擎'],'guardrails':['No world mutation from draft or query','NPC belief is not global truth','No automatic combat, spending, travel or random reroll'],'budget_bytes':budget_bytes,'paging':{}}
        # Context omission produces stable references, never silent knowledge promotion.
        for key in ('recent_patterns','semantic_rules','pending_consequences','recent_claims','facts'):
            total=len(packet[key]);remaining=total
            while len(json.dumps(packet,ensure_ascii=False,separators=(',',':')).encode())>budget_bytes and remaining>0:
                packet[key].pop();remaining-=1
            if remaining<total:packet['paging'][key]={'included':remaining,'total':total,'next_query':'knowledgequery --scene-id '+sid if key=='facts' else 'narrativecontext --scene-id '+sid+' --budget 65536'}
        packet['context_bytes']=len(json.dumps(packet,ensure_ascii=False,separators=(',',':')).encode());packet['budget_exceeded']=packet['context_bytes']>budget_bytes
        return player_output_policy(packet) if viewer!='gm' else packet


def validate_narrative_proposal(base,proposal,state=None,outer=None):
    if os.environ.get('VOYAGER_DIRECTOR','1')=='0':raise EngineError('NARRATIVE_DIRECTOR_DISABLED')
    base=Path(base);state=state or read_json(base/'state.json');rt=_story_runtime(state);manifest=read_json(base/'manifest.json')
    required={'schema','base_save_set_id','scene_id','audience','intent_ref','basis_refs','draft_text','new_facts','claims','action_requests','consequence_requests','required_unknowns','narrative_tags'}
    if not isinstance(proposal,dict) or set(proposal)!=required or proposal['schema']!='NARRATIVE_PROPOSAL_V1':raise EngineError('NARRATIVE_PROPOSAL_SCHEMA')
    if proposal['base_save_set_id']!=manifest['save_set_id']:raise EngineError('NARRATIVE_STALE_BASE')
    sid=proposal['scene_id'];rec=_story_record(state,sid,True)
    if proposal['audience']!='player' or not _story_scene_visible(state,rec,'player'):raise EngineError('NARRATIVE_AUDIENCE_OR_SCENE')
    if outer and proposal['intent_ref']!=outer['authorization_ref']:raise EngineError('NARRATIVE_INTENT_BINDING')
    _narrative_soft_text(proposal['draft_text']);rules=read_json(base/'rules.json')['rule_registry']['rules'];known=_knowledge_known(state,sid,'player')
    if not isinstance(proposal['basis_refs'],list) or not proposal['basis_refs']:raise EngineError('NARRATIVE_BASIS_REQUIRED')
    for ref in proposal['basis_refs']:
        if ref.startswith('fact/'+sid+'/'):
            if ref[len('fact/'+sid+'/'):] not in known:raise EngineError('NARRATIVE_UNKNOWN_OR_HIDDEN_FACT')
        elif ref.startswith('claim/'):
            if ref not in {r['claim_ref'] for r in _knowledge_claims(state,sid,'player')}:raise EngineError('NARRATIVE_UNKNOWN_CLAIM_REF')
        elif ref.startswith('rule:'):
            if ref[5:] not in rules:raise EngineError('NARRATIVE_RULE_NOT_REGISTERED')
        else:raise EngineError('NARRATIVE_BASIS_REF_UNSUPPORTED')
    for key in ('new_facts','claims','action_requests','consequence_requests','required_unknowns','narrative_tags'):
        if not isinstance(proposal[key],list) or len(proposal[key])>30:raise EngineError('NARRATIVE_COLLECTION_LIMIT:'+key)
    tags=proposal['narrative_tags']
    if any(not isinstance(t,str) or not re.fullmatch(r'[A-Za-z0-9_:-]{1,80}',t) for t in tags):raise EngineError('NARRATIVE_TAG_INVALID')
    for f in proposal['new_facts']:
        if set(f)!={'fact_id','subject_id','predicate','value','epistemic','source_category','confidence_basis','known_by'}:raise EngineError('NARRATIVE_NEW_FACT_SCHEMA')
        _story_entity(state,f['subject_id']);_story_id(f['fact_id'])
        if f['predicate'] not in STORY_PREDICATES:raise EngineError('NARRATIVE_MECHANICAL_FACT_FORBIDDEN')
        if f['epistemic']=='confirmed':_narrative_soft_text(f['value'])
        if not isinstance(f['known_by'],list):raise EngineError('NARRATIVE_KNOWLEDGE_LIST')
        for viewer in f['known_by']:_knowledge_viewer(viewer,True)
    for claim in proposal['claims']:
        if set(claim)!={'speaker_id','text','epistemic','basis_fact_ids'} or claim['epistemic'] not in ('rumor','hypothesis'):raise EngineError('NARRATIVE_CLAIM_NOT_WORLD_TRUTH')
        _story_entity(state,claim['speaker_id']);_story_text(claim['text'])
        speaker_known=_knowledge_known(state,sid,'npc:'+claim['speaker_id'])
        if not isinstance(claim['basis_fact_ids'],list) or not set(claim['basis_fact_ids'])<=speaker_known:raise EngineError('NARRATIVE_NPC_UNKNOWABLE_BASIS')
    verified=[]
    for req in proposal['action_requests']:
        if not isinstance(req,dict) or set(req)!={'command_id','effect_sha256'}:raise EngineError('NARRATIVE_ACTION_MUST_REFERENCE_COMMITTED_RECEIPT')
        ev=history_lookup(base,command_id=req['command_id'])
        if not ev or _repair_digest(ev.get('domain_effect'))!=req['effect_sha256']:raise EngineError('NARRATIVE_ACTION_NOT_VERIFIED')
        verified.append({'command_id':req['command_id'],'event_id':ev['event_id'],'effect_sha256':req['effect_sha256']})
    for c in proposal['consequence_requests']:
        if set(c)!={'consequence_id','subject_id','effect_type','cause_event_id','not_before','not_after','visible_to','text'} or c['effect_type'] not in ('social_response','pending_reply','scene_hook'):raise EngineError('NARRATIVE_CONSEQUENCE_DOMAIN')
        _story_id(c['consequence_id']);_story_entity(state,c['subject_id']);lo=parse_iso(c['not_before']);hi=parse_iso(c['not_after']);now=parse_iso(state['game_time'])
        if lo is None or hi is None or not now<=lo<=hi:raise EngineError('NARRATIVE_CONSEQUENCE_TIME_WINDOW')
        if not isinstance(c['visible_to'],list) or not c['visible_to']:raise EngineError('NARRATIVE_CONSEQUENCE_VISIBILITY')
        for v in c['visible_to']:_knowledge_viewer(v,True)
        cause=c['cause_event_id'];ctx=_story_scope.get()
        if cause=='$current_transaction' and ctx:cause=ctx['event_id']
        if cause!=(ctx or {}).get('event_id') and not history_lookup(base,event_id=cause):raise EngineError('NARRATIVE_CAUSE_EVENT_MISSING')
        _narrative_soft_text(c['text'])
    return {'status':'VALID','scene_id':sid,'proposal_sha256':_repair_digest(proposal),'policy_version':NARRATIVE_POLICY_VERSION,'verified_actions':verified,'hard_effects_executed':0,'authorization':'not granted by validation'}


def _narrative_action(stage,state,tasks,action):
    rt=_story_runtime(state);ctx=_story_event_context();typ=action['type'];now=state['game_time']
    if typ=='narrative_commit':
        pid=_story_id(action['proposal_id'])
        if pid in rt['proposals']:raise EngineError('NARRATIVE_PROPOSAL_ALREADY_COMMITTED')
        proposal=copy.deepcopy(action['proposal'])
        if action['scene_id']!=proposal.get('scene_id'):raise EngineError('NARRATIVE_SCENE_TARGET_MISMATCH')
        check=validate_narrative_proposal(stage,proposal,state,ctx['outer']);sid=proposal['scene_id']
        for f in proposal['new_facts']:
            p={k:v for k,v in f.items() if k!='known_by'};_knowledge_action(stage,state,tasks,{'type':'fact_append','scene_id':sid,**p})
            for viewer in f['known_by']:
                if viewer!='gm':_knowledge_action(stage,state,tasks,{'type':'knowledge_disclose','scene_id':sid,'fact_id':f['fact_id'],'viewer_id':viewer,'channel':'reported','basis_event_id':ctx['event_id']})
        for c in proposal['consequence_requests']:
            cid=c['consequence_id']
            if cid in rt['consequences']:raise EngineError('NARRATIVE_CONSEQUENCE_EXISTS')
            stored=copy.deepcopy(c)
            if stored['cause_event_id']=='$current_transaction':stored['cause_event_id']=ctx['event_id']
            rt['consequences'][cid]={**stored,'scene_id':sid,'status':'pending','created_by':ctx['event_id'],'required_authorization':'new exact consequence_resolve action','created_at':now}
        rt['proposals'][pid]={'proposal_id':pid,'scene_id':sid,'proposal':proposal,'validation':check,'narrative_tags':proposal['narrative_tags'],'status':'committed_story_only','source_event_id':ctx['event_id'],'committed_at':now,'revisions':[]}
        return {'action':typ,'proposal_id':pid,'hard_effects_executed':0,'changes':[{'target':'state:engine_runtime.story_runtime_v1','action':'commit_authorized_story_facts_and_pending_causal_edges'}]}
    if typ=='narrative_rewrite':
        pid=action['proposal_id'];row=rt['proposals'].get(pid)
        if not row:raise EngineError('NARRATIVE_PROPOSAL_NOT_FOUND')
        if action['scene_id']!=row['scene_id']:raise EngineError('NARRATIVE_SCENE_TARGET_MISMATCH')
        text=_narrative_soft_text(action['draft_text']);row['revisions'].append({'draft_text':text,'source_event_id':ctx['event_id'],'rewritten_at':now,'unchanged_effects_sha256':_repair_digest(row['validation']['verified_actions'])})
        return {'action':typ,'hard_effects_executed':0,'changes':[{'target':'state:engine_runtime.story_runtime_v1.proposals.'+pid+'.revisions','action':'rewrite_without_replaying_effects'}]}
    cid=action['consequence_id'];c=rt['consequences'].get(cid)
    if c and c.get('schema')=='STORY_CONSEQUENCE_V2':raise EngineError('STORY_V2_USE_TYPED_CONSEQUENCE_MANAGEMENT')
    if not c or c['status']!='pending':raise EngineError('NARRATIVE_CONSEQUENCE_NOT_PENDING')
    if action.get('scene_id')!=c['scene_id']:raise EngineError('NARRATIVE_CONSEQUENCE_SCENE_MISMATCH')
    status=action.get('status')
    if status not in ('delivered','cancelled','expired','missed'):raise EngineError('NARRATIVE_CONSEQUENCE_STATUS')
    lo=parse_iso(c['not_before']);hi=parse_iso(c['not_after']);at=parse_iso(now)
    if lo is None or hi is None or at is None or lo>hi:raise EngineError('NARRATIVE_CONSEQUENCE_TIME_INVALID')
    if status=='delivered' and not lo<=at<=hi:raise EngineError('NARRATIVE_CONSEQUENCE_OUTSIDE_AUTHORIZED_TIME')
    if status in ('expired','missed') and at<=hi:raise EngineError('NARRATIVE_CONSEQUENCE_NOT_EXPIRED')
    if action.get('reason') is not None:_story_text(action['reason'],500)
    c.update(status=status,resolved_at=now,resolution_event_id=ctx['event_id'],resolution_reason=action.get('reason') or ('explicit authorized cancellation' if status=='cancelled' else 'deadline elapsed without delivery' if status in ('expired','missed') else 'delivered within inclusive window'))
    return {'action':typ,'consequence_id':cid,'status':c['status'],'changes':[{'target':'state:engine_runtime.story_runtime_v1.consequences.'+cid,'action':'resolve_causal_story_consequence_only'}]}


def narrative_report_packet(base,pid):
    with SnapshotContext(base):
        ready=ensure_source_ready(base);state=read_json(Path(base)/'state.json');row=_story_runtime(state)['proposals'].get(pid)
        if not row:raise EngineError('NARRATIVE_PROPOSAL_NOT_FOUND')
        p=row['proposal'];sid=row['scene_id'];known=_knowledge_known(state,sid,'player');revisions=row['revisions'];draft=revisions[-1]['draft_text'] if revisions else p['draft_text']
        return player_output_policy({'packet':'NARRATIVE_REPORT_V1','save_set_id':ready['save_set_id'],'proposal_id':pid,'scene_id':sid,'draft_text':draft,'text_role':'approved creative scene prose; hard outcomes only in verified_results','claims':[{k:v for k,v in c.items() if k!='basis_fact_ids'} for c in p['claims']],'new_disclosed_facts':[r for r in _knowledge_rows(state,sid,'player') if r['fact_id'] in {f['fact_id'] for f in p['new_facts']}],'verified_results':row['validation']['verified_actions'],'pending_consequences':[{'consequence_id':c['consequence_id'],'status':c['status'],'effect_type':c['effect_type']} for c in _story_runtime(state)['consequences'].values() if c['created_by']==row['source_event_id'] and 'player' in c['visible_to']],'revisions':len(revisions)})


def _narrative_integrity(state):
    rt=_story_runtime(state);errors=[]
    if any(c.get('schema')=='STORY_CONSEQUENCE_V2' for c in rt['consequences'].values()):errors+=_s3_consequence_integrity(state,{})
    for pid,row in rt['proposals'].items():
        if row['proposal_id']!=pid or row['validation']['proposal_sha256']!=_repair_digest(row['proposal']) or row['validation']['hard_effects_executed']!=0:errors.append('PROPOSAL_BINDING')
    for cid,c in rt['consequences'].items():
        if c.get('schema')=='STORY_CONSEQUENCE_V2':
            # V2 uses its own strict contract, timing and authorization audit.
            continue
        if cid!=c['consequence_id'] or c['status'] not in ('pending','delivered','cancelled','expired','missed') or c['effect_type'] not in ('social_response','pending_reply','scene_hook') or not c.get('cause_event_id'):errors.append('CONSEQUENCE_CONTRACT')
        if c.get('status') in ('delivered','expired','missed'):
            lo=parse_iso(c.get('not_before'));hi=parse_iso(c.get('not_after'));at=parse_iso(c.get('resolved_at'))
            if lo is None or hi is None or at is None or lo>hi or (c['status']=='delivered' and not lo<=at<=hi) or (c['status'] in ('expired','missed') and at<=hi):errors.append('CONSEQUENCE_RESOLUTION_TIME')
    return errors
