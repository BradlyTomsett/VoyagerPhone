# === VOYAGER_DEV_MODULE: living_world ===
# Persistent experience, portrayal and scene-independent NPC life. AI supplies
# prose and plausible plans; this module validates, commits and replays neither.
_lw_prepare_previous=prepare_turn
_lw_check_previous=_s3_proposal_check
_lw_update_previous=_s3_apply_update
_lw_targets_previous=_s3_action_targets
_lw_apply_previous=_apply_domain_command
_lw_report_previous=turn_report
_lw_integrity_previous=_story_integrity
_lw_source_previous=_story_source_report
_lw_queue_previous=deterministic_event_queue
_lw_resolve_previous=_resolve_deterministic_event
_lw_time_previous=_set_runtime_time
_lw_ai_previous=_next_ai_monitor_time
_lw_precedes_previous=_deterministic_event_precedes_barrier
_lw_boot_previous=cold_start_packet
_lw_schema_previous=story_schema_packet
_lw_main_previous=main
_lw_catalog_previous=domain_command_catalog
_lw_presence_previous=_s3_presence
_lw_entities_previous=_entity_registry_expected
_lw_known_previous=_knowledge_known
_lw_rows_previous=_knowledge_rows
STORY_TURN_SCHEMA='STORY_TURN_PROPOSAL_V3'
_lw_review_scope=contextvars.ContextVar('living_narrative_review',default=None)
_lw_clock_scope=contextvars.ContextVar('living_clock_authority',default=None)
LIVING_SCHEMA='LIVING_WORLD_V1'
LIVING_BACKGROUND=('name','age','sex','species','occupation','income','housing','family','personality','habits','goals','troubles','experiences','relations','memories','social_identity','social_class','beliefs','interests','past','current_life','future_paths','education','professional_background')
LIVING_VOICE=('vocabulary','catchphrases','dialect','politeness','humor','pauses','repetition','metaphors','topic_gravity','angry','tired','relaxed','nervous')
LIVING_SENSES=('visual','auditory','olfactory','tactile','atmosphere')
LIVING_CONDITIONS=('facilities','weather','society','perception')
LIVING_ACTIONS={'life_profile','life_place','life_schedule','life_cancel','life_inner','life_review','life_position','life_memory','life_control'}
LIVING_LIFE_FIELDS={'occupation','income','housing','family','personality','habits','goals','troubles','experiences','relations','memories','social_identity','social_class','beliefs','interests','current_life','future_paths','education','professional_background'}
STORY_UPDATE_KINDS.update(LIVING_ACTIONS)
LIVING_INSTRUCTION='''每次玩家行动写成一个真实的人正在生活：行动、环境、具体细节、身体/情绪/认知体验与人物反应自然相连；有人交流必须有符合背景和情绪的对话。禁止流水账、状态报告、事件列表。初访完整写视觉、听觉、嗅觉、触觉和氛围；重访只写变化、新发现与简短定位，连续停留不算再次进入。描写服从游戏时间、设施、天气、社会状态与角色认知。真空、隔离头盔、远程等感官缺失必须承认，不能编造可闻气味。NPC说话有各自词汇、口癖、方言、礼貌、幽默、停顿、重复、比喻和关注点；情绪改变节奏，不把这些特点每句堆满，不一次倒出全部信息。玩家台词服从本次实际输入及身份、教育和职业；可把明确交谈意图转为自然台词，但不得添加新的承诺和选择，意图改写须AI复核。重要NPC有完整生活档案，大多数是普通人；拒绝、误解、欺骗、利用、怀疑、遗忘、离开和改变主意都合理，不自动崇拜主角。内在体验用精确身体反应、轻微情绪/认知变化或可选行为倾向呈现；日常一笔带过，关键时刻才展开。感受不是决定，不强迫逃跑、交易、示爱或结盟。世界按游戏时间持续运行，与玩家位置和活动无关；工作作息自动推算，人生节点独立调度；重大未定发展交AI依据人物利益与已知经历塑造，不能把可能性当既成事实。离线聊天不会产生无人运行的后台进程；等待、航行、战斗、交易、调查的实际耗时统一推进游戏时钟。'''


def _lw_runtime(state):
    rt=state.get('engine_runtime',{}).get('living_world_v1')
    if not isinstance(rt,dict) or rt.get('schema')!=LIVING_SCHEMA:raise EngineError('LIVING_WORLD_EXPLICIT_MIGRATION_REQUIRED')
    return rt


def _lw_seed_profile(state,eid):
    e=_s3_entity(state,eid,True)
    return {'entity_id':eid,'important':True,'background':{k:e['canonical_name'] if k=='name' else None for k in LIVING_BACKGROUND},'voice':{k:None for k in LIVING_VOICE},'public_fields':['name'],'voice_visible_to':[],'daily_routine':[],'basis_refs':['state:entity_registry.entities.'+eid],'source_kind':'legacy_reference','revision':0,'source_event_id':None,'as_of':state['game_time']}


def _lw_initial(state):
    return {'schema':LIVING_SCHEMA,'policy_version':1,'adopted_at':state['game_time'],'initial_review_at':(parse_iso(state['game_time'])+dt.timedelta(days=1)).isoformat(),'policy':{'enabled':True,'npc_autonomy':True,'default_population':'ordinary_people','player_decisions':'player_only','clock':'game_time','history_before_adoption':'do_not_resimulate'},'profiles':{eid:_lw_seed_profile(state,eid) for eid in _s3_runtime(state)['npcs']},'places':{},'visits':{},'interiors':{},'life_nodes':{},'experience_receipts':{}}


def _lw_complete(profile):
    return all(isinstance(profile.get('background',{}).get(k),str) and bool(profile['background'][k].strip()) and profile['background'][k].strip().lower() not in ('未知','待补全','unknown','n/a') for k in LIVING_BACKGROUND) and all(isinstance(profile.get('voice',{}).get(k),str) and bool(profile['voice'][k].strip()) and profile['voice'][k].strip().lower() not in ('未知','待补全','unknown','n/a') for k in LIVING_VOICE)


def _lw_text(value,limit=1000):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:raise EngineError('LIVING_TEXT_INVALID')
    return value


def _lw_routine(profile,when):
    if profile.get('life_status')=='dead':return '已死亡；无当前活动'
    minute=when.hour*60+when.minute
    for row in profile['daily_routine']:
        lo=row['start_minute'];hi=row['end_minute']
        if lo<=minute<hi if lo<hi else minute>=lo or minute<hi:return row['activity']
    return profile.get('current_activity') or '未安排；按当前生活与临时事件判断，不默认等待玩家'


def _lw_visit_key(actor,location):return actor+'@'+location


def _lw_frame(state,place,actor=None,viewer='player'):
    frame={'game_time':state['game_time'],**{k:place['conditions'][k] for k in LIVING_CONDITIONS if k!='perception'},'place_revision':place['revision']}
    if actor:
        p=_lw_runtime(state)['profiles'].get(actor,{})
        own=_lw_owns(state,viewer,actor)
        frame['perception']={'actor_id':actor,'education':p.get('background',{}).get('education') if own else None,'professional_background':p.get('background',{}).get('professional_background') if own else None,'knowledge_policy':'Only facts explicitly learned by this actor; no shared omniscience.'}
    return frame


def _lw_visit(state,sid,actor,viewer='player'):
    rec=_story_record(state,sid);loc=rec.get('location_ref')
    if not loc:return {'mode':'needs_location','location_ref':None}
    rt=_lw_runtime(state);place=rt['places'].get(loc);key=_lw_visit_key(actor,loc);prior=rt['visits'].get(key)
    epoch=rt.get('presence_epochs',{}).get(actor,0)
    if rec.get('presence_mode')=='remote':mode='remote'
    elif prior is None:mode='first'
    elif prior.get('presence_epoch',0)==epoch:mode='continuing'
    else:mode='return'
    frame=_lw_frame(state,place,actor,viewer) if place else None
    changes=[k for k in (frame or {}) if k not in ('game_time','perception') and (not prior or prior.get('frame',{}).get(k)!=frame[k])]
    return {'mode':mode,'location_ref':loc,'presence_epoch':epoch,'prior_visits':(prior or {}).get('count',0),'last_seen_at':(prior or {}).get('last_seen_at'),'frame':frame,'changed_fields':changes,'place_required':place is None,'prior_environment_quote':(prior or {}).get('environment_quote')}


