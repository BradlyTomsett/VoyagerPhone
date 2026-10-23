# === VOYAGER_DEV_MODULE: story_turns ===
STORY_MECHANICAL_KINDS={'account_transfer','settle_price','transfer_asset','cancel_task','complete_task','start_travel','arrive_location'}
STORY_UPDATE_KINDS={'scene_open','scene_join','scene_focus_v2','npc_update','fact_revision','consequence_schedule','consequence_manage','fact_append','knowledge_disclose','decision_open','decision_resolve','entity_register','scene_phase','turn_rewrite'}
for _s3_kind,_s3_fields in {'story_turn':('proposal',),'story_setup':('actions',),'npc_policy':('policy_id','policy_action')}.items():
    DOMAIN_PUBLIC_KINDS.add(_s3_kind);DOMAIN_COMMAND_KINDS.add(_s3_kind);DOMAIN_REQUIRED_FIELDS[_s3_kind]=_s3_fields


def _s3_fields(value,required,optional=()):
    if not isinstance(value,dict) or not set(required)<=set(value) or set(value)-(set(required)|set(optional)):raise EngineError('STORY_TYPED_SCHEMA_INVALID')


def _s3_updates(payload):
    if payload['kind']=='story_setup':return payload['actions']
    p=payload['proposal'];return p['updates']+[{'type':'consequence_schedule',**c} for c in p['consequences']]


def _s3_child(payload,index,effect):
    if not isinstance(effect,dict) or effect.get('kind') not in STORY_MECHANICAL_KINDS:raise EngineError('STORY_MECHANICAL_CAPABILITY_UNSUPPORTED')
    forbidden={'schema','command_id','base_save_set_id','actor_id','authorization','authorization_ref','trusted','authorized','is_authorized','authorization_status'}
    if set(effect)&forbidden:raise EngineError('STORY_NESTED_AUTHORIZATION_FORBIDDEN')
    return _canonical_domain_payload({'schema':DOMAIN_COMMAND_SCHEMA,'command_id':payload['command_id'],'base_save_set_id':payload['base_save_set_id'],'actor_id':payload['actor_id'],'authorization':payload['authorization'],'authorization_ref':payload['authorization_ref'],**copy.deepcopy(effect)})


def _s3_action_targets(action):
    if not isinstance(action,dict) or action.get('type') not in STORY_UPDATE_KINDS:raise EngineError('STORY_TYPED_ACTION_UNSUPPORTED')
    typ=action['type'];sid=action.get('scene_id');out=[]
    if sid:out.append('state:engine_runtime.scene_registry_v1.records.'+_story_id(sid))
    if typ=='npc_update':out.append('state:engine_runtime.story_turns_v1.npcs.'+_story_id(action.get('entity_id')))
    elif typ=='turn_rewrite':out.append('state:engine_runtime.story_turns_v1.turns.'+_story_id(action.get('turn_id')))
    elif typ in ('consequence_schedule','consequence_manage'):
        out.append('state:engine_runtime.story_runtime_v1.consequences.'+_story_id(action.get('consequence_id')))
        if typ=='consequence_schedule':
            out.append('state:engine_runtime.story_turns_v1.npcs.'+_story_id(action.get('subject_id')))
            effect=action.get('effect',{})
            if effect.get('kind')=='learn_fact':
                out.append('state:engine_runtime.story_runtime_v1.learning_events')
                if str(effect.get('viewer_id','')).startswith('npc:'):out.append('state:engine_runtime.story_turns_v1.npcs.'+_story_id(effect['viewer_id'][4:]))
    elif typ=='scene_focus_v2':out.append('state:engine_runtime.story_runtime_v1.focus_scene_id')
    elif typ in ('scene_open','scene_join'):
        if typ=='scene_open':
            out+=['state:entity:'+_story_id(eid) for eid in action.get('participants',[])]
            out.append('state:location:'+_story_id(action.get('location_ref')))
        else:out.append('state:entity:'+_story_id(action.get('entity_id')))
        if action.get('task_id'):out.append('state:engine_runtime.story_runtime_v1.task_scene_bindings.'+_story_id(action['task_id']))
        if action.get('task_id')==_PATROL_TASK_ID:out+=['tasks:task:'+_PATROL_TASK_ID,'state:'+SCENE_PATROL_PATH+'.current_local_event']
    elif typ=='fact_revision':out.append('state:engine_runtime.story_runtime_v1.facts.'+_knowledge_key(sid,action['fact_id']))
    else:
        out+=_s3_previous_targets({'kind':'story_action','action':action})
        if typ=='knowledge_disclose' and str(action.get('viewer_id','')).startswith('npc:'):out.append('state:engine_runtime.story_turns_v1.npcs.'+_story_id(action['viewer_id'][4:]))
        if typ=='entity_register':out.append('state:engine_runtime.story_turns_v1.npcs.'+_story_id(action.get('entity_id')))
    return out


def _s3_targets(payload):
    if payload.get('kind')=='npc_policy':return ['state:standing_authorizations.'+_story_id(payload['policy_id'])]
    if payload.get('kind') not in ('story_turn','story_setup'):return _s3_previous_targets(payload)
    out=[];actions=_s3_updates(payload)
    if not isinstance(actions,list) or len(actions)>40:raise EngineError('STORY_ACTION_LIMIT')
    for action in actions:out+=_s3_action_targets(action)
    if payload['kind']=='story_turn':
        proposal=payload['proposal'];out.extend(['state:game_time','tasks:game_time','state:engine_runtime.long_horizon']);out.append('state:engine_runtime.story_turns_v1.turns.'+_story_id(proposal['turn_id']))
        if proposal.get('viewer')=='player':out.append('state:engine_runtime.living_world_v1')
        for i,effect in enumerate(proposal['effects']):out+=_s3_previous_targets(_s3_child(payload,i,effect))
    return sorted(set(out))


def _s3_cost(payload):
    if payload.get('kind')=='npc_policy':return {'uses':1,'gold_units':0,'grey_units':0,'quantity':1}
    if payload.get('kind') not in ('story_turn','story_setup'):return _s3_previous_cost(payload)
    total={'uses':1,'gold_units':0,'grey_units':0,'quantity':len(_s3_updates(payload))}
    for i,effect in enumerate(payload.get('proposal',{}).get('effects',[])):
        cost=_s3_previous_cost(_s3_child(payload,i,effect))
        for key in total:total[key]=_price_decimal(total[key])+_price_decimal(cost[key])
    return {k:int(v) if _price_decimal(v)==_price_decimal(v).to_integral_value() else _price_text(v) for k,v in total.items()}


def _s3_authorization(state,payload,consume=False):
    if payload.get('kind')=='npc_policy' and (payload.get('authorization')!='host_intent' or not _host_intent_scope.get()):raise EngineError('NPC_POLICY_TRUSTED_HOST_REQUIRED')
    if payload.get('kind') in ('story_turn','story_setup') and payload.get('authorization')=='standing_authorization':
        grant=state.get('standing_authorizations',{}).get(payload.get('authorization_ref'),{}).get('machine_grant',{})
        kinds={a['type'] for a in _s3_updates(payload)}|{e['kind'] for e in payload.get('proposal',{}).get('effects',[])}
        kinds|={a['effect']['kind'] for a in _s3_updates(payload) if a.get('type')=='consequence_schedule' and a.get('mode')=='mechanical'}
        if not kinds<=set(grant.get('action_kinds',[])):raise EngineError('STORY_AUTONOMY_ACTION_OUT_OF_SCOPE')
    return _s3_previous_authorization(state,payload,consume)


def _s3_visible_refs(state,sid,viewer):
    return {'fact/'+sid+'/'+r['fact_id'] for r in _knowledge_rows(state,sid,viewer)}


def _s3_proposal_check(base,proposal,state):
    required={'elapsed_seconds','schema','turn_id','base_identity','scene_id','actor_id','viewer','player_intent','intent_tags','basis_refs','segments','effects','updates','consequences','claims','public_reason','candidates'}
    _s3_fields(proposal,required,{'experience'})
    if proposal['schema']!=STORY_TURN_SCHEMA:raise EngineError('STORY_PROPOSAL_SCHEMA_VERSION')
    _story_id(proposal['turn_id']);sid=proposal['scene_id'];actor=proposal['actor_id'];viewer=proposal['viewer']
    if proposal['base_identity']!=_s3_identity(base):raise EngineError('STORY_PROPOSAL_STALE_BASE')
    rec=_s3_scene_access(state,sid,viewer,actor)
    for key in ('basis_refs','segments','effects','updates','consequences','claims','intent_tags','candidates'):
        if not isinstance(proposal[key],list) or len(proposal[key])>40:raise EngineError('STORY_PROPOSAL_COLLECTION_LIMIT')
    if len(proposal['effects'])>12 or len(proposal['segments'])>20:raise EngineError('STORY_PROPOSAL_EFFECT_LIMIT')
    _story_text(proposal['player_intent'],2000);_story_text(proposal['public_reason'],1000)
    actor_refs=_s3_visible_refs(state,sid,'npc:'+actor);viewer_refs=_s3_visible_refs(state,sid,viewer)
    if not set(proposal['basis_refs'])<=actor_refs&viewer_refs:raise EngineError('STORY_PROPOSAL_UNKNOWN_BASIS')
    for candidate in proposal['candidates']:_story_text(candidate,500)
    for segment in proposal['segments']:
        _s3_fields(segment,{'mode','speaker_id','text','basis_refs','receipt_refs'})
        mode=segment['mode'];speaker=segment['speaker_id']
        if mode not in ('description','dialogue','quote','rumor','hypothesis','outcome'):raise EngineError('STORY_SEGMENT_MODE_UNSUPPORTED')
        if not isinstance(segment['basis_refs'],list) or not isinstance(segment['receipt_refs'],list):raise EngineError('STORY_SEGMENT_REFERENCE_SCHEMA')
        if speaker is not None:
            if speaker not in rec['participants']:raise EngineError('STORY_SPEAKER_NOT_PRESENT')
            _s3_presence(state,rec,speaker,rec.get('presence_mode','present'))
        allowed=_s3_visible_refs(state,sid,'npc:'+speaker) if speaker else viewer_refs
        if not set(segment['basis_refs'])<=allowed&viewer_refs:raise EngineError('STORY_SEGMENT_KNOWLEDGE_DENIED')
        if mode=='outcome':
            if segment['text'] or not segment['receipt_refs']:raise EngineError('STORY_OUTCOME_ENGINE_RENDER_ONLY')
        else:
            _story_text(segment['text'],4000)
            if mode=='description':_narrative_soft_text(segment['text'])
            if segment['receipt_refs']:raise EngineError('STORY_USE_TYPED_OUTCOME_SEGMENT')
    for effect in proposal['effects']:_s3_child({'command_id':proposal['turn_id'],'base_save_set_id':proposal['base_identity']['save_set_id'],'actor_id':actor,'authorization':'standing_authorization','authorization_ref':'validation-only'},0,effect)
    for action in proposal['updates']:
        if action.get('type') not in STORY_UPDATE_KINDS or action.get('scene_id',sid)!=sid:raise EngineError('STORY_UPDATE_SCENE_OR_KIND')
        if action['type'] in ('scene_open','scene_join','entity_register','scene_focus_v2','turn_rewrite'):raise EngineError('STORY_SETUP_SEPARATE_AUTHORIZED_COMMAND_REQUIRED')
    for claim in proposal['claims']:
        _s3_fields(claim,{'receipt_ref','expected_effect'})
        if not isinstance(claim['expected_effect'],dict):raise EngineError('STORY_RECEIPT_EXPECTATION_REQUIRED')
    return rec