def _lw_context(state,sid,actor,viewer):
    rt=_lw_runtime(state);rec=_story_record(state,sid);visit=_lw_visit(state,sid,actor,viewer) if actor else {'mode':'actor_required'};people=[]
    known={f.get('subject_id') for f in _knowledge_rows(state,sid,viewer)}
    visible=lambda eid:viewer=='gm' or eid==actor or eid in known or viewer in rec.get('participant_visibility',[])
    for eid in rec['participants']:
        if not visible(eid):continue
        p=rt['profiles'].get(eid);row={'entity_id':eid,'profile_required':p is None or not _lw_complete(p)}
        if p:
            own=_lw_owns(state,viewer,eid)
            row.update(revision=p['revision'],background={k:v for k,v in p['background'].items() if own or k in p['public_fields']})
            if own or viewer in p['voice_visible_to']:row['voice']=copy.deepcopy(p['voice'])
            if own:row['routine_now']=_lw_routine(p,parse_iso(state['game_time']));row['daily_routine']=copy.deepcopy(p['daily_routine'])
        people.append(row)
    place=rt['places'].get(visit.get('location_ref'));public_place=place and (viewer=='gm' or viewer in place['visible_to'])
    # Conditions and changes can also be secrets; do not expose a private frame.
    if not public_place:visit={k:v for k,v in visit.items() if k not in ('frame','changed_fields')}
    inner=rt['interiors'].get(actor)
    disclosed_place=copy.deepcopy(place) if public_place else None
    if disclosed_place:disclosed_place.get('conditions',{}).pop('perception',None)
    packet={'schema':'LIVED_CONTEXT_V2','instruction':LIVING_INSTRUCTION,'visit':visit,'place':disclosed_place,'people':people,'interior':copy.deepcopy(inner) if inner and _lw_owns(state,viewer,actor) else None,'planning':'Complete missing profiles/place in an authorized story_setup before acting; schedule plausible future life nodes, not guaranteed futures. Never reveal private fields.','pov_control_required':viewer=='player' and not _lw_owns(state,viewer,actor),'literary_review':'Independent trusted host review of the exact proposal is required before player prose can commit; model flags are not approval.'}
    if viewer=='gm':packet['life_planning_due']=[eid for eid,p in rt['profiles'].items() if _lw_complete(p) and not any(n['entity_id']==eid and n['status']=='pending' for n in rt['life_nodes'].values())]
    return packet


def _lw_prepare(base=ROOT,scene_id=None,actor_id=None,viewer='player',player_intent='',intent_tags=None,budget_bytes=16384):
    with SnapshotContext(base):
        packet=_lw_prepare_previous(base,scene_id,actor_id,viewer,player_intent,intent_tags,budget_bytes)
        state=read_json_view(Path(base)/'state.json');rt=_lw_runtime(state)
        if packet.get('scene_id'):packet['lived_experience']=_lw_context(state,packet['scene_id'],actor_id,viewer)
        else:packet['lived_experience']={'schema':'LIVED_CONTEXT_V2','instruction':LIVING_INSTRUCTION,'next':'Open an authorized scene; no auto-resurrection of closed scenes.'}
        packet['proposal_schema']=STORY_TURN_SCHEMA
        packet=_s3_fit_context(packet,budget_bytes) if packet.get('scene_id') else _stage2_finalize_size(packet,budget_bytes)
        if packet.get('budget_exceeded'):packet['generation_blocked']='INCREASE_CONTEXT_BUDGET_BEFORE_NARRATING'
        return _stage2_finalize_size(packet,budget_bytes)


def _lw_anchor(segments,anchor):
    _s3_fields(anchor,{'segment','quote'})
    i=anchor['segment'];q=anchor['quote']
    if type(i) is not int or not 0<=i<len(segments) or segments[i]['mode']=='outcome' or not isinstance(q,str) or len(q.strip())<4 or q not in segments[i]['text']:raise EngineError('LIVED_ANCHOR_NOT_IN_PROSE')
    return segments[i]


def _lw_check_experience(state,proposal,visit=None):
    x=proposal.get('experience');segments=proposal['segments'];sid=proposal['scene_id'];actor=proposal['actor_id'];rt=_lw_runtime(state);rec=_story_record(state,sid)
    for eid in rec['participants']:
        profile=rt['profiles'].get(eid)
        if not profile or profile.get('important',True) and not _lw_complete(profile):raise EngineError('LIVED_NPC_PROFILE_INCOMPLETE')
    _s3_fields(x,{'schema','location_ref','visit_mode','frame','anchors','senses','dialogue_mode','voices','agency','player_speech'})
    if x['schema']!='LIVED_EXPERIENCE_V1':raise EngineError('LIVED_EXPERIENCE_SCHEMA')
    historical=visit is not None
    visit=visit or _lw_visit(state,sid,actor,proposal['viewer'])
    if not historical and proposal['viewer']=='player' and not _lw_owns(state,'player',actor):raise EngineError('LIVING_PLAYER_CONTROL_REQUIRED')
    if x['location_ref']!=visit.get('location_ref') or x['visit_mode']!=visit['mode']:raise EngineError('LIVED_VISIT_MODE_MISMATCH')
    place=rt['places'].get(x['location_ref'])
    if not place:raise EngineError('LIVED_PLACE_PROFILE_REQUIRED')
    if proposal['viewer']!='gm' and proposal['viewer'] not in place['visible_to']:raise EngineError('LIVED_PLACE_NOT_DISCLOSED')
    if x['frame']!=visit['frame']:raise EngineError('LIVED_SCENE_FRAME_STALE')
    _s3_fields(x['anchors'],{'action','environment','detail','response','inner'})
    for key,anchor in x['anchors'].items():_lw_anchor(segments,anchor)
    quotes=[a['quote'].strip() for a in x['anchors'].values()]
    if len(set(quotes))!=len(quotes) or any(a in b or b in a for i,a in enumerate(quotes) for b in quotes[i+1:]):raise EngineError('LIVED_ANCHORS_MUST_BE_DISTINCT')
    if any(re.fullmatch(r'(?:系统|状态|数据|检查|事件|报告)[：:、\s]*(?:状态|正常|完成|通过|无变化)*[。.!！]?',q) for q in quotes):raise EngineError('LIVED_STATUS_REPORT_NOT_NARRATIVE')
    if not isinstance(x['senses'],dict) or set(x['senses'])-set(LIVING_SENSES):raise EngineError('LIVED_SENSES_SCHEMA')
    for kind,anchor in x['senses'].items():_lw_anchor(segments,anchor)
    if len({a['quote'].strip() for a in x['senses'].values()})!=len(x['senses']):raise EngineError('LIVED_SENSES_MUST_BE_DISTINCT')
    if visit['mode']=='first' and set(x['senses'])!=set(LIVING_SENSES):raise EngineError('LIVED_FIRST_VISIT_FIVE_SENSES_REQUIRED')
    if visit['mode']=='first' and sum(len(s['text']) for s in segments if s['mode']=='description')<120:raise EngineError('LIVED_FIRST_VISIT_DETAIL_REQUIRED')
    if visit['mode'] in ('return','continuing'):
        prior=rt['visits'].get(_lw_visit_key(actor,x['location_ref']),{})
        if visit['mode']=='return' and sum(len(s['text']) for s in segments if s['mode']=='description')>3000:raise EngineError('LIVED_RETURN_DESCRIPTION_NOT_CONCISE')
    if x['agency']!={'decisions_left_to_player':True,'feelings_are_suggestions':True}:raise EngineError('LIVED_PLAYER_AGENCY_REQUIRED')
    if x['dialogue_mode'] not in ('exchange','alone','no_channel'):raise EngineError('LIVED_DIALOGUE_MODE')
    if x['dialogue_mode']=='alone' and any(eid!=actor and _lw_is_present(state,rec,eid) for eid in rec['participants']):raise EngineError('LIVED_DIALOGUE_REQUIRED')
    if not historical:
        for segment in segments:
            if segment['speaker_id'] is not None:_s3_presence(state,rec,segment['speaker_id'],rec.get('presence_mode','present'))
    dialogue=[(i,s) for i,s in enumerate(segments) if s['mode']=='dialogue']
    if x['dialogue_mode']=='exchange' and not dialogue:raise EngineError('LIVED_DIALOGUE_REQUIRED')
    if not isinstance(x['voices'],list) or len(x['voices'])!=len(dialogue):raise EngineError('LIVED_VOICE_COVERAGE')
    for (i,segment),voice in zip(dialogue,x['voices']):
        _s3_fields(voice,{'segment','entity_id','profile_revision','emotion','disclosure'})
        eid=segment['speaker_id'];p=rt['profiles'].get(eid)
        if p and p.get('life_status')=='dead':raise EngineError('LIVING_PERSON_DEAD')
        if voice['segment']!=i or voice['entity_id']!=eid or not p or not _lw_complete(p):raise EngineError('LIVED_NPC_PROFILE_INCOMPLETE')
        if voice['profile_revision']!=p['revision']:raise EngineError('LIVED_VOICE_PROFILE_STALE')
        if voice['emotion'] not in ('neutral','angry','tired','relaxed','nervous','sad','afraid','happy') or voice['disclosure'] not in ('partial','none'):raise EngineError('LIVED_VOICE_OR_INFORMATION_DUMP')
    player_lines=[s['text'] for _,s in dialogue if s['speaker_id']==actor]
    if x['player_speech'] not in ('none','verbatim','intent_faithful'):raise EngineError('LIVED_PLAYER_SPEECH_MUST_FOLLOW_INPUT')
    if player_lines and (x['player_speech']=='none' or x['player_speech']=='verbatim' and any(t not in proposal['player_intent'] for t in player_lines)):raise EngineError('LIVED_PLAYER_SPEECH_NOT_AUTHORIZED')
    for s in segments:
        if s['mode']=='description' and re.search(r'你(?:决定|答应了|签下了|承诺了|爱上了|选择了逃跑|不由自主地扣动)',s['text']):raise EngineError('LIVED_FORCED_PLAYER_DECISION')
    if not historical:_lw_require_review(proposal)
    return {'status':'PASS','structural_only':True,'literary_review':'TRUSTED_REVIEW_REQUIRED','visit_mode':visit['mode'],'frame_sha256':_repair_digest(x['frame'])}