def validate_proposal(base,proposal,command=None):
    try:
        with SnapshotContext(base):
            ensure_source_ready(base);state=read_json(Path(base)/'state.json');_s3_proposal_check(base,proposal,state)
            # Validation is not permission and does not disclose private account
            # data by simulating an unauthorized mechanical request.
            if command is None:return {'packet':'STORY_VALIDATION_V1','status':'NEEDS_AUTHORIZATION','structurally_valid':True,'proposal_sha256':_repair_digest(proposal),'mechanical_effects_executed':0}
            if command.get('kind')!='story_turn' or command.get('proposal')!=proposal or command.get('command_id')!=proposal['turn_id'] or command.get('base_save_set_id')!=proposal['base_identity']['save_set_id']:raise EngineError('STORY_VALIDATION_COMMAND_BINDING')
            _s3_authorization(state,command)
            return {'packet':'STORY_VALIDATION_V1','status':'VALID','proposal_sha256':_repair_digest(proposal),'mechanical_effects_executed':0,'full_mechanical_revalidation':'inside commit transaction'}
    except (EngineError,TypeError,KeyError,ValueError) as ex:
        code=str(ex).split(':')[0] if isinstance(ex,EngineError) else 'STORY_TYPED_SCHEMA_INVALID'
        status='NEEDS_NARRATIVE_REVIEW' if 'NARRATIVE_REVIEW' in code else 'STALE' if 'STALE' in code else 'UNSUPPORTED' if 'UNSUPPORTED' in code else 'NEEDS_AUTHORIZATION' if any(x in code for x in ('AUTHORIZATION','AUTONOMY','INTENT','BUDGET')) else 'NEEDS_INFORMATION' if any(x in code for x in ('UNAVAILABLE','PRESENT','BASIS','KNOWLEDGE')) else 'INVALID'
        return {'packet':'STORY_VALIDATION_V1','status':status,'code':code,'mechanical_effects_executed':0}


def _s3_presence(state,rec,eid,mode):
    row=_s3_entity(state,eid,True)
    if row.get('status') not in ('active','alive',None):raise EngineError('STORY_PERSON_NOT_AVAILABLE_FOR_CONTACT')
    if mode not in ('remote','present'):raise EngineError('STORY_PRESENCE_MODE')
    if mode=='present':
        npc=_s3_runtime(state)['npcs'].get(eid)
        if not npc or npc.get('location_ref')!=rec.get('location_ref'):raise EngineError('STORY_LOCATION_NEEDS_INFORMATION')
    # A remote authorized interaction never moves an entity or reveals its
    # hidden actual location. Activation still requires the exact host/grant.


def _s3_apply_update(stage,state,tasks,action,proposal=None):
    typ=action['type'];rt=_s3_runtime(state);story=_story_runtime(state);ctx=_story_event_context();now=state['game_time'];sid=action.get('scene_id');event_id=ctx['event_id']
    if typ=='scene_open':
        _s3_fields(action,{'type','scene_id','task_id','family','title','location_ref','participants','presence_mode','visible_to'}, {'patrol_directive'})
        _story_id(sid);reg=_scene_registry(state)
        if sid in reg['records'] or sid in reg['legacy_closed']:raise EngineError('STORY_SCENE_ID_ALREADY_USED')
        loc=_s3_entity(state,action['location_ref'])
        if loc['entity_type'] not in ('location','independent_station','independent_planet','mining_site','independent_agricultural_planet'):raise EngineError('STORY_LOCATION_REFERENCE_INVALID')
        participants=action['participants']
        if not isinstance(participants,list) or not 1<=len(participants)<=40 or len(set(participants))!=len(participants):raise EngineError('STORY_PARTICIPANTS_INVALID')
        for eid in participants:_s3_presence(state,action,eid,action['presence_mode'])
        for viewer in action['visible_to']:_knowledge_viewer(viewer,True)
        if not action['visible_to']:raise EngineError('STORY_SCENE_DISCLOSURE_REQUIRED')
        tid=action['task_id']
        if tid is not None:
            if not any(t['task_id']==tid for t in tasks.get('active_tasks',[])):raise EngineError('STORY_LINKED_TASK_NOT_ACTIVE')
            if any(r.get('task_id')==tid and r['phase']!='closed' for r in reg['records'].values()):raise EngineError('SCENE_TASK_ALREADY_HAS_OPEN_SCENE')
            if tid==_PATROL_TASK_ID:
                env=_host_intent_scope.get()
                if not env or action.get('patrol_directive')!=env.get('evidence_ref'):raise EngineError('STORY_HIDDEN_STANDBY_REQUIRES_NEW_COMMANDER_DIRECTIVE')
                # Preserve the established single-event adapter, including its
                # hidden standby restoration on close.
                result=_story_action_apply(stage,state,tasks,{'type':'scene_create','scene_id':sid,'task_id':tid,'family':action['family'],'title':action['title'],'participants':participants,'location_label':loc['canonical_name']})
                rec=reg['records'][sid];rec.update(location_ref=action['location_ref'],visible_to=action['visible_to'],participant_visibility=action['visible_to'],presence_mode=action['presence_mode'],source_event_id=event_id)
                return result
        rec={'scene_id':sid,'type':_story_text(action['family'],80),'title':_story_text(action['title'],200),'participants':copy.deepcopy(participants),'task_id':tid,'phase':'proposed','status':'active','created_at':now,'facts':{},'disclosures':[],'pending_decisions':[],'story_schema':'STORY_SCENE_V2','knowledge_scope':'explicit','visible_to':copy.deepcopy(action['visible_to']),'participant_visibility':copy.deepcopy(action['visible_to']),'location_ref':action['location_ref'],'presence_mode':action['presence_mode'],'source_event_id':event_id}
        reg['records'][sid]=rec
        if tid:story['task_scene_bindings'].setdefault(tid,{'task_id':tid,'one_open_scene':True,'adapter':'generic','scene_ids':[]})['scene_ids'].append(sid)
    elif typ=='scene_join':
        _s3_fields(action,{'type','scene_id','entity_id','presence_mode','visible_to'})
        rec=_story_record(state,sid,True);_s3_presence(state,rec,action['entity_id'],action['presence_mode'])
        if action['entity_id'] in rec['participants']:raise EngineError('STORY_PARTICIPANT_ALREADY_PRESENT')
        if action['presence_mode']!=rec.get('presence_mode'):raise EngineError('STORY_PRESENCE_CHANNEL_MISMATCH')
        for viewer in action['visible_to']:_knowledge_viewer(viewer,True)
        rec['participants'].append(action['entity_id']);rec['visible_to']=sorted(set(rec.get('visible_to',[]))|set(action['visible_to']));rec.setdefault('join_events',[]).append({'entity_id':action['entity_id'],'source_event_id':event_id,'visible_to':action['visible_to']})
    elif typ=='scene_focus_v2':
        _s3_fields(action,{'type','scene_id'});_story_record(state,sid,True);story['focus_scene_id']=sid
    elif typ=='npc_update':
        _s3_fields(action,{'type','entity_id','operation','record'})
        eid=action['entity_id'];_s3_entity(state,eid,True);npc=rt['npcs'][eid];row=copy.deepcopy(action['record']);op=action['operation']
        if op=='goal':
            _s3_fields(row,{'goal_id','priority','deadline','status','preconditions','description','visible_to'})
            _story_id(row['goal_id']);_story_text(row['description'],1000)
            if type(row['priority']) is not int or not 0<=row['priority']<=100 or row['status'] not in ('pending','active','completed','cancelled'):raise EngineError('NPC_GOAL_CONTRACT')
            if row['deadline'] is not None and (parse_iso(row['deadline']) is None or parse_iso(row['deadline'])<parse_iso(now)):raise EngineError('NPC_GOAL_DEADLINE')
            if not isinstance(row['preconditions'],list):raise EngineError('NPC_GOAL_PRECONDITIONS')
            for condition in row['preconditions']:
                if not isinstance(condition,dict) or condition.get('kind') not in ('confirmed_fact','effect_receipt'):raise EngineError('NPC_GOAL_TYPED_PRECONDITION_REQUIRED')
                _s3_fields(condition,{'kind','scene_id','fact_id','viewer_id'} if condition['kind']=='confirmed_fact' else {'kind','receipt_ref','expected_effect'})
            previous=npc['goals'].get(row['goal_id'])
            if previous and previous['status'] in ('completed','cancelled'):raise EngineError('NPC_GOAL_TERMINAL_REQUIRES_NEW_ID')
            if row['status']=='completed':
                if not proposal or not previous or not previous['preconditions'] or row['preconditions']!=previous['preconditions']:raise EngineError('NPC_GOAL_COMPLETION_EVIDENCE_REQUIRED')
                for condition in previous['preconditions']:
                    if condition['kind']=='effect_receipt':
                        if _s3_receipt_effect(stage,condition['receipt_ref'],ctx.get('effects',[]),proposal,state)!=condition['expected_effect']:raise EngineError('NPC_GOAL_COMPLETION_RECEIPT_MISMATCH')
                    else:
                        facts=_knowledge_facts(state,condition['scene_id']);fact=facts.get(condition['fact_id'])
                        if not fact or fact['epistemic']!='confirmed' or condition['viewer_id']!='npc:'+eid or condition['fact_id'] not in _knowledge_known(state,condition['scene_id'],condition['viewer_id']):raise EngineError('NPC_GOAL_COMPLETION_FACT_REQUIRED')
            npc['goals'][row['goal_id']]={**row,'source_event_id':event_id,'updated_at':now}
        elif op=='relation':
            _s3_fields(row,{'target_id','relation_type','value','reason','visible_to'});_s3_entity(state,row['target_id']);_story_text(row['reason'],500)
            if row['value'] is not None and (type(row['value']) is not int or not -100<=row['value']<=100):raise EngineError('NPC_RELATION_BOUNDS')
            _story_text(row['relation_type'],80);npc['relations'][row['target_id']]={**row,'source_event_id':event_id,'updated_at':now}
        elif op=='trait':
            _s3_fields(row,{'trait_id','value','source_kind','basis_refs','visible_to'})
            if row['source_kind'] not in ('observed_now','generated_now'):raise EngineError('NPC_TRAIT_NO_INVENTED_HISTORY')
            _story_id(row['trait_id']);_story_text(row['value'],300)
            if any(t['trait_id']==row['trait_id'] for t in npc['traits']):raise EngineError('NPC_TRAIT_STABLE_ID_EXISTS')
            if row['source_kind']=='observed_now' and (not proposal or not set(row['basis_refs'])<=set(proposal['basis_refs']) or not row['basis_refs']):raise EngineError('NPC_TRAIT_VISIBLE_EVIDENCE_REQUIRED')
            if row['source_kind']=='observed_now':
                facts=_knowledge_facts(state,proposal['scene_id'])
                if any(facts.get(ref.split('/')[-1],{}).get('subject_id')!=eid or facts.get(ref.split('/')[-1],{}).get('epistemic')!='confirmed' for ref in row['basis_refs']):raise EngineError('NPC_TRAIT_SUBJECT_EVIDENCE_MISMATCH')
            npc['traits'].append({**row,'source_event_id':event_id,'created_at':now,'not_historical_fact':row['source_kind']=='generated_now'})
        else:raise EngineError('NPC_UPDATE_OPERATION_UNSUPPORTED')
        for viewer in row['visible_to']:_knowledge_viewer(viewer,True)
        npc['revision']+=1;npc['last_event_id']=event_id
    elif typ=='turn_rewrite':
        _s3_fields(action,{'type','turn_id','segments','viewer'})
        row=rt['turns'].get(action['turn_id'])
        if not row or action['viewer']!=row['viewer']:raise EngineError('STORY_REWRITE_TURN_OR_VIEWER')
        if not isinstance(action['segments'],list) or len(action['segments'])>20:raise EngineError('STORY_REWRITE_SEGMENT_LIMIT')
        for segment in action['segments']:
            _s3_fields(segment,{'mode','speaker_id','text','basis_refs','receipt_refs'})
            if not set(segment['basis_refs'])<=set(row['proposal']['basis_refs']):raise EngineError('STORY_REWRITE_NEW_KNOWLEDGE_FORBIDDEN')
            if segment['mode']=='outcome':
                if segment['text'] or not segment['receipt_refs'] or not set(segment['receipt_refs'])<={r['receipt_ref'] for r in row['verified_effects']}:raise EngineError('STORY_REWRITE_OUTCOME_UNVERIFIED')
            elif segment['mode'] in ('description','dialogue','quote','rumor','hypothesis'):
                _story_text(segment['text'],4000)
                if segment['mode']=='description':_narrative_soft_text(segment['text'])
                if segment['receipt_refs']:raise EngineError('STORY_REWRITE_RECEIPT_MODE')
            else:raise EngineError('STORY_REWRITE_MODE')
            if segment['speaker_id'] is not None and segment['speaker_id'] not in _story_record(state,row['scene_id'])['participants']:raise EngineError('STORY_REWRITE_SPEAKER')
            if segment['speaker_id'] is not None and not set(segment['basis_refs'])<=_lw_rewrite_refs(state,row,segment['speaker_id']):raise EngineError('STORY_REWRITE_SPEAKER_KNOWLEDGE_DENIED')
        row.setdefault('revisions',[]).append({'segments':copy.deepcopy(action['segments']),'source_event_id':event_id,'at':now,'unchanged_effects_sha256':_repair_digest(row['mechanical_effects'])})
    elif typ=='fact_revision':
        _s3_fields(action,{'type','scene_id','fact_id','prior_fact_id','mode','evidence_fact_id','value'})
        facts=_knowledge_facts(state,sid);old=facts.get(action['prior_fact_id']);ev=facts.get(action['evidence_fact_id'])
        if not old or not ev or action['mode'] not in ('temporal_change','correction'):raise EngineError('STORY_FACT_REVISION_EVIDENCE')
        if not proposal or {old['fact_id'],ev['fact_id']}-{r.split('/')[-1] for r in proposal['basis_refs']}:raise EngineError('STORY_FACT_REVISION_UNKNOWN_EVIDENCE')
        if ev['epistemic']!='confirmed' or ev.get('subject_id')!=old.get('subject_id') or ev.get('predicate')!=old.get('predicate') or ev['value']!=action['value']:raise EngineError('STORY_FACT_REVISION_EVIDENCE_MISMATCH')
        if not any(history_lookup(stage,event_id=eid) for eid in ev['source_event_ids']):raise EngineError('STORY_FACT_REVISION_COMMITTED_EVIDENCE_REQUIRED')
        new={'type':'fact_append','scene_id':sid,'fact_id':action['fact_id'],'subject_id':old['subject_id'],'predicate':old['predicate'],'value':action['value'],'epistemic':'confirmed','source_category':'direct_observation','confidence_basis':'controlled '+action['mode']+' using '+action['evidence_fact_id']}
        _knowledge_action(stage,state,tasks,new);stored=story['facts'][_knowledge_key(sid,action['fact_id'])];stored.update(supersedes_fact_id=old['fact_id'],change_kind=action['mode'],evidence_fact_id=ev['fact_id'])
    elif typ in ('consequence_schedule','consequence_manage'):return _s3_consequence_action(stage,state,tasks,action,proposal)
    else:
        knowledge_actor=(proposal or {}).get('actor_id') or (ctx['outer'].get('actor_id') if ctx['outer'].get('actor_id') in rt['npcs'] else None)
        if typ=='knowledge_disclose' and knowledge_actor:
            fid=action['fact_id'];actor=knowledge_actor;rec=_story_record(state,sid)
            newids={a.get('fact_id') for a in ((proposal or {}).get('updates') or ctx['outer'].get('actions',[])) if a.get('type') in ('fact_append','fact_revision')}
            if fid not in _knowledge_known(state,sid,'npc:'+actor) and fid not in newids:raise EngineError('STORY_KNOWLEDGE_SENDER_DOES_NOT_KNOW')
            recipient=action['viewer_id']
            if recipient.startswith('npc:') and recipient[4:] not in rec['participants']:raise EngineError('STORY_KNOWLEDGE_RECIPIENT_NOT_PRESENT')
            if recipient=='player' and 'player' not in rec.get('visible_to',['player']):raise EngineError('STORY_KNOWLEDGE_PLAYER_NOT_PRESENT')
            if action['basis_event_id']!='$current_transaction':
                facts=_knowledge_facts(state,sid)
                if action['basis_event_id'] not in facts.get(fid,{}).get('source_event_ids',[]):raise EngineError('STORY_KNOWLEDGE_EVIDENCE_UNRELATED')
        result=_story_action_apply(stage,state,tasks,copy.deepcopy(action))
        if typ=='entity_register':rt['npcs'][action['entity_id']]=_s3_empty_npc(action['entity_id'])
        if typ=='knowledge_disclose' and action['viewer_id'].startswith('npc:'):
            npc=rt['npcs'][action['viewer_id'][4:]];npc['memory_refs'].append({'scene_id':sid,'fact_id':action['fact_id'],'source_event_id':event_id});npc['revision']+=1;npc['last_event_id']=event_id
        return result
    return {'action':typ,'changes':[{'target':t,'action':typ} for t in _s3_action_targets(action)]}