def _lw_proposal_check(base,proposal,state):
    if type(proposal.get('elapsed_seconds')) is not int or not 1<=proposal['elapsed_seconds']<=86400:raise EngineError('STORY_ACTION_DURATION_REQUIRED_1_TO_86400')
    rec=_lw_check_previous(base,proposal,state)
    if proposal['viewer']=='player':_lw_check_experience(state,proposal)
    return rec


def _lw_targets(action):
    typ=action.get('type')
    if typ not in LIVING_ACTIONS:
        out=_lw_targets_previous(action)
        if typ=='entity_register':out.append('state:engine_runtime.living_world_v1.profiles.'+_story_id(action['entity_id']))
        return out
    if typ in ('life_profile','life_inner','life_review','life_position','life_memory','life_control'):tail=('interiors.' if typ=='life_inner' else 'profiles.')+_story_id(action.get('entity_id'))
    elif typ=='life_place':tail='places.'+_story_id(action.get('location_ref'))
    else:tail='life_nodes.'+_story_id(action.get('node_id'))
    out=['state:engine_runtime.living_world_v1.'+tail]
    if typ=='life_control':out.extend(['state:engine_runtime.living_world_v1.controls','state:engine_runtime.living_world_v1.player_characters'])
    if typ=='life_position':out.extend(['state:engine_runtime.story_turns_v1.npcs.'+_story_id(action['entity_id']),'state:engine_runtime.living_world_v1.presence_epochs'])
    if typ=='life_schedule' and action.get('location_after'):out.append('state:engine_runtime.story_turns_v1.npcs.'+_story_id(action['entity_id']))
    return out


def _lw_profile_record(state,eid,record):
    _s3_entity(state,eid,True)
    _s3_fields(record,{'important','background','voice','public_fields','voice_visible_to','daily_routine','basis_refs','source_kind'})
    if type(record['important']) is not bool or set(record['background'])!=set(LIVING_BACKGROUND) or set(record['voice'])!=set(LIVING_VOICE):raise EngineError('LIVING_PROFILE_FIELDS')
    if not _lw_complete(record):raise EngineError('LIVING_PROFILE_COMPLETION_REQUIRED')
    for other,profile in _lw_runtime(state)['profiles'].items():
        if other!=eid and record['important'] and profile.get('important') and _lw_complete(profile) and record['voice']==profile['voice']:raise EngineError('LIVING_VOICE_MUST_BE_DISTINCT')
    for value in list(record['background'].values())+list(record['voice'].values()):_lw_text(value,1500)
    if record['background']['name']!=_s3_entity(state,eid)['canonical_name']:raise EngineError('LIVING_PROFILE_NAME_BINDING')
    if not isinstance(record['public_fields'],list) or not set(record['public_fields'])<=set(LIVING_BACKGROUND):raise EngineError('LIVING_PROFILE_PUBLIC_FIELDS')
    for v in record['voice_visible_to']:_knowledge_viewer(v,True)
    if record['source_kind'] not in ('authored_consistent_extension','confirmed_evidence') or not isinstance(record['basis_refs'],list) or not record['basis_refs']:raise EngineError('LIVING_PROFILE_PROVENANCE')
    for ref in record['basis_refs']:_lw_text(ref,300)
    if not isinstance(record['daily_routine'],list) or len(record['daily_routine'])>24:raise EngineError('LIVING_ROUTINE_LIMIT')
    occupied=set()
    for r in record['daily_routine']:
        _s3_fields(r,{'start_minute','end_minute','activity'})
        lo=r['start_minute'];hi=r['end_minute'];_lw_text(r['activity'],200)
        if type(lo) is not int or type(hi) is not int or not 0<=lo<1440 or not 0<=hi<=1440 or lo==hi:raise EngineError('LIVING_ROUTINE_TIME')
        minutes=set(range(lo,hi)) if lo<hi else set(range(lo,1440))|set(range(hi))
        if occupied&minutes:raise EngineError('LIVING_ROUTINE_OVERLAP')
        occupied|=minutes


def _lw_update(stage,state,tasks,action,proposal=None):
    typ=action['type'];rt=_lw_runtime(state)
    if typ not in LIVING_ACTIONS:
        if typ=='turn_rewrite':
            old=_s3_runtime(state)['turns'].get(action.get('turn_id'),{});p=copy.deepcopy(old.get('proposal',{}))
            if p.get('experience'):
                if 'experience' not in action:raise EngineError('LIVED_REWRITE_EXPERIENCE_REQUIRED')
                p['segments']=action['segments'];p['experience']=action['experience'];visit=copy.deepcopy(rt['experience_receipts'][p['turn_id']]['visit_basis'])
                # Check against the original frame/profile snapshots, not today's
                # location or speech revision; rewriting is never another visit.
                snap=copy.deepcopy(state);snap['engine_runtime']['living_world_v1']['places'][visit['location_ref']]=copy.deepcopy(rt['portrayal_snapshots'][rt['experience_receipts'][p['turn_id']]['place_basis']])
                scene_ref=rt['experience_receipts'][p['turn_id']].get('scene_basis')
                if scene_ref:snap['engine_runtime']['scene_registry_v1']['records'][p['scene_id']]=copy.deepcopy(rt['portrayal_snapshots'][scene_ref])
                for eid,ref in rt['experience_receipts'][p['turn_id']]['voice_basis'].items():snap['engine_runtime']['living_world_v1']['profiles'][eid]=copy.deepcopy(rt['portrayal_snapshots'][ref])
                if p['viewer']=='player':_lw_require_review(p)
                _lw_check_experience(snap,p,visit)
                clean={k:v for k,v in action.items() if k!='experience'};result=_lw_update_previous(stage,state,tasks,clean,proposal)
                _s3_runtime(state)['turns'][p['turn_id']]['revisions'][-1].update(experience=copy.deepcopy(p['experience']),literary_review=copy.deepcopy(_lw_review_scope.get()))
                return result
        result=_lw_update_previous(stage,state,tasks,action,proposal)
        if typ=='entity_register':
            eid=action['entity_id']
            if _s3_entity(state,eid).get('entity_type')=='person':rt['profiles'][eid]=_lw_seed_profile(state,eid)
        return result
    ctx=_story_event_context();event=ctx['event_id'];now=state['game_time']
    if typ=='life_profile':
        _s3_fields(action,{'type','entity_id','expected_revision','record'});eid=action['entity_id'];r=copy.deepcopy(action['record']);_lw_profile_record(state,eid,r)
        old=rt['profiles'].get(eid)
        if action['expected_revision']!=(old or {}).get('revision',0):raise EngineError('LIVING_PROFILE_STALE')
        # A completed biography cannot be silently replaced by a newly authored
        # past; life changes use chronological nodes, corrections cite evidence.
        if old and _lw_complete(old):_lw_profile_correction(stage,state,eid,old,r)
        rt['profiles'][eid]={**copy.deepcopy(old or {}),**r,'life_status':(old or {}).get('life_status','alive'),'entity_id':eid,'revision':(old or {}).get('revision',0)+1,'source_event_id':event,'as_of':now,'next_review_at':(parse_iso(now)+dt.timedelta(days=30)).isoformat()}
    elif typ=='life_control':
        _s3_fields(action,{'type','entity_id','operation','reason'});eid=action['entity_id'];_s3_entity(state,eid,True);_lw_text(action['reason'],500)
        if action['operation'] not in ('take','release'):raise EngineError('LIVING_CONTROL_OPERATION')
        if action['operation']=='take' and rt['profiles'][eid].get('life_status')=='dead':raise EngineError('LIVING_PERSON_DEAD')
        rt.setdefault('controls',{})[eid]={'active':action['operation']=='take','source_event_id':event,'as_of':now,'reason':action['reason']}
        rt['player_characters']=sorted(k for k,v in rt['controls'].items() if v['active'])
    elif typ=='life_review':
        _s3_fields(action,{'type','entity_id','next_review_at','reason'});eid=action['entity_id'];p=rt['profiles'].get(eid);at=parse_iso(action['next_review_at']);_lw_text(action['reason'],500)
        if not p or not _lw_complete(p) or not at or not parse_iso(now)<at<=parse_iso(now)+dt.timedelta(days=30):raise EngineError('LIVING_REVIEW_WINDOW')
        p.update(next_review_at=action['next_review_at'],review_event_id=event)
    elif typ=='life_position':
        _s3_fields(action,{'type','entity_id','location_ref','basis_refs','reason'});eid=action['entity_id'];_s3_entity(state,eid,True);loc=_s3_entity(state,action['location_ref']);_lw_text(action['reason'],500)
        if loc['entity_type'] not in ('location','independent_station','independent_planet','mining_site','independent_agricultural_planet') or not action['basis_refs']:raise EngineError('LIVING_POSITION_BASIS')
        _lw_move(state,eid,action['location_ref'],event)
    elif typ=='life_memory':
        _s3_fields(action,{'type','entity_id','scene_id','fact_id','operation','reason'});eid=action['entity_id'];_s3_entity(state,eid,True);_lw_text(action['reason'],500)
        fid=action['fact_id'];scene=action['scene_id'];known=_lw_known_previous(state,scene,'npc:'+eid)
        if fid not in known or action['operation'] not in ('forget','recall'):raise EngineError('LIVING_MEMORY_NOT_LEARNED')
        p=rt['profiles'][eid];p.setdefault('forgotten',{})[_knowledge_key(scene,fid)]={'scene_id':scene,'fact_id':fid,'operation':action['operation'],'reason':action['reason'],'source_event_id':event};p['revision']+=1;p['source_event_id']=event
    elif typ=='life_place':
        _s3_fields(action,{'type','location_ref','expected_revision','senses','conditions','visible_to','basis_refs'});loc=action['location_ref'];entity=_s3_entity(state,loc)
        if entity['entity_type'] not in ('location','independent_station','independent_planet','mining_site','independent_agricultural_planet'):raise EngineError('LIVING_PLACE_TYPE')
        if set(action['senses'])!=set(LIVING_SENSES) or set(action['conditions'])!=set(LIVING_CONDITIONS):raise EngineError('LIVING_PLACE_FIELDS')
        for v in list(action['senses'].values())+list(action['conditions'].values()):_lw_text(v,700)
        for v in action['visible_to']:_knowledge_viewer(v,True)
        if not action['basis_refs']:raise EngineError('LIVING_PLACE_PROVENANCE')
        old=rt['places'].get(loc)
        if action['expected_revision']!=(old or {}).get('revision',0):raise EngineError('LIVING_PLACE_STALE')
        rt['places'][loc]={k:copy.deepcopy(v) for k,v in action.items() if k not in ('type','expected_revision')};rt['places'][loc].update(revision=(old or {}).get('revision',0)+1,source_event_id=event,as_of=now)
    elif typ=='life_inner':
        _s3_fields(action,{'type','entity_id','body','emotion','cognition','impulse','basis_refs'});eid=action['entity_id'];_s3_entity(state,eid,True)
        for k in ('body','emotion','cognition','impulse'):_lw_text(action[k],400)
        if not action['basis_refs']:raise EngineError('LIVING_INNER_BASIS_REQUIRED')
        rt['interiors'][eid]={k:copy.deepcopy(v) for k,v in action.items() if k!='type'};rt['interiors'][eid].update(source_event_id=event,as_of=now,decision_effects=0)
    elif typ=='life_cancel':
        _s3_fields(action,{'type','node_id','reason'});n=rt['life_nodes'].get(action['node_id']);_lw_text(action['reason'],500)
        if not n or n['status']!='pending':raise EngineError('LIVING_NODE_NOT_PENDING')
        n.update(status='cancelled',resolution_event_id=event,resolved_at=now,cancellation_reason=action['reason'])
    else:
        _s3_fields(action,{'type','node_id','entity_id','due_at','category','changes','expected','status_after','reason','visible_to'},{'location_after','routine_after','current_activity_after'})
        nid=_story_id(action['node_id']);eid=action['entity_id'];p=rt['profiles'].get(eid)
        if nid in rt['life_nodes']:raise EngineError('LIVING_NODE_ID_REUSED')
        if not p or not _lw_complete(p):raise EngineError('LIVING_PROFILE_COMPLETION_REQUIRED')
        if _lw_controlled(state,eid):raise EngineError('LIVING_AUTONOMY_CANNOT_CONTROL_PLAYER')
        if p.get('life_status')=='dead':raise EngineError('LIVING_PERSON_DEAD')
        due=parse_iso(action['due_at']);at=parse_iso(now)
        if not due or due<=at:raise EngineError('LIVING_NODE_FUTURE_REQUIRED')
        if action['category'] not in ('work','marriage','birth','move','promotion','unemployment','bankruptcy','travel','study','training','military','business','illness','retirement','death','family','organization','belief','relationship','ordinary'):raise EngineError('LIVING_LIFE_CATEGORY')
        if not isinstance(action['changes'],dict) or not action['changes'] or set(action['changes'])-LIVING_LIFE_FIELDS or set(action['expected'])!=set(action['changes']):raise EngineError('LIVING_LIFE_FIELDS')
        for key,val in action['changes'].items():
            _lw_text(val,1500)
            if action['expected'][key]!=p['background'][key]:raise EngineError('LIVING_LIFE_EXPECTED_MISMATCH')
        if action['status_after'] not in (None,'dead'):raise EngineError('LIVING_STATUS_UNSUPPORTED')
        if action['status_after']=='dead' and action['category']!='death':raise EngineError('LIVING_DEATH_CATEGORY')
        if action['status_after']=='dead' and eid in state.get('key_personnel_current_roles',{}):raise EngineError('LIVING_MANAGED_CREW_DEATH_REQUIRES_MECHANICAL_RECEIPT')
        if action.get('location_after'):
            loc=_s3_entity(state,action['location_after'])
            if loc['entity_type'] not in ('location','independent_station','independent_planet','mining_site','independent_agricultural_planet'):raise EngineError('LIVING_POSITION_TYPE')
        if 'routine_after' in action:_lw_validate_routine(action['routine_after'])
        if 'current_activity_after' in action:_lw_text(action['current_activity_after'],400)
        _lw_text(action['reason'],1000)
        for v in action['visible_to']:_knowledge_viewer(v,True)
        rt['life_nodes'][nid]={k:copy.deepcopy(v) for k,v in action.items() if k!='type'};rt['life_nodes'][nid].update(status='pending',created_at=now,source_event_id=event)
    return {'action':typ,'changes':[{'target':t,'action':typ} for t in _lw_targets(action)]}