def _s3_receipt_effect(base,ref,effects,proposal,state):
    if isinstance(ref,str) and re.fullmatch(r'effect:\d+',ref):
        index=int(ref.split(':')[1])
        if index>=len(effects):raise EngineError('STORY_RECEIPT_REFERENCE_INVALID')
        return effects[index]
    if isinstance(ref,str) and ref.startswith('command:'):
        event=history_lookup(base,command_id=ref[8:])
        if not event or not event.get('receipt') or not event.get('domain_effect'):raise EngineError('STORY_COMMITTED_RECEIPT_REQUIRED')
        prior=next((row for row in _s3_runtime(state)['turns'].values() if row['source_event_id']==event['event_id']),None)
        if prior and prior['viewer'] not in (proposal['viewer'],'player') and proposal['viewer']!='gm':raise EngineError('STORY_RECEIPT_VISIBILITY_DENIED')
        # NPCs may only reference a past result explicitly learned as an evidence
        # fact, never arbitrary command IDs discoverable through a side channel.
        if event['event_id'] not in {e for f in _knowledge_rows(state,proposal['scene_id'],'npc:'+proposal['actor_id']) for e in f.get('source_event_ids',[])}:raise EngineError('STORY_RECEIPT_KNOWLEDGE_REQUIRED')
        return event['domain_effect']
    raise EngineError('STORY_COMMITTED_RECEIPT_REQUIRED')


def _s3_apply(stage,state,tasks,payload,event_payload=None):
    if payload.get('kind')=='npc_policy':return _s3_apply_policy(stage,state,payload)
    if payload.get('kind') not in ('story_setup','story_turn'):return _s3_previous_apply(stage,state,tasks,payload)
    cid=payload['command_id'];digest=_domain_payload_digest(event_payload if event_payload is not None else payload);event_id='DOMAIN-'+cid+'-'+sha256_bytes(str(digest).encode())[:8]
    proposal=payload.get('proposal');runtime=_s3_runtime(state)
    if proposal:
        _s3_proposal_check(stage,proposal,state)
        if cid!=proposal['turn_id']:raise EngineError('STORY_TURN_COMMAND_ID_MISMATCH')
        if cid in runtime['turns']:raise EngineError('STORY_TURN_ALREADY_RECORDED_USE_RECEIPT')
    context={'event_id':event_id,'command_id':cid,'authorization_ref':payload['authorization_ref'],'outer':payload,'stage':Path(stage)};token=_story_scope.set(context)
    try:
        effects=[];changes=[];entries=[]
        # One private work copy, one top-level auth reservation, one native
        # publication. No temporary child receipt can escape as committed.
        for i,effect in enumerate((proposal or {}).get('effects',[])):
            child=_s3_child(payload,i,effect);result=_s3_previous_apply(stage,state,tasks,child);effects.append(result);changes+=result.get('changes',[]);entries+=result.get('entries',[])+result.get('finance_entries',[])
        context['effects']=effects
        verified=[{'receipt_ref':'effect:'+str(i),'effect':copy.deepcopy(effect),'effect_sha256':_repair_digest(effect)} for i,effect in enumerate(effects)]
        for claim in (proposal or {}).get('claims',[]):
            effect=_s3_receipt_effect(stage,claim['receipt_ref'],effects,proposal,state)
            if effect!=claim['expected_effect']:raise EngineError('STORY_RECEIPT_SUBJECT_AMOUNT_QUANTITY_STATUS_MISMATCH')
            if claim['receipt_ref'] not in {r['receipt_ref'] for r in verified}:verified.append({'receipt_ref':claim['receipt_ref'],'effect':copy.deepcopy(effect),'effect_sha256':_repair_digest(effect)})
        for segment in (proposal or {}).get('segments',[]):
            if segment['mode']=='outcome':
                for ref in segment['receipt_refs']:
                    if ref not in {r['receipt_ref'] for r in verified}:raise EngineError('STORY_OUTCOME_UNVERIFIED')
        updates=[]
        for action in _s3_updates(payload):
            result=_s3_apply_update(stage,state,tasks,action,proposal);updates.append(result);changes+=result.get('changes',[])
        if proposal:
            effective_tags=set(proposal['intent_tags'])
            if any(e['kind'] in ('settle_price','account_transfer') for e in proposal['effects']):effective_tags.add('trade')
            if any(e['kind'] in ('start_travel','arrive_location') for e in proposal['effects']):effective_tags.add('travel')
            rules=_s3_rules(state,read_json(Path(stage)/'rules.json'),list(effective_tags),_story_record(state,proposal['scene_id'])['type'],proposal['actor_id'],parse_iso(state['game_time']),proposal['viewer'],base=stage,scene_id=proposal['scene_id'])
            row={'turn_id':cid,'proposal_sha256':_repair_digest(proposal),'proposal':copy.deepcopy(proposal),'viewer':proposal['viewer'],'actor_id':proposal['actor_id'],'scene_id':proposal['scene_id'],'status':'committed','source_event_id':event_id,'committed_at':state['game_time'],'verified_effects':verified,'mechanical_effects':copy.deepcopy(effects),'decision_record':{'base_identity':proposal['base_identity'],'fact_refs':proposal['basis_refs'],'rule_versions':[{'rule_id':r['rule_id'],'version':r['version']} for r in rules],'intent':proposal['player_intent'],'candidates':proposal['candidates'],'public_reason':proposal['public_reason'],'selected_effect_kinds':[r['kind'] for r in proposal['effects']],'result_event_id':event_id,'no_hidden_chain_of_thought_stored':True}}
            runtime['turns'][cid]=row;changes.append({'target':'state:engine_runtime.story_turns_v1.turns.'+cid,'action':'commit_turn_receipt_and_auditable_decision'})
        integrity=_story_integrity(state,tasks)
        if integrity['status']!='PASS':raise EngineError('STORY_TURN_POSTCHECK:'+str(integrity['errors']))
        return {'kind':payload['kind'],'turn_id':cid if proposal else None,'mechanical_effects':effects,'updates':updates,'verified_effects':verified,'changes':changes,'entries':entries,'atomic_world_and_story':True,'command_payload':copy.deepcopy(payload)}
    finally:_story_scope.reset(token)