def _lw_portrayal_snapshot(rt,value):
    digest=_repair_digest(value);rt.setdefault('portrayal_snapshots',{}).setdefault(digest,copy.deepcopy(value));return digest


def _lw_apply(stage,state,tasks,payload,event_payload=None):
    legacy=[payload.get('action',{})] if payload.get('kind')=='story_action' else payload.get('actions',[]) if payload.get('kind')=='story_transaction' else []
    if any(a.get('type') in ('narrative_commit','narrative_rewrite') for a in legacy):raise EngineError('LIVED_USE_STORY_TURN')
    p=payload.get('proposal') if payload.get('kind')=='story_turn' else None
    visit=_lw_visit(state,p['scene_id'],p['actor_id'],p['viewer']) if p and p['viewer']=='player' else None
    start=state['game_time'];rt=_lw_runtime(state)
    basis={'place':copy.deepcopy(rt['places'].get(visit['location_ref'])),'scene':copy.deepcopy(_story_record(state,p['scene_id'])),'voices':{eid:copy.deepcopy(rt['profiles'][eid]) for eid in _story_record(state,p['scene_id'])['participants']},'knowledge':{eid:sorted(_s3_visible_refs(state,p['scene_id'],'npc:'+eid)) for eid in _story_record(state,p['scene_id'])['participants']}} if visit else None
    result=_lw_apply_previous(stage,state,tasks,payload)
    if visit:
        rt=_lw_runtime(state);x=p['experience'];key=_lw_visit_key(p['actor_id'],x['location_ref']);prior=rt['visits'].get(key,{})
        row=_s3_runtime(state)['turns'][p['turn_id']];event=row['source_event_id']
        rt['experience_receipts'][p['turn_id']]={'turn_id':p['turn_id'],'source_event_id':event,'experience_sha256':_repair_digest(x),'visit_basis':copy.deepcopy(visit),'place_basis':_lw_portrayal_snapshot(rt,basis['place']),'voice_basis':{eid:_lw_portrayal_snapshot(rt,profile) for eid,profile in basis['voices'].items()},'scene_basis':_lw_portrayal_snapshot(rt,basis['scene']),'knowledge_basis':basis['knowledge'],'structural_review':'PASS','literary_review':copy.deepcopy(_lw_review_scope.get())}
        if visit['mode']!='remote':
            rt['visits'][key]={'actor_id':p['actor_id'],'location_ref':x['location_ref'],'presence_epoch':visit['presence_epoch'],'count':prior.get('count',0)+(visit['mode'] in ('first','return')),'last_seen_at':start,'frame':copy.deepcopy(x['frame']),'environment_quote':x['anchors']['environment']['quote'],'source_event_id':event}
        result['experience_receipt_sha256']=_repair_digest(rt['experience_receipts'][p['turn_id']])
        result['changes'].append({'target':'state:engine_runtime.living_world_v1','action':'commit_experience_and_physical_visit'})
    if p:
        clock=_lw_advance_round(stage,state,tasks,payload,start)
        result['clock']=clock;result['changes']+=_routine_time_changes()
        result['changes'].extend(clock['changes'])
        row=_s3_runtime(state)['turns'][p['turn_id']];row['completed_at']=state['game_time'];row['clock']=copy.deepcopy(clock)
    return result


def _lw_queue(state,tasks,now,horizon):
    rows=_lw_queue_previous(state,tasks,now,horizon);rt=state.get('engine_runtime',{}).get('living_world_v1',{})
    for nid,n in rt.get('life_nodes',{}).items():
        due=parse_iso(n['due_at'])
        if n['status']=='pending' and due<=horizon:rows.append({'time':max(now,due).isoformat(),'source':'npc_life','job_id':nid,'node_id':nid,'resolver':'npc_life_v1','task_id':None})
    return sorted(rows,key=lambda r:(r['time'],r.get('source',''),r.get('task_id') or r.get('job_id') or ''))


def _lw_resolve(stage,state,tasks,event,when):
    if event.get('source')!='npc_life':return _lw_resolve_previous(stage,state,tasks,event,when)
    rt=_lw_runtime(state);nid=event['node_id'];n=rt['life_nodes'].get(nid)
    if not n or n['status']!='pending' or parse_iso(n['due_at'])>when:raise EngineError('LIVING_NODE_NOT_DUE')
    p=rt['profiles'][n['entity_id']];e=_s3_entity(state,n['entity_id'],True)
    eid='NPC-LIFE-'+nid+'-'+_repair_digest({'source':n['source_event_id'],'due':n['due_at']})[:12]
    if _lw_controlled(state,n['entity_id']):status='superseded_player_control'
    elif e.get('status')=='dead' or any(p['background'][k]!=v for k,v in n['expected'].items()):status='superseded'
    else:
        p['background'].update(copy.deepcopy(n['changes']));p['revision']+=1;p.update(as_of=when.isoformat(),source_event_id=eid);status='delivered'
        if n.get('location_after'):
            _lw_move(state,n['entity_id'],n['location_after'],eid)
        if 'routine_after' in n:p['daily_routine']=copy.deepcopy(n['routine_after'])
        elif n['category'] in ('retirement','unemployment','illness','death'):p['daily_routine']=[]
        if 'current_activity_after' in n:p['current_activity']=n['current_activity_after']
        elif n['category'] in ('retirement','unemployment','illness','death'):p['current_activity']=n['changes'].get('current_life','按新的生活情况休息；旧班次已结束')
        if n['status_after']=='dead':p['life_status']='dead';e['status']='dead';p['daily_routine']=[];p['current_activity']='已死亡'
    n.update(status=status,resolved_at=when.isoformat(),resolution_event_id=eid)
    changes=[{'target':'state:engine_runtime.living_world_v1','action':'npc_life_'+status}]
    if status=='delivered' and n.get('location_after'):changes.append({'target':'state:engine_runtime.story_turns_v1.npcs.'+n['entity_id'],'action':'npc_arrival'})
    if status=='delivered' and n['status_after']=='dead':changes.append({'target':'state:entity_registry.entities.'+n['entity_id']+'.status','action':'death'})
    _append_engine_history(Path(stage)/'events.jsonl',{'event_id':eid,'game_time':when.isoformat(),'type':'npc_autonomous_life','summary':'独立于玩家场景的NPC人生节点；私有细节遵循知情隔离。','changes':changes,'authority_files':['state.json'],'source':'GAME ENGINE '+ENGINE_VERSION,'node_id':nid,'cause_event_id':n['source_event_id'],'outcome':status})
    return {'status':'COMMITTED','event_id':eid,'node_id':nid,'outcome':status,'changes':changes}


def _lw_known(state,sid,viewer):
    known=_lw_known_previous(state,sid,viewer)
    if viewer.startswith('npc:'):
        p=state.get('engine_runtime',{}).get('living_world_v1',{}).get('profiles',{}).get(viewer[4:],{})
        known-={row['fact_id'] for row in p.get('forgotten',{}).values() if row['scene_id']==sid and row['operation']=='forget'}
    return known