def commit_turn(base,command,version,dry_run=False):
    if command.get('kind')!='story_turn':raise EngineError('STORY_TURN_COMMAND_REQUIRED')
    # host_intent is accepted only inside an already authenticated host scope;
    # this service never constructs a new approved envelope.
    return domain_command_packet(base,command,version,'story_turn atomic effects and narrative',dry_run)


def turn_report(base,turn_id,viewer='player'):
    _s3_viewer(viewer)
    with SnapshotContext(base):
        ensure_source_ready(base);state=read_json_view(Path(base)/'state.json');row=_s3_runtime(state)['turns'].get(turn_id)
        if row is None or viewer not in (row['viewer'],'gm'):return {'packet':'STORY_TURN_REPORT_V1','status':'NOT_FOUND','viewer':viewer}
        event=history_lookup(base,event_id=row['source_event_id'])
        if not event or event.get('command_id')!=turn_id or event.get('domain_kind')!='story_turn' or event.get('receipt',{}).get('payload_sha256')!=event.get('payload_sha256'):raise EngineError('STORY_TURN_COMMITTED_RECEIPT_MISSING')
        if event['domain_effect']['mechanical_effects']!=row['mechanical_effects']:raise EngineError('STORY_TURN_EFFECT_RECEIPT_MISMATCH')
        segments=[]
        for segment in row.get('revisions',[{'segments':row['proposal']['segments']}])[-1]['segments']:
            if segment['mode']=='outcome':
                segments.append({'mode':'verified_outcome','source_event_id':event['event_id'],'facts':[copy.deepcopy(r) for r in row['verified_effects'] if r['receipt_ref'] in segment['receipt_refs']],'world_truth':True})
            else:segments.append({**copy.deepcopy(segment),'world_truth':False,'role':'creative prose or attributed speech; never a mechanical state update'})
        learned=[fact for fact in _knowledge_rows(state,row['scene_id'],viewer) if any(acquired.get('record_event_id')==event['event_id'] for acquired in fact.get('acquired_from',[]))]
        return {'packet':'STORY_TURN_REPORT_V1','status':'COMMITTED','turn_id':turn_id,'viewer':viewer,'source_event_id':event['event_id'],'committed_at':row['committed_at'],'current_identity':_s3_identity(base),'segments':segments,'verified_results':copy.deepcopy(row['verified_effects']),'newly_learned_facts':learned,'narration_instruction':'AI may expand only these committed facts; rewrite prose without redoing any effect or random roll.','generation_quality':'NOT_RUN','decision_record':copy.deepcopy(row['decision_record'])}