def _lw_rows(state,sid,viewer):
    rows=_lw_rows_previous(state,sid,viewer)
    if viewer.startswith('npc:'):
        known=_lw_known(state,sid,viewer);rows=[r for r in rows if r['fact_id'] in known]
    return rows


def _lw_presence(state,rec,eid,mode):
    if state.get('engine_runtime',{}).get('living_world_v1',{}).get('profiles',{}).get(eid,{}).get('life_status')=='dead':raise EngineError('LIVING_PERSON_DEAD')
    return _lw_presence_previous(state,rec,eid,mode)


def _lw_entities(state):
    expected=_lw_entities_previous(state)
    for eid,p in state.get('engine_runtime',{}).get('living_world_v1',{}).get('profiles',{}).items():
        if p.get('life_status')=='dead' and eid in expected:expected[eid]['status']='dead'
    return expected


def _lw_set_time(state,tasks,world_text,new_time,runtime_rules=None):
    rt=state.get('engine_runtime',{}).get('living_world_v1',{})
    if any(n['status']=='pending' and parse_iso(n['due_at'])<new_time for n in rt.get('life_nodes',{}).values()):raise EngineError('LIVING_DUE_USE_SHARED_SCHEDULER')
    _lw_background_check_time(state,new_time)
    if rt.get('initial_review_at') and parse_iso(rt['initial_review_at'])<new_time and any(not _lw_complete(p) and not _lw_background_eligible(state,eid,new_time) and _s3_entity(state,eid).get('status')!='dead' for eid,p in rt.get('profiles',{}).items()):raise EngineError('LIVING_GLOBAL_PROFILE_REVIEW_REQUIRED')
    if any(_lw_complete(p) and not _lw_background_eligible(state,eid,new_time) and p.get('next_review_at') and parse_iso(p['next_review_at'])<new_time and _s3_entity(state,eid).get('status')!='dead' and eid not in rt.get('player_characters',[]) for eid,p in rt.get('profiles',{}).items()):raise EngineError('LIVING_REVIEW_USE_SHARED_SCHEDULER')
    return _lw_time_previous(state,tasks,world_text,new_time,runtime_rules)


def _lw_next_ai(tasks,now,horizon,state=None):
    prior=_lw_ai_previous(tasks,now,horizon,state);candidates=[prior] if prior else []
    if state:
        rt=state.get('engine_runtime',{}).get('living_world_v1',{})
        for eid,p in rt.get('profiles',{}).items():
            managed=_lw_background_eligible(state,eid)
            if not managed and not _lw_complete(p) and _s3_entity(state,eid).get('status')!='dead':
                initial=parse_iso(rt.get('initial_review_at'))
                if initial and initial<=horizon:candidates.append({'time':max(now,initial),'kind':'npc_life_profile','title':'既有人物独立生活初始化','event':{'entity_id':eid,'query':'livingworld --viewer gm'},'resolution_required':'AI completes this existing NPC from canonical evidence and consistent setting extensions, then plans ordinary independent life; do not wait for player contact or invent pre-adoption events.'})
            due=parse_iso(p.get('next_review_at'))
            if not managed and due and due<=horizon and _lw_complete(p) and eid not in rt.get('player_characters',[]) and _s3_entity(state,eid).get('status')!='dead':
                candidates.append({'time':max(now,due),'kind':'npc_life_review','title':'NPC独立生活规划复核','event':{'entity_id':eid,'query':'livingworld --viewer gm'},'resolution_required':'AI uses the private biography, current life and interests to schedule/adjust future life nodes; life_review advances the bounded review horizon, with no player approval for ordinary NPC life.'})
    return min(candidates,key=lambda r:(r['time'],r.get('kind',''),r.get('event',{}).get('entity_id',''))) if candidates else None


def _lw_precedes(event,event_time,hard,barrier):
    if event.get('source')=='npc_life' and event_time==hard:return True
    return _lw_precedes_previous(event,event_time,hard,barrier)


def _lw_integrity(state,tasks):
    out=_lw_integrity_previous(state,tasks)
    try:
        rt=_lw_runtime(state)
        for eid,entity in state['entity_registry']['entities'].items():
            if entity.get('entity_type')=='person' and (eid not in _s3_runtime(state)['npcs'] or eid not in rt['profiles']):raise EngineError('LIVING_PERSON_RUNTIME_NOT_INITIALIZED:'+eid)
        if rt.get('player_characters',[])!=sorted(eid for eid,row in rt.get('controls',{}).items() if row.get('active') is True):raise EngineError('LIVING_CONTROL_BINDING')
        if rt['policy']!={'enabled':True,'npc_autonomy':True,'default_population':'ordinary_people','player_decisions':'player_only','clock':'game_time','history_before_adoption':'do_not_resimulate'}:raise EngineError('LIVING_POLICY_BINDING')
        for eid,p in rt['profiles'].items():
            _s3_entity(state,eid,True)
            if set(p['background'])!=set(LIVING_BACKGROUND) or set(p['voice'])!=set(LIVING_VOICE) or p['entity_id']!=eid:raise EngineError('LIVING_PROFILE_CONTRACT')
            if p['revision'] and not _lw_complete(p):raise EngineError('LIVING_PROFILE_INCOMPLETE')
        for nid,n in rt['life_nodes'].items():
            if n['node_id']!=nid or n['status'] not in ('pending','delivered','cancelled','superseded','superseded_player_control') or not n['source_event_id']:raise EngineError('LIVING_NODE_BINDING')
            if n['status']=='pending' and parse_iso(n['due_at'])<=parse_iso(state['game_time']):raise EngineError('LIVING_OVERDUE_NODE_NOT_PROCESSED')
        for digest,value in rt.get('portrayal_snapshots',{}).items():
            if _repair_digest(value)!=digest:raise EngineError('LIVING_PORTRAYAL_SNAPSHOT_HASH')
        for tid,x in rt['experience_receipts'].items():
            row=_s3_runtime(state)['turns'].get(tid)
            if x.get('scene_basis') and x['scene_basis'] not in rt['portrayal_snapshots']:raise EngineError('LIVING_SCENE_SNAPSHOT_MISSING')
            if x['place_basis'] not in rt['portrayal_snapshots'] or any(ref not in rt['portrayal_snapshots'] for ref in x['voice_basis'].values()):raise EngineError('LIVING_PORTRAYAL_SNAPSHOT_MISSING')
            if not row or x['experience_sha256']!=_repair_digest(row['proposal']['experience']) or x['source_event_id']!=row['source_event_id']:raise EngineError('LIVED_EXPERIENCE_RECEIPT_BINDING')
    except (EngineError,TypeError,KeyError,ValueError) as ex:out['errors'].append(str(ex))
    out['status']='FAIL' if out['errors'] else 'PASS';return out


def _lw_source_report(base):
    out=_lw_source_previous(base);state=read_json_view(Path(base)/'state.json');rt=_lw_runtime(state);refs=[]
    for group in ('profiles','places','interiors','life_nodes','experience_receipts','controls'):
        for row in rt.get(group,{}).values():
            if row.get('source_event_id'):refs.append(row['source_event_id'])
            if row.get('resolution_event_id'):refs.append(row['resolution_event_id'])
            if row.get('review_event_id'):refs.append(row['review_event_id'])
            refs.extend(r['source_event_id'] for r in row.get('forgotten',{}).values())
    for ref in set(refs):
        if not history_lookup(base,event_id=ref):out['errors'].append('LIVING_SOURCE_EVENT_MISSING')
    for nid,n in rt['life_nodes'].items():
        source=history_lookup(base,event_id=n['source_event_id']) or {};command=(source.get('domain_effect') or {}).get('command_payload') or {}
        actions=_s3_updates(command) if command.get('kind') in ('story_setup','story_turn') else []
        scheduled=next((a for a in actions if a.get('type')=='life_schedule' and a.get('node_id')==nid),None)
        if not scheduled or source.get('authorization',{}).get('status')!='verified' or any(n.get(k)!=v for k,v in scheduled.items() if k!='type'):out['errors'].append('LIVING_NODE_SOURCE_PAYLOAD_MISMATCH')
        if n['status'] in ('delivered','superseded','superseded_player_control'):
            resolved=history_lookup(base,event_id=n.get('resolution_event_id')) or {}
            if resolved.get('type')!='npc_autonomous_life' or resolved.get('node_id')!=nid or resolved.get('outcome')!=n['status'] or resolved.get('cause_event_id')!=n['source_event_id']:out['errors'].append('LIVING_NODE_RESOLUTION_BINDING')
    for tid,receipt in rt['experience_receipts'].items():
        event=history_lookup(base,event_id=receipt['source_event_id']) or {}
        if (event.get('domain_effect') or {}).get('experience_receipt_sha256')!=_repair_digest(receipt):out['errors'].append('LIVED_SOURCE_RECEIPT_BINDING')
    out['status']='FAIL' if out['errors'] else 'PASS';return out