_domain_command_targets=_s3_targets
_domain_authorization_cost=_s3_cost
_phase2_domain_authorization=_s3_authorization
_apply_domain_command=_s3_apply


def _domain_evidence_events(events):
    """Accounting projections of COMMITTED aggregate event bodies, not new events.

    Each projection retains the one actual event ID, authorization and command
    ID. Its exact child input is bound by the parent's ordinary payload digest.
    Never used as a temporary receipt, history append, or a replay instruction.
    """
    rows=[]
    for event in events:
        if event.get('domain_kind')!='story_turn':rows.append(event);continue
        effect=event.get('domain_effect') or {};command=effect.get('command_payload') or {}
        if command.get('kind')!='story_turn' or command.get('command_id')!=event.get('command_id') or _domain_payload_digest(command)!=event.get('payload_sha256') or event.get('authorization',{}).get('status')!='verified':raise EngineError('STORY_COMPOSITE_RECEIPT_BINDING')
        children=command['proposal']['effects'];results=effect['mechanical_effects']
        if len(children)!=len(results):raise EngineError('STORY_COMPOSITE_RECEIPT_COUNT')
        parent=copy.deepcopy(event);parent.pop('finance',None);rows.append(parent)
        for i,(request,result) in enumerate(zip(children,results)):
            child=_s3_child(command,i,request)
            if result.get('kind')!=child['kind']:raise EngineError('STORY_COMPOSITE_RECEIPT_KIND')
            entries=result.get('entries',[])+result.get('finance_entries',[])
            finance={cur:_money_value_currency(sum(_money_units_currency(r.get('delta',0),cur) for r in entries if r.get('currency')==cur),cur) for cur in ('gold','grey')}
            rows.append({**copy.deepcopy(event),'domain_kind':child['kind'],'domain_effect':copy.deepcopy(result),'finance':finance,'composite_parent_event_id':event['event_id'],'composite_effect_index':i})
    return rows


def _s3_apply_policy(stage,state,payload):
    # Grant/revocation is a host-authorized ordinary native transaction. A model
    # proposal, a fixture flag, and an existing autonomous grant cannot create
    # another grant or widen its own scope.
    if not _host_intent_scope.get() or payload.get('authorization')!='host_intent':raise EngineError('NPC_POLICY_TRUSTED_HOST_REQUIRED')
    pid=payload['policy_id']
    if not re.fullmatch(r'[A-Za-z0-9_:-]{1,80}',pid):raise EngineError('NPC_POLICY_ID_INVALID')
    registry=state.setdefault('standing_authorizations',{});action=payload['policy_action'];event_id='DOMAIN-'+payload['command_id']+'-'+sha256_bytes(_domain_payload_digest(payload).encode())[:8]
    if action=='register':
        if pid in registry:raise EngineError('NPC_POLICY_ID_EXISTS')
        grant=copy.deepcopy(payload.get('grant'));fields={'schema','grant_id','subject_id','action_kinds','targets','valid_from','valid_until','max_uses','max_gold_units','max_grey_units','max_quantity'};_s3_fields(grant,fields)
        if grant['schema']!='DOMAIN_MACHINE_GRANT_V1' or grant['grant_id']!=pid:raise EngineError('NPC_POLICY_GRANT_SCHEMA')
        _s3_entity(state,grant['subject_id'],True);now=parse_iso(state['game_time']);lo=parse_iso(grant['valid_from']);hi=parse_iso(grant['valid_until'])
        if not lo or not hi or not now<=lo<=hi<=now+dt.timedelta(days=30):raise EngineError('NPC_POLICY_FINITE_TIME_WINDOW')
        allowed=STORY_UPDATE_KINDS|STORY_MECHANICAL_KINDS|{'story_turn','story_setup','goal_activate','learn_fact'}
        if not isinstance(grant['action_kinds'],list) or not set(grant['action_kinds'])<=allowed or not set(grant['action_kinds'])&{'story_turn','story_setup'}:raise EngineError('NPC_POLICY_ACTION_SCOPE')
        if not isinstance(grant['targets'],list) or not grant['targets'] or any(not isinstance(t,str) or not t.startswith(('state:','tasks:')) or '*' in t or '..' in t for t in grant['targets']):raise EngineError('NPC_POLICY_EXACT_TARGETS_REQUIRED')
        for key in ('max_uses','max_gold_units','max_grey_units','max_quantity'):
            if type(grant[key]) is not int or not 0<=grant[key]<=10**18:raise EngineError('NPC_POLICY_INTEGER_BUDGET')
        if grant['max_uses']==0 or grant['max_grey_units']%100:raise EngineError('NPC_POLICY_BUDGET_OR_GREY_QUANTUM')
        registry[pid]={'status':'active','revoked':False,'machine_grant':grant,'source_event_id':event_id,'source':'verified explicit human/host policy, no implicit NPC authority'}
    elif action=='revoke':
        if pid not in registry:raise EngineError('NPC_POLICY_NOT_FOUND')
        registry[pid].update(status='revoked',revoked=True,revoked_by=event_id)
    else:raise EngineError('NPC_POLICY_ACTION_UNSUPPORTED')
    return {'kind':'npc_policy','policy_id':pid,'policy_action':action,'changes':[{'target':'state:standing_authorizations.'+pid,'action':'verified_finite_npc_policy_'+action}]}