def _lw_report(base,turn_id,viewer='player'):
    with SnapshotContext(base):
        packet=_lw_report_previous(base,turn_id,viewer)
        if packet.get('status')=='COMMITTED':
            packet['prose']='\n\n'.join(s['text'] for s in packet['segments'] if s['mode']!='verified_outcome')
            state=read_json_view(Path(base)/'state.json');rt=_lw_runtime(state);receipt=rt['experience_receipts'].get(turn_id);row=_s3_runtime(state)['turns'][turn_id]
            if receipt:packet['experience_review']={'structural':'PASS','literary':copy.deepcopy(receipt.get('literary_review','LEGACY_AI_REQUIRED')),'player_agency':'REQUIRED'}
            packet['completed_at']=row.get('completed_at',row['committed_at']);packet['clock']=_lw_public_clock(row.get('clock'),viewer)
            packet['narration_instruction']=LIVING_INSTRUCTION+'\n机械结果依据verified_results融入自然叙述；不要向玩家显示内部档案、锚点、回执JSON。'
        return packet


def living_world_packet(base=ROOT,viewer='player'):
    _s3_viewer(viewer)
    with SnapshotContext(base):
        ensure_source_ready(base);state=read_json_view(Path(base)/'state.json');rt=_lw_runtime(state)
        out={'packet':'LIVING_WORLD_STATUS_V1','game_time':state['game_time'],'policy':copy.deepcopy(rt['policy']),'instruction':LIVING_INSTRUCTION,'schemas':'development/schemas/living_world_v2.json; story_turn_v3.json','time_semantics':'Advancing game time runs global life nodes; wall-clock chat silence creates no process. Long absences use the shared bounded scheduler repeatedly.'}
        if viewer=='gm':out['profiles']=copy.deepcopy(rt['profiles']);out['life_nodes']=copy.deepcopy(rt['life_nodes'])
        return out


def _lw_boot(base=ROOT):
    out=_lw_boot_previous(base)
    out['current_guide']=(read_json_view(Path(base)/'manifest.json').get('current_guide') or {}).get('path')
    # Exact balances remain in five_balances; startupfull retains expanded views.
    out.get('fleet_core',{}).pop('gold',None);out.get('fleet_core',{}).pop('grey',None)
    out['next_layers']=['playcontext']
    if 'command_contract' in out:out['command_contract']['authorization']='trusted host or verified grant'
    # The full mandatory policy is supplied by prepare/livingworld. Boot keeps
    # its guide and enforced schema, leaving room for authenticated diagnostics.
    out['lived_experience_policy']={'enabled':True,'turn_schema':STORY_TURN_SCHEMA,'required_flow':'prepare/review/submit'}
    return _stage2_finalize_size(out,out.get('context_budget_bytes',3500))


def _lw_schema():
    out=_lw_schema_previous();out['player_additional_required']=['experience','elapsed_seconds'];out['proposal_schema']=STORY_TURN_SCHEMA;out['schema_files']='development/schemas/story_turn_v3.json and living_world_v2.json';out['lived_policy']=LIVING_INSTRUCTION;return out


def _lw_catalog(base=ROOT):
    out=_lw_catalog_previous(base);out['queries'].append('livingworld');return out


def _lw_main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    if not args or args[0]!='livingworld':return _lw_main_previous(args)
    try:
        p=argparse.ArgumentParser();p.add_argument('--base',default=str(ROOT));p.add_argument('--viewer',default='player');ns=p.parse_args(args[1:]);print(json.dumps(living_world_packet(Path(ns.base),ns.viewer),ensure_ascii=False,separators=(',',':')));return 0
    except Exception as ex:print(json.dumps({'status':'FAIL','code':str(ex).split(':')[0]}));return 1


prepare_turn=_lw_prepare
_s3_proposal_check=_lw_proposal_check
_s3_apply_update=_lw_update
_s3_action_targets=_lw_targets
_s3_presence=_lw_presence
_entity_registry_expected=_lw_entities
_knowledge_known=_lw_known
_knowledge_rows=_lw_rows
_apply_domain_command=_lw_apply
turn_report=_lw_report
_story_integrity=_lw_integrity
_story_source_report=_lw_source_report
deterministic_event_queue=_lw_queue
_resolve_deterministic_event=_lw_resolve
_set_runtime_time=_lw_set_time
_next_ai_monitor_time=_lw_next_ai
TASK_AI_BARRIER_KINDS.update({'npc_life_review','npc_life_profile'})
_deterministic_event_precedes_barrier=_lw_precedes
cold_start_packet=_lw_boot
story_schema_packet=_lw_schema
domain_command_catalog=_lw_catalog
main=_lw_main
StoryTurnService.prepare=staticmethod(prepare_turn)
StoryTurnService.report=staticmethod(turn_report)
RoundService.prepare=staticmethod(prepare_turn)
NarrativeDirector.context=staticmethod(narrative_context_packet)


# V14.61: explicit ownership, durable identity, historical knowledge and one clock.
def _lw_controlled(state,eid):
    return _lw_runtime(state).get('controls',{}).get(eid,{}).get('active') is True


def _lw_owns(state,viewer,eid):
    return bool(eid) and (viewer in ('gm','npc:'+eid) or viewer=='player' and _lw_controlled(state,eid))


def _lw_is_present(state,rec,eid):
    try:_s3_presence(state,rec,eid,rec.get('presence_mode','present'));return True
    except EngineError:return False


def _lw_move(state,eid,location,event):
    rt=_lw_runtime(state);npc=_s3_runtime(state)['npcs'].get(eid)
    if not npc or eid not in rt['profiles']:raise EngineError('LIVING_PERSON_RUNTIME_NOT_INITIALIZED:'+eid)
    if npc.get('location_ref')!=location:
        epochs=rt.setdefault('presence_epochs',{});epochs[eid]=epochs.get(eid,0)+1
    npc.update(location_ref=location,last_event_id=event);npc['revision']+=1
    rt['profiles'][eid]['location_ref']=location


def _lw_validate_routine(rows):
    if not isinstance(rows,list) or len(rows)>24:raise EngineError('LIVING_ROUTINE_LIMIT')
    occupied=set()
    for r in rows:
        _s3_fields(r,{'start_minute','end_minute','activity'});lo=r['start_minute'];hi=r['end_minute'];_lw_text(r['activity'],200)
        if type(lo) is not int or type(hi) is not int or not 0<=lo<1440 or not 0<=hi<=1440 or lo==hi:raise EngineError('LIVING_ROUTINE_TIME')
        minutes=set(range(lo,hi)) if lo<hi else set(range(lo,1440))|set(range(hi))
        if occupied&minutes:raise EngineError('LIVING_ROUTINE_OVERLAP')
        occupied|=minutes


def _lw_profile_correction(stage,state,eid,old,record):
    changed={k:v for k,v in record['background'].items() if v!=old['background'][k]}
    if not changed:return
    if record['source_kind']!='confirmed_evidence':raise EngineError('LIVING_EXISTING_HISTORY_REWRITE_DENIED')
    verified={}
    for ref in record['basis_refs']:
        parts=ref.split('/') if isinstance(ref,str) else []
        if len(parts)!=3 or parts[0]!='fact':continue
        fact=_knowledge_facts(state,parts[1]).get(parts[2]);value=(fact or {}).get('value')
        if isinstance(value,str):
            try:value=json.loads(value)
            except (ValueError,TypeError):continue
        if not fact or fact.get('epistemic')!='confirmed' or fact.get('subject_id')!=eid or not isinstance(value,dict):continue
        if not fact.get('source_event_ids') or not all(history_lookup(stage,event_id=e) for e in fact['source_event_ids']):continue
        if value.get('profile_field') in changed and value.get('value')==changed[value['profile_field']]:verified[value['profile_field']]=ref
    if set(verified)!=set(changed):raise EngineError('LIVING_PROFILE_CORRECTION_COMMITTED_EVIDENCE_REQUIRED')
    old.setdefault('corrections',[]).append({'at':state['game_time'],'source_event_id':_story_event_context()['event_id'],'before':{k:old['background'][k] for k in changed},'after':copy.deepcopy(changed),'evidence':verified})


def _lw_rewrite_refs(state,row,eid):
    snapshot=_lw_runtime(state)['experience_receipts'].get(row['turn_id'],{}).get('knowledge_basis')
    if snapshot is not None:return set(snapshot.get(eid,[]))
    # Legacy receipts never grant knowledge that was not actually used then.
    return {r for s in row['proposal']['segments'] if s.get('speaker_id')==eid for r in s['basis_refs']}


def _lw_require_review(proposal):
    review=_lw_review_scope.get()
    if not isinstance(review,dict) or review.get('proposal_sha256')!=_repair_digest(proposal) or review.get('status')!='PASS' or review.get('criteria')!=['living_prose','voice_and_knowledge','sensory_grounding','player_agency']:raise EngineError('LIVED_TRUSTED_NARRATIVE_REVIEW_REQUIRED')


@contextmanager
def narrative_review_context(proposal,reviewer):
    """Trusted host adapter only. reviewer independently reads the exact proposal.
    Never pass a callback that just copies proposal flags or always returns True.
    This grants no command authority and executes no effects.
    """
    snapshot=copy.deepcopy(proposal);digest=_repair_digest(snapshot)
    verdict=reviewer(snapshot) if callable(reviewer) else None
    if _repair_digest(snapshot)!=digest or _repair_digest(proposal)!=digest:raise EngineError('LIVED_REVIEW_INPUT_CHANGED')
    if not isinstance(verdict,dict) or verdict.get('status')!='PASS' or verdict.get('criteria')!=['living_prose','voice_and_knowledge','sensory_grounding','player_agency']:raise EngineError('LIVED_TRUSTED_NARRATIVE_REVIEW_REQUIRED')
    attestation={'status':'PASS','criteria':copy.deepcopy(verdict['criteria']),'proposal_sha256':digest}
    token=_lw_review_scope.set(attestation)
    try:yield copy.deepcopy(attestation)
    finally:_lw_review_scope.reset(token)


def _lw_inflight_creation(eid):
    row=_lw_clock_scope.get()
    return copy.deepcopy(row) if row and row.get('event_id')==eid else None


def _lw_advance_round(stage,state,tasks,payload,start):
    duration=payload['proposal']['elapsed_seconds'];target=parse_iso(start)+dt.timedelta(seconds=duration);cursor=parse_iso(state['game_time'])
    if cursor!=parse_iso(start):raise EngineError('STORY_EFFECT_MUST_NOT_ADVANCE_CLOCK')
    rules=load_runtime_rules(stage);world='';executed=[];changes=[];seen=set()
    digest=_domain_payload_digest(payload);eid='DOMAIN-'+payload['command_id']+'-'+sha256_bytes(digest.encode())[:8]
    token=_lw_clock_scope.set({'event_id':eid,'payload_sha256':digest,'authorization':{'status':'verified','authority':payload['authorization']}})
    try:
        while cursor<=target:
            ai=_next_ai_monitor_time(tasks,cursor,target,state)
            lh=preview_long_horizon(state,rules,target,max_events=_mechanical_multi_event_limit(rules))
            if lh.get('truncated'):raise EngineError('STORY_TIME_SCHEDULER_LIMIT')
            hazards=[e for e in lh.get('events',[]) if e.get('requires_simulation',True) and parse_iso(e.get('time')) and cursor<=parse_iso(e['time'])<=target]
            barriers=([ai] if ai else [])+[{'time':parse_iso(e['time']),'kind':'hazard','event':e} for e in hazards]
            barrier=min(barriers,key=lambda b:(b['time'],b.get('kind',''))) if barriers else None
            hard=barrier['time'] if barrier else target
            queue=deterministic_event_queue(state,tasks,cursor,hard);event=queue[0] if queue else None;when=parse_iso(event['time']) if event else None
            if event and _deterministic_event_precedes_barrier(event,when,hard,barrier):
                key=(event.get('source'),event.get('task_id'),event.get('job_id'),event.get('resolver'),event.get('time'))
                if key in seen:raise EngineError('STORY_TIME_SCHEDULER_NO_PROGRESS')
                if len(seen)>=1024:raise EngineError('STORY_TIME_SCHEDULER_LIMIT')
                seen.add(key)
                mechanical=_set_runtime_time(state,tasks,world,when,rules);executed.extend(_record_mechanical_hazards(stage,state,mechanical));cursor=when
                row=_resolve_deterministic_event(stage,state,tasks,event,when)
                if not isinstance(row,dict) or row.get('status')=='AI_REQUIRED':raise EngineError('STORY_TIME_NEEDS_AI:'+json.dumps(row,ensure_ascii=False,default=str))
                executed.append(copy.deepcopy(row));changes.extend(row.get('changes',[]));continue
            if barrier:raise EngineError('STORY_TIME_NEEDS_AI:'+json.dumps(barrier,ensure_ascii=False,default=str))
            if cursor<target:
                mechanical=_set_runtime_time(state,tasks,world,target,rules);executed.extend(_record_mechanical_hazards(stage,state,mechanical));cursor=target
            break
    finally:_lw_clock_scope.reset(token)
    return {'schema':'STORY_CLOCK_V1','started_at':start,'completed_at':state['game_time'],'elapsed_seconds':duration,'scheduler':'shared_deterministic_queue','executed':executed,'changes':changes,'command_sha256':digest}


def _lw_domain_postcheck(state,tasks,before,payload,effect):
    after=state['game_time']
    if after==before:return _phase2_domain_post_mutation_validate(state,tasks,before)
    clock=effect.get('clock') or {};p=payload.get('proposal') or {};seconds=p.get('elapsed_seconds')
    if payload.get('kind')!='story_turn' or type(seconds) is not int or not 1<=seconds<=86400 or clock.get('schema')!='STORY_CLOCK_V1' or clock.get('command_sha256')!=_domain_payload_digest(payload) or clock.get('started_at')!=before or clock.get('completed_at')!=after or parse_iso(after)!=parse_iso(before)+dt.timedelta(seconds=seconds):raise EngineError('DOMAIN_COMMAND_MUST_NOT_ADVANCE_GAME_TIME')
    result=_phase2_domain_post_mutation_validate(state,tasks,after)
    result['checks']=[c for c in result['checks'] if c!='game_time_unchanged']+['authorized_story_duration_exact','shared_scheduler_atomic_with_effects']
    return result


def _lw_public_clock(clock,viewer='player'):
    if clock is None:return None
    if viewer=='gm':return copy.deepcopy(clock)
    return {k:copy.deepcopy(clock[k]) for k in ('schema','started_at','completed_at','elapsed_seconds','scheduler') if k in clock}


def _lw_clock_projection(value,viewer):
    if isinstance(value,dict):
        if value.get('schema')=='STORY_CLOCK_V1':return _lw_public_clock(value,viewer)
        return {k:_lw_clock_projection(v,viewer) for k,v in value.items()}
    if isinstance(value,list):return [_lw_clock_projection(v,viewer) for v in value]
    return value
